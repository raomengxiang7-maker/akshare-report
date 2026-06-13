# -*- coding: utf-8 -*-
"""
A股市场每日速览 - 自动化报告
定时抓取A股数据并发送HTML邮件报告
"""

import akshare as ak
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import traceback

# ========== 配置区 ==========
SENDER = "raomengxiang7@outlook.com"
SMTP_SERVER = "smtp-mail.outlook.com"
SMTP_PORT = 587
PASSWORD = os.environ.get("EMAIL_PWD")
RECEIVER = "raomengxiang7@outlook.com"
# ===========================


def is_trade_day():
    """判断今天是否为交易日"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        trade_df = ak.tool_trade_date_hist_sina()
        trade_dates = trade_df['trade_date'].astype(str).tolist()
        return today in trade_dates
    except Exception:
        wd = datetime.now().weekday()
        return wd < 5


def fetch_data():
    """抓取A股市场数据"""
    try:
        index_df = ak.stock_zh_index_spot_em()
        target = ['上证指数', '深证成指', '创业板指', '科创50']
        index_df = index_df[index_df['名称'].isin(target)][['名称', '最新价', '涨跌幅', '成交量', '成交额']]
        index_df.columns = ['指数', '最新价', '涨跌幅(%)', '成交量(手)', '成交额(元)']
        index_df = index_df.reset_index(drop=True)

        market_df = ak.stock_zh_index_spot_em()
        up_col = [c for c in market_df.columns if '上涨' in c]
        down_col = [c for c in market_df.columns if '下跌' in c]
        if up_col and down_col:
            up = market_df[up_col[0]].dropna().iloc[0] if not market_df[up_col[0]].dropna().empty else 'N/A'
            down = market_df[down_col[0]].dropna().iloc[0] if not market_df[down_col[0]].dropna().empty else 'N/A'
        else:
            up, down = 'N/A', 'N/A'

        sector_df = ak.stock_board_industry_name_em()
        top_sectors = sector_df.nlargest(5, '涨跌幅')[['板块名称', '涨跌幅']]
        top_sectors.columns = ['板块', '涨跌幅(%)']

        etf_df = ak.fund_etf_spot_em()
        mask = ~etf_df['名称'].str.contains('债|货币|国债|逆回购|回购', case=False, na=False)
        etf_stock = etf_df[mask].copy()
        etf_stock['涨跌幅'] = pd.to_numeric(etf_stock['涨跌幅'], errors='coerce')
        top_etf = etf_stock.nlargest(5, '涨跌幅')[['名称', '涨跌幅']]
        top_etf.columns = ['ETF名称', '涨跌幅(%)']

        stock_df = ak.stock_zh_a_spot_em()
        stock_df['涨跌幅'] = pd.to_numeric(stock_df['涨跌幅'], errors='coerce')
        cond = (
            ~stock_df['名称'].str.contains('ST|退', na=False) &
            (stock_df['最新价'] > 0) &
            (stock_df['涨跌幅'] < 20)
        )
        valid_stock = stock_df[cond].copy()
        top_stocks = valid_stock.nlargest(10, '涨跌幅')[['名称', '涨跌幅']]
        top_stocks.columns = ['股票', '涨跌幅(%)']

        return {
            'index': index_df,
            'up_down': f"上涨 {up} 家，下跌 {down} 家",
            'sectors': top_sectors,
            'etf': top_etf,
            'stocks': top_stocks
        }
    except Exception as e:
        print(f"数据抓取出错: {e}")
        traceback.print_exc()
        return None


def build_html(data):
    """构建HTML邮件内容"""
    date_str = datetime.now().strftime("%Y年%m月%d日")

    def color(val):
        try:
            v = float(val)
        except Exception:
            return 'black'
        return 'red' if v > 0 else ('green' if v < 0 else 'gray')

    index_rows = ""
    for _, row in data['index'].iterrows():
        chg = row['涨跌幅(%)']
        c = color(chg)
        index_rows += (
            f"<tr><td>{row['指数']}</td><td>{row['最新价']}</td>"
            f"<td style='color:{c};font-weight:bold'>{chg}%</td>"
            f"<td>{row['成交额(元)']}</td></tr>"
        )

    sector_rows = ""
    for _, row in data['sectors'].iterrows():
        c = color(row['涨跌幅(%)'])
        sector_rows += (
            f"<tr><td>{row['板块']}</td>"
            f"<td style='color:{c};font-weight:bold'>{row['涨跌幅(%)']}%</td></tr>"
        )

    etf_rows = ""
    for _, row in data['etf'].iterrows():
        c = color(row['涨跌幅(%)'])
        etf_rows += (
            f"<tr><td>{row['ETF名称']}</td>"
            f"<td style='color:{c};font-weight:bold'>{row['涨跌幅(%)']}%</td></tr>"
        )

    stock_rows = ""
    for _, row in data['stocks'].iterrows():
        c = color(row['涨跌幅(%)'])
        stock_rows += (
            f"<tr><td>{row['股票']}</td>"
            f"<td style='color:{c};font-weight:bold'>{row['涨跌幅(%)']}%</td></tr>"
        )

    html = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:Microsoft YaHei, sans-serif;">
        <h2>📊 A股市场速览 - {date_str}</h2>
        <p><b>市场情绪：</b>{data['up_down']}</p>
        <h3>🏛️ 大盘指数</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%;">
            <tr style="background-color:#4472C4;color:white;"><th>指数</th><th>最新价</th><th>涨跌幅</th><th>成交额</th></tr>
            {index_rows}
        </table>
        <h3>🔥 热门行业板块 TOP5</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%;">
            <tr style="background-color:#ED7D31;color:white;"><th>板块名称</th><th>涨跌幅</th></tr>
            {sector_rows}
        </table>
        <h3>📈 热门ETF TOP5</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%;">
            <tr style="background-color:#70AD47;color:white;"><th>ETF名称</th><th>涨跌幅</th></tr>
            {etf_rows}
        </table>
        <h3>🚀 个股涨幅 TOP10</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%;">
            <tr style="background-color:#FFC000;color:white;"><th>股票</th><th>涨跌幅</th></tr>
            {stock_rows}
        </table>
    </body>
    </html>
    """
    return html


def send_email(html_content):
    """发送HTML邮件"""
    password = os.environ.get("EMAIL_PWD")
    if not password:
        print("错误：未设置 EMAIL_PWD 环境变量")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"A股市场速览 - {datetime.now().strftime('%Y-%m-%d')}"
        msg['From'] = SENDER
        msg['To'] = RECEIVER
        part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER, password)
        server.sendmail(SENDER, RECEIVER, msg.as_string())
        server.quit()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 邮件发送成功 -> {RECEIVER}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] A股日报脚本启动")

    if not is_trade_day():
        print("今天非交易日，跳过运行。")
        return

    print("正在抓取市场数据...")
    data = fetch_data()
    if data is None:
        print("数据抓取失败，终止运行。")
        return

    print("正在生成HTML报告...")
    html = build_html(data)

    print("正在发送邮件...")
    send_email(html)

    print("运行完成。")


if __name__ == "__main__":
    main()
