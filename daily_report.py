# -*- coding: utf-8 -*-
"""全球市场速览 - A股/港股/美股 + ETF排行 + 新闻情绪"""

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


# ------------------------- A股指数（新浪） -------------------------
def fetch_a_share_indices():
    idx_map = [
        ("sh000001", "上证指数"), ("sz399001", "深证成指"),
        ("sz399006", "创业板指"), ("sh000688", "科创50"),
    ]
    results = []
    for symbol, name in idx_map:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            last = df.iloc[-1]
            pct = 0.0
            if len(df) >= 2:
                prev_close = df.iloc[-2]["close"]
                pct = round((last["close"] - prev_close) / prev_close * 100, 2)
            results.append({"指数": name, "最新价": last["close"], "涨跌幅(%)": pct})
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
            last = df.iloc[-1]
            pct = 0.0
            if len(df) >= 2:
                prev = df.iloc[-2]["close"]
                pct = round((last["close"] - prev) / prev * 100, 2)
            results.append({"指数": name, "最新价": last["close"], "涨跌幅(%)": pct})
        except Exception as e:
            print(f"  港股 {name} 失败: {e}")
    return pd.DataFrame(results)


# ------------------------- 美股指数（新浪） -------------------------
def fetch_us_indices():
    us_map = [(".DJI", "道琼斯"), (".IXIC", "纳斯达克"), (".INX", "标普500")]
    results = []
    for sym, name in us_map:
        try:
            df = ak.index_us_stock_sina(symbol=sym)
            last = df.iloc[-1]
            pct = 0.0
            if len(df) >= 2:
                prev = df.iloc[-2]["close"]
                pct = round((last["close"] - prev) / prev * 100, 2)
            results.append({"指数": name, "最新价": last["close"], "涨跌幅(%)": pct})
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


# ------------------------- 板块排行（东财，可能被墙） -------------------------
def fetch_top_sectors():
    try:
        sector_df = ak.stock_board_industry_name_em()
        top = sector_df.nlargest(5, "涨跌幅")[["板块名称", "涨跌幅"]]
        top.columns = ["板块", "涨跌幅(%)"]
        return top
    except Exception:
        print("  板块数据不可用")
        return pd.DataFrame(columns=["板块", "涨跌幅(%)"])


# ------------------------- ETF排行（同花顺） -------------------------
def fetch_all_etfs():
    try:
        d = ak.fund_etf_spot_ths()
        name_col = d.iloc[:, 2]
        pct_col = pd.to_numeric(d.iloc[:, 8], errors="coerce")
        df_clean = pd.DataFrame({"名称": name_col, "涨跌幅(%)": pct_col}).dropna(subset=["涨跌幅(%)"])

        def market_classify(name):
            nu = str(name).upper()
            if any(k in nu for k in ["港股", "恒生", "H股", "香港"]):
                return "港股"
            if any(k in nu for k in ["美股", "纳斯达克", "标普", "道琼斯", "纳指", "美国", "QQQ", "SPY"]):
                return "美股"
            return "A股"

        df_clean["市场"] = df_clean["名称"].apply(market_classify)
        return df_clean
    except Exception as e:
        print(f"ETF数据失败: {e}")
        return pd.DataFrame(columns=["名称", "涨跌幅(%)", "市场"])


def get_top_bottom_funds(df_fund, top_n=10):
    if df_fund.empty:
        return pd.DataFrame(), pd.DataFrame()
    df_sorted = df_fund.sort_values("涨跌幅(%)", ascending=False)
    return df_sorted.head(top_n), df_sorted.tail(top_n)


