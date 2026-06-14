# -*- coding: utf-8 -*-
"""全球市场速览 - A股/港股/美股 + 多周期涨跌幅 + ETF排行"""

import akshare as ak
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import traceback

# ------------------------- 邮件配置 -------------------------
SENDER = "1753380036@qq.com"
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
RECEIVER = "1753380036@qq.com"


# ------------------------- 周期涨跌幅计算 -------------------------
def calc_period_perf(df):
    """
    df: 日线数据 DataFrame (需包含 'close' 列，按日期升序)
    返回 dict: {'day':日涨跌幅, 'week':近一周, 'month':近一月, 'year':近一年}
    """
    perf = {"day": None, "week": None, "month": None, "year": None}
    if df.empty or len(df) < 2:
        return perf
    l = df.iloc[-1]["close"]
    # 日涨跌幅 = 当日与前一日
    p = df.iloc[-2]["close"]
    perf["day"] = round((l - p) / p * 100, 2)
    # 近1周 ≈ 5个交易日
    if len(df) >= 6:
        p5 = df.iloc[-6]["close"]
        perf["week"] = round((l - p5) / p5 * 100, 2)
    # 近1月 ≈ 21个交易日
    if len(df) >= 22:
        p21 = df.iloc[-22]["close"]
        perf["month"] = round((l - p21) / p21 * 100, 2)
    # 近1年 ≈ 252个交易日
    if len(df) >= 253:
        p252 = df.iloc[-253]["close"]
        perf["year"] = round((l - p252) / p252 * 100, 2)
    return perf


# ------------------------- A股指数（新浪） -------------------------
def fetch_a_share_indices():
    idx_map = [
        ("sh000001", "上证指数"), ("sz399001", "深证成指"),
        ("sz399006", "创业板指"), ("sh000688", "科创50"),
        ("sh000300", "沪深300"), ("sh000905", "中证500"),
        ("sh000510", "中证A500"), ("sh000906", "中证800"),
        ("sh000852", "中证1000"),
    ]
    results = []
    for symbol, name in idx_map:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            last = df.iloc[-1]["close"]
            perf = calc_period_perf(df)
            results.append({
                "指数": name, "最新价": last,
                "日涨跌幅": perf["day"], "周涨跌幅": perf["week"],
                "月涨跌幅": perf["month"], "年涨跌幅": perf["year"],
            })
        except Exception as e:
            print(f"  A股 {name} 失败: {e}")
    return pd.DataFrame(results)


# ------------------------- 港股指数（新浪） -------------------------
def fetch_hk_indices():
    hk_map = [("HSI", "恒生指数"), ("HSCEI", "恒生中国企业指数"), ("HSTECH", "恒生科技指数")]
    results = []
    for sym, name in hk_map:
        try:
            df = ak.stock_hk_index_daily_sina(symbol=sym)
            last = df.iloc[-1]["close"]
            perf = calc_period_perf(df)
            results.append({
                "指数": name, "最新价": last,
                "日涨跌幅": perf["day"], "周涨跌幅": perf["week"],
                "月涨跌幅": perf["month"], "年涨跌幅": perf["year"],
            })
        except Exception as e:
            print(f"  港股 {name} 失败: {e}")
    return pd.DataFrame(results)


# ------------------------- 美股指数（新浪） -------------------------
def fetch_us_indices():
    us_map = [(".DJI", "道琼斯"), (".IXIC", "纳斯达克"),
              (".INX", "标普500"), (".NDX", "纳斯达克100")]
    results = []
    for sym, name in us_map:
        try:
            df = ak.index_us_stock_sina(symbol=sym)
            last = df.iloc[-1]["close"]
            perf = calc_period_perf(df)
            results.append({
                "指数": name, "最新价": last,
                "日涨跌幅": perf["day"], "周涨跌幅": perf["week"],
                "月涨跌幅": perf["month"], "年涨跌幅": perf["year"],
            })
        except Exception as e:
            print(f"  美股 {name} 失败: {e}")
    return pd.DataFrame(results)


# ------------------------- 市场情绪（新浪） -------------------------
def fetch_market_sentiment():
    try:
        df = ak.stock_zh_a_spot()
        up = int((df["涨跌幅"] > 0).sum())
        down = int((df["涨跌幅"] < 0).sum())
        return f"上涨 {up} 家，下跌 {down} 家", df
    except Exception as e:
        print(f"市场情绪失败: {e}")
        return "数据获取中...", None


# ------------------------- ETF排行（同花顺） -------------------------
def fetch_etfs():
    try:
        d = ak.fund_etf_spot_ths()
        name_col = d.iloc[:, 2]  # 名称
        pct_col = pd.to_numeric(d.iloc[:, 8], errors="coerce")
        df_clean = pd.DataFrame({"名称": name_col, "涨跌幅(%)": pct_col}).dropna(subset=["涨跌幅(%)"])
        return df_clean.sort_values("涨跌幅(%)", ascending=False)
    except Exception as e:
        print(f"ETF数据失败: {e}")
        return pd.DataFrame(columns=["名称", "涨跌幅(%)"])


