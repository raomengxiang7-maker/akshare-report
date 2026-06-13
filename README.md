# A股市场每日速览

自动抓取 A 股市场数据，生成 HTML 邮件报告并发送到指定邮箱。

## 功能

- 每日收盘后自动运行（周一到五，北京时间 ~15:30）
- 抓取：大盘指数、行业板块、ETF、个股涨幅排名
- 发送 HTML 格式化邮件到你的邮箱

## 配置

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加：

| Key | Value |
|-----|-------|
| `EMAIL_PWD` | Outlook 邮箱的 SMTP 授权码 |

## 手动触发

在 GitHub Actions 页面选择 **A股每日报告** → **Run workflow** 即可手动运行。

## 技术栈

- Python 3.13
- [akshare](https://github.com/akfamily/akshare) - A股数据接口
- GitHub Actions - 定时调度