# ------------------------- 新闻情绪分析（东财） -------------------------
def fetch_news_sentiment():
    result = {"A股": {"bull": [], "bear": []},
              "港股": {"bull": [], "bear": []},
              "美股": {"bull": [], "bear": []}}
    try:
        news_df = ak.stock_news_em()
        if news_df.empty:
            return result
        market_kw = {
            "A股": ["A股", "沪深", "上证", "深证", "创业板", "科创", "北交所", "央行", "证监会"],
            "港股": ["港股", "恒生", "H股", "香港", "南下资金", "港股通"],
            "美股": ["美股", "道琼斯", "纳斯达克", "标普", "美联储", "美国", "中概股"],
        }
        bull_kw = ["上涨", "大涨", "利好", "突破", "提振", "放量", "净流入", "增持", "看好", "强势", "反弹", "新高", "降息"]
        bear_kw = ["下跌", "大跌", "利空", "跌破", "拖累", "缩量", "净流出", "减持", "看空", "弱势", "回调", "新低", "加息"]

        for _, row in news_df.iterrows():
            title = str(row.get("内容", ""))
            if not title:
                continue
            market = None
            for m, keys in market_kw.items():
                if any(k in title for k in keys):
                    market = m
                    break
            if market is None:
                continue
            sentiment = None
            if any(k in title for k in bull_kw):
                sentiment = "bull"
            elif any(k in title for k in bear_kw):
                sentiment = "bear"
            if sentiment:
                titles_seen = [item["title"] for item in result[market][sentiment]]
                if title not in titles_seen and len(result[market][sentiment]) < 5:
                    result[market][sentiment].append({"title": title})
        return result
    except Exception as e:
        print(f"  新闻分析不可用: {e}")
        return result


# ------------------------- HTML 报告 -------------------------
def build_html(a_idx, hk_idx, us_idx, updown, sec, etf_df):
    ds = datetime.now().strftime("%Y年%m月%d日")

    def cv(v):
        try:
            f = float(str(v).replace("%", "").strip())
            return "red" if f > 0 else ("green" if f < 0 else "gray")
        except Exception:
            return "black"

    def make_table(hd, rows, bg):
        if not rows:
            return "<p>暂无数据</p>"
        h = "".join(f"<th>{x}</th>" for x in hd)
        b = "".join("<tr>" + "".join(f"<td style='color:{cv(z)}'>{z}</td>" for z in r) + "</tr>" for r in rows)
        return f"<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse;width:100%;'><tr style='background-color:{bg};color:white;'>{h}</tr>{b}</table>"

    html = f"""<html><head><meta charset="utf-8"></head>
<body style="font-family:Microsoft YaHei,sans-serif;">
<h2>🌍 全球市场速览 - {ds}</h2>
<p><b>市场情绪：</b>{updown}</p>
<h3>🇨🇳 A股指数</h3>{make_table(["指数","最新价","涨跌幅"],[(r['指数'],r['最新价'],f"{r['涨跌幅(%)']}%") for _,r in a_idx.iterrows()],"#C00000")}
<h3>🇭🇰 港股指数</h3>{make_table(["指数","最新价","涨跌幅"],[(r['指数'],r['最新价'],f"{r['涨跌幅(%)']}%") for _,r in hk_idx.iterrows()],"#0072C6")}
<h3>🇺🇸 美股指数</h3>{make_table(["指数","最新价","涨跌幅"],[(r['指数'],r['最新价'],f"{r['涨跌幅(%)']}%") for _,r in us_idx.iterrows()],"#548235")}
<h3>🔥 热门板块 TOP5</h3>{make_table(["板块","涨跌幅"],[(r['板块'],f"{r['涨跌幅(%)']}%") for _,r in sec.iterrows()],"#ED7D31")}
"""

    # ETF 排行按市场分组
    for mkt_name, mkt_key in [("A股ETF排行", "A股"), ("港股ETF排行", "港股"), ("美股ETF排行", "美股")]:
        sub = etf_df[etf_df["市场"] == mkt_key]
        if sub.empty:
            html += f"<h3>📊 {mkt_name}</h3><p>暂无数据</p>"
            continue
        top, bottom = get_top_bottom_funds(sub, 5)
        rows_top = [(r['名称'], f"{r['涨跌幅(%)']}%") for _, r in top.iterrows()]
        rows_btm = [(r['名称'], f"{r['涨跌幅(%)']}%") for _, r in bottom.iterrows()]
        html += f"<h3>📊 {mkt_name}</h3><h4>涨幅 TOP5</h4>{make_table(['名称','涨跌幅'],rows_top,'#70AD47')}<h4>跌幅 TOP5</h4>{make_table(['名称','涨跌幅'],rows_btm,'#FF0000')}"

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
    sec = fetch_top_sectors()
    etf = fetch_all_etfs()
    print(f"完成: A股={len(a_idx)}, 港股={len(hk_idx)}, 美股={len(us_idx)}, 板块={len(sec)}, ETF={len(etf)}")

    html = build_html(a_idx, hk_idx, us_idx, ud, sec, etf)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("报告已保存: report.html")
    send_email(html)
    print("运行完成。")


if __name__ == "__main__":
    main()