# ------------------------- HTML 报告 -------------------------
def build_html(a_idx, hk_idx, us_idx, updown, etf_sorted):
    ds = datetime.now().strftime("%Y年%m月%d日")

    def cv(v):
        try:
            f = float(str(v).replace("%", "").strip())
            return "red" if f > 0 else ("green" if f < 0 else "gray")
        except Exception:
            return "black"

    def make_table(hd, rows):
        if not rows:
            return "<p>暂无数据</p>"
        h = "".join(f"<th>{x}</th>" for x in hd)
        b = "".join("<tr>" + "".join(f"<td style='color:{cv(z)}'>{z}</td>" for z in r) + "</tr>" for r in rows)
        return f"<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse;width:100%;'>{h}{b}</table>"

    def color_header(c):
        return f"<tr style='background-color:{c};color:white;'>"

    # 指数表格: hd = [指数, 最新价, 日涨跌幅, 周涨跌幅, 月涨跌幅, 年涨跌幅]
    idh = ["指数", "最新价", "日涨跌幅", "周涨跌幅", "月涨跌幅", "年涨跌幅"]

    def idx_rows(df):
        return [(r["指数"], r["最新价"],
                 f"{r['日涨跌幅']}%" if pd.notna(r.get('日涨跌幅')) else "-",
                 f"{r['周涨跌幅']}%" if pd.notna(r.get('周涨跌幅')) else "-",
                 f"{r['月涨跌幅']}%" if pd.notna(r.get('月涨跌幅')) else "-",
                 f"{r['年涨跌幅']}%" if pd.notna(r.get('年涨跌幅')) else "-") for _, r in df.iterrows()]

    html = f"""<html><head><meta charset="utf-8"></head>
<body style="font-family:Microsoft YaHei,sans-serif;">
<h2>🌍 全球市场速览 - {ds}</h2>
<p><b>市场情绪：</b>{updown}</p>

<h3>🇨🇳 A股指数</h3>{make_table(idh, idx_rows(a_idx))}
<h3>🇭🇰 港股指数</h3>{make_table(idh, idx_rows(hk_idx))}
<h3>🇺🇸 美股指数</h3>{make_table(idh, idx_rows(us_idx))}
"""

    # ETF 排行（仅A股ETF）
    if not etf_sorted.empty:
        top10 = etf_sorted.head(10)
        bottom10 = etf_sorted.tail(10).sort_values("涨跌幅(%)", ascending=True)
        html += f"""<h3>📊 ETF 排行</h3>
<h4>涨幅 TOP10</h4>{make_table(["名称","涨跌幅"],[(r['名称'],f"{r['涨跌幅(%)']}%") for _,r in top10.iterrows()])}
<h4>跌幅 TOP10</h4>{make_table(["名称","涨跌幅"],[(r['名称'],f"{r['涨跌幅(%)']}%") for _,r in bottom10.iterrows()])}
"""
    else:
        html += "<h3>📊 ETF 排行</h3><p>暂无数据</p>"

    html += "</body></html>"
    return html


# ------------------------- 发送邮件 -------------------------
def send_email(html):
    pwd = os.environ.get("EMAIL_PWD")
    if not pwd:
        print("错误：未设置 EMAIL_PWD 环境变量")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"全球市场速览 - {datetime.now().strftime('%Y-%m-%d')}"
        msg["From"] = SENDER
        msg["To"] = RECEIVER
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as s:
            s.login(SENDER, pwd)
            s.sendmail(SENDER, RECEIVER, msg.as_string())
        print(f"邮件发送成功 -> {RECEIVER}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        traceback.print_exc()
        return False


# ------------------------- 主函数 -------------------------
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 全球市场日报启动")
    if not ak.tool_trade_date_hist_sina().empty:
        today = datetime.now().strftime("%Y%m%d")
        tdates = ak.tool_trade_date_hist_sina()["trade_date"].astype(str).tolist()
        if today not in tdates and os.environ.get("FORCE_RUN") != "true":
            print("今天非交易日，跳过。")
            return

    print("正在抓取全球市场数据...")
    a_idx = fetch_a_share_indices()
    hk_idx = fetch_hk_indices()
    us_idx = fetch_us_indices()
    ud, _ = fetch_market_sentiment()
    etf = fetch_etfs()
    print(f"完成: A股={len(a_idx)}, 港股={len(hk_idx)}, 美股={len(us_idx)}, ETF={len(etf)}")

    html = build_html(a_idx, hk_idx, us_idx, ud, etf)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("报告已保存: report.html")
    send_email(html)
    print("运行完成。")


if __name__ == "__main__":
    main()
