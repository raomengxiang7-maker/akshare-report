# -*- coding: utf-8 -*-
"""A股市场每日速览 - 自动化报告 (多数据源版)"""

import akshare as ak
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import traceback

SENDER = "raomengxiang7@outlook.com"
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
RECEIVER = "raomengxiang7@outlook.com"


def is_trade_day():
    try:
        today = datetime.now().strftime("%Y%m%d")
        trade_df = ak.tool_trade_date_hist_sina()
        trade_dates = trade_df["trade_date"].astype(str).tolist()
        return today in trade_dates
    except Exception:
        return datetime.now().weekday() < 5


def fetch_index_data():
    idx_map = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sz399006", "创业板指"),
        ("sh000688", "科创50"),
    ]
    results = []
    for symbol, name in idx_map:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            last = df.iloc[-1]
            pct = round((last["close"] - last["open"]) / last["open"] * 100, 2)
            results.append({
                "指数": name, "最新价": last["close"],
                "涨跌幅(%)": pct, "成交额(元)": last.get("amount", 0),
            })
        except Exception as e:
            print(f"  指数 {name} 获取失败: {e}")
    return pd.DataFrame(results)


def fetch_market_sentiment():
    try:
        df = ak.stock_zh_a_spot()
        up = int((df["涨跌幅"] > 0).sum())
        down = int((df["涨跌幅"] < 0).sum())
        return f"上涨 {up} 家，下跌 {down} 家", df
    except Exception as e:
        print(f"市场情绪获取失败: {e}")
        return "数据获取中...", None


def fetch_top_etfs():
    try:
        d = ak.fund_etf_spot_ths()
        d["代码_str"] = d.iloc[:, 1].astype(str)
        d["涨跌幅"] = pd.to_numeric(d.iloc[:, 8], errors="coerce")
        mask = d["代码_str"].str.match(r"^(51|159)", na=False)
        etf = d[mask].dropna(subset=["涨跌幅"])
        top = etf.nlargest(5, "涨跌幅")
        return pd.DataFrame({"ETF名称": top.iloc[:, 2].values, "涨跌幅(%)": top.iloc[:, 8].values})
    except Exception as e:
        print(f"  ETF获取失败: {e}")
        return pd.DataFrame(columns=["ETF名称", "涨跌幅(%)"])


def fetch_top_sectors():
    try:
        sector_df = ak.stock_board_industry_name_em()
        top = sector_df.nlargest(5, "涨跌幅")[["板块名称", "涨跌幅"]]
        top.columns = ["板块", "涨跌幅(%)"]
        return top
    except Exception:
        print("  板块数据不可用")
        return pd.DataFrame(columns=["板块", "涨跌幅(%)"])


def fetch_top_stocks(stock_df):
    try:
        cond = (
            ~stock_df["名称"].str.contains("ST|退", na=False)
            & (stock_df["最新价"] > 0)
            & (stock_df["涨跌幅"] < 20)
        )
        valid = stock_df[cond].copy()
        top = valid.nlargest(10, "涨跌幅")[["名称", "涨跌幅"]]
        top.columns = ["股票", "涨跌幅(%)"]
        return top
    except Exception as e:
        print(f"个股筛选失败: {e}")
        return pd.DataFrame(columns=["股票", "涨跌幅(%)"])


def build_html(idx, updown, sec, etf, stk):
    ds = datetime.now().strftime("%Y年%m月%d日")

    def cv(v):
        try:
            return "red" if float(v) > 0 else ("green" if float(v) < 0 else "gray")
        except Exception:
            return "black"

    def tbl(hd, rows, bg):
        if not rows:
            return "<p>暂无数据</p>"
        h = "".join(f"<th>{x}</th>" for x in hd)
        b = "".join("<tr>" + "".join(f"<td style='color:{cv(str(z).replace(chr(37),'').strip())}'>{z}</td>" for z in r) + "</tr>" for r in rows)
        return f"<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse;width:100%;'><tr style='background-color:{bg};color:white;'>{h}</tr>{b}</table>"

    return f"""<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Microsoft YaHei,sans-serif;">
<h2>📊 A股市场速览 - {ds}</h2>
<p><b>市场情绪：</b>{updown}</p>
<h3>🏛️ 大盘指数</h3>{tbl(["指数","最新价","涨跌幅","成交额"],[(r["指数"],r["最新价"],f"{r['涨跌幅(%)']}%",r["成交额(元)"]) for _,r in idx.iterrows()],"#4472C4")}
<h3>🔥 热门行业板块 TOP5</h3>{tbl(["板块名称","涨跌幅"],[(r["板块"],f"{r['涨跌幅(%)']}%") for _,r in sec.iterrows()],"#ED7D31")}
<h3>📈 热门ETF TOP5</h3>{tbl(["ETF名称","涨跌幅"],[(r["ETF名称"],f"{r['涨跌幅(%)']}%") for _,r in etf.iterrows()],"#70AD47")}
<h3>🚀 个股涨幅 TOP10</h3>{tbl(["股票","涨跌幅"],[(r["股票"],f"{r['涨跌幅(%)']}%") for _,r in stk.iterrows()],"#FFC000")}
</body></html>"""


def send_email(html):
    pwd = os.environ.get("EMAIL_PWD")
    if not pwd:
        print("错误：未设置 EMAIL_PWD 环境变量")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"A股市场速览 - {datetime.now().strftime('%Y-%m-%d')}"
        msg["From"] = SENDER
        msg["To"] = RECEIVER
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls()
            s.login(SENDER, pwd)
            s.sendmail(SENDER, RECEIVER, msg.as_string())
        print(f"邮件发送成功 -> {RECEIVER}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("邮件失败: Outlook SMTP认证被禁用，需使用应用密码")
        print("详见 https://aka.ms/smtp_auth_disabled")
        return False
    except Exception as e:
        print(f"邮件发送失败: {e}")
        traceback.print_exc()
        return False


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] A股日报启动")
    if not is_trade_day() and os.environ.get("FORCE_RUN") != "true":
        print("今天非交易日，跳过。")
        return
    print("正在抓取数据...")
    idx = fetch_index_data()
    ud, sdf = fetch_market_sentiment()
    sec = fetch_top_sectors()
    etf = fetch_top_etfs()
    stk = fetch_top_stocks(sdf) if sdf is not None else pd.DataFrame()
    print(f"完成: 指数={len(idx)}, 板块={len(sec)}, ETF={len(etf)}, 个股={len(stk)}")
    html = build_html(idx, ud, sec, etf, stk)
    # Always save HTML report as artifact
    report_path = "report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"报告已保存: {report_path}")
    send_email(html)
    print("运行完成。")


if __name__ == "__main__":
    main()
