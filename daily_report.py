# -*- coding: utf-8 -*-
"""A股市场每日速览 - 自动化报告 (Sina 数据源版)"""

import akshare as ak
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import traceback
import re

# ========== 配置区 ==========
SENDER = "raomengxiang7@outlook.com"
SMTP_SERVER = "smtp-mail.outlook.com"
SMTP_PORT = 587
PASSWORD = os.environ.get("EMAIL_PWD")
RECEIVER = "raomengxiang7@outlook.com"
# ===========================

def is_trade_day():
    """判断今天是否为交易日（使用新浪接口，全球可访问）"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        trade_df = ak.tool_trade_date_hist_sina()
        trade_dates = trade_df['trade_date'].astype(str).tolist()
        return today in trade_dates
    except Exception:
        wd = datetime.now().weekday()
        return wd < 5

def fetch_index_data():
    """获取大盘指数数据（新浪接口）"""
    idx_map = [
        ('sh000001', '上证指数'),
        ('sz399001', '深证成指'),
        ('sz399006', '创业板指'),
        ('sh000688', '科创50'),
    ]
    results = []
    for symbol, name in idx_map:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            last = df.iloc[-1]
            results.append({
                '指数': name,
                '最新价': last['close'],
                '涨跌幅(%)': round((last['close'] - last['open']) / last['open'] * 100, 2),
                '成交量': last.get('volume', 0),
                '成交额(元)': last.get('amount', 0),
            })
        except Exception as e:
            print(f"  指数 {name} 获取失败: {e}")
    return pd.DataFrame(results)

def fetch_market_sentiment():
    """从个股数据统计涨跌家数（新浪接口）"""
    try:
        df = ak.stock_zh_a_spot()
        up_count = int((df['涨跌幅'] > 0).sum())
        down_count = int((df['涨跌幅'] < 0).sum())
        return f"上涨 {up_count} 家，下跌 {down_count} 家", df
    except Exception as e:
        print(f"市场情绪获取失败: {e}")
        return "数据获取中...", None

def fetch_top_sectors():
    """获取热门行业板块 TOP5"""
    sectors = []
    # 尝试东方财富 - GitHub Actions 可能被墙，但保留尝试
    try:
        sector_df = ak.stock_board_industry_name_em()
        top = sector_df.nlargest(5, '涨跌幅')[['板块名称', '涨跌幅']]
        top.columns = ['板块', '涨跌幅(%)']
        return top
    except Exception:
        print("  东财板块数据不可用")
    return pd.DataFrame(columns=['板块', '涨跌幅(%)'])

def fetch_top_etfs(stock_df):
    """从行情数据中筛选ETF涨幅TOP5"""
    try:
        etf_mask = stock_df['代码'].astype(str).str.match(r'^(51\d{3}|159\d{3}|16\d{3})', na=False)
        etf = stock_df[etf_mask].copy()
        if len(etf) == 0:
            raise ValueError("未找到ETF")
        top = etf.nlargest(5, '涨跌幅')[['名称', '涨跌幅']]
        top.columns = ['ETF名称', '涨跌幅(%)']
        return top
    except Exception as e:
        print(f"  ETF筛选失败: {e}")
    return pd.DataFrame(columns=['ETF名称', '涨跌幅(%)'])

def fetch_top_stocks(stock_df):
    """获取个股涨幅TOP10"""
    try:
        cond = (
            ~stock_df['名称'].str.contains('ST|退', na=False) &
            (stock_df['最新价'] > 0) &
            (stock_df['涨跌幅'] < 20)
        )
        valid = stock_df[cond].copy()
        top = valid.nlargest(10, '涨跌幅')[['名称', '涨跌幅']]
        top.columns = ['股票', '涨跌幅(%)']
        return top
    except Exception as e:
        print(f"个股筛选失败: {e}")
    return pd.DataFrame(columns=['股票', '涨跌幅(%)'])

def build_html(index_df, up_down, sectors, etf, stocks):
    """构建HTML邮件内容"""
    date_str = datetime.now().strftime("%Y年%m月%d日")

    def color(val):
        try:
            v = float(val)
        except Exception:
            return 'black'
        return 'red' if v > 0 else ('green' if v < 0 else 'gray')

    def make_table(headers, rows, header_color):
        if len(rows) == 0:
            return "<p>暂无数据</p>"
        hdr = "".join(f"<th>{h}</th>" for h in headers)
        body = ""
        for row in rows:
            cells = "".join(f"<td style='color:{color(v)}'>{v}</td>" for v in row)
            body += f"<tr>{cells}</tr>"
        return (f"<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse; width:100%;'>"
                f"<tr style='background-color:{header_color};color:white;'>{hdr}</tr>{body}</table>")

    index_rows = []
    for _, r in index_df.iterrows():
        index_rows.append((r['指数'], r['最新价'], f"{r['涨跌幅(%)']}%", r['成交额(元)']))
    index_table = make_table(['指数', '最新价', '涨跌幅', '成交额'], index_rows, '#4472C4')

    sector_rows = []
    for _, r in sectors.iterrows():
        sector_rows.append((r['板块'], f"{r['涨跌幅(%)']}%"))
    sector_table = make_table(['板块名称', '涨跌幅'], sector_rows, '#ED7D31')

    etf_rows = []
    for _, r in etf.iterrows():
        etf_rows.append((r['ETF名称'], f"{r['涨跌幅(%)']}%"))
    etf_table = make_table(['ETF名称', '涨跌幅'], etf_rows, '#70AD47')

    stock_rows = []
    for _, r in stocks.iterrows():
        stock_rows.append((r['股票'], f"{r['涨跌幅(%)']}%"))
    stock_table = make_table(['股票', '涨跌幅'], stock_rows, '#FFC000')

    html = f"""<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Microsoft YaHei, sans-serif;">
    <h2>📊 A股市场速览 - {date_str}</h2>
    <p><b>市场情绪：</b>{up_down}</p>
    <h3>🏛️ 大盘指数</h3>{index_table}
    <h3>🔥 热门行业板块 TOP5</h3>{sector_table}
    <h3>📈 热门ETF TOP5</h3>{etf_table}
    <h3>🚀 个股涨幅 TOP10</h3>{stock_table}
</body></html>"""
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
        print(f"邮件发送成功 -> {RECEIVER}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        traceback.print_exc()
        return False

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] A股日报脚本启动")
    if not is_trade_day() and os.environ.get("FORCE_RUN") != "true":
        print("今天非交易日，跳过运行。")
        return

    print("正在抓取市场数据...")
    index_df = fetch_index_data()
    up_down, stock_df = fetch_market_sentiment()
    sectors = fetch_top_sectors()
    etf = fetch_top_etfs(stock_df) if stock_df is not None else pd.DataFrame()
    stocks = fetch_top_stocks(stock_df) if stock_df is not None else pd.DataFrame()
    print(f"数据获取完成: 指数={len(index_df)}, 板块={len(sectors)}, ETF={len(etf)}, 个股={len(stocks)}")

    print("正在生成HTML报告...")
    html = build_html(index_df, up_down, sectors, etf, stocks)
    send_email(html)
    print("运行完成。")

if __name__ == "__main__":
    main()