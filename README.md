# QQ华夏 充值活动监控

定时抓取 QQ华夏官网，发现新充值/限时活动后推送通知。部署在 GitHub Actions，免费、不用自己挂机。

## 监控源

1. **官网新闻列表** `qqhx.qq.com/webplat/info/.../list_1.shtml`
   标题命中 `充值 / 回馈 / 限时充 / 送元宝 / 送点券 / 返利` 等关键词即视为充值活动。
2. **主页 main.shtml 全页扫描**
   提取所有 `qqhx.qq.com/cp/...` 活动页链接，出现新路径即告警。

> 说明：主页顶部轮播 `#roll_adbtn` 的真实链接由 JS 动态加载（静态 HTML 里是 `href="#"`），纯 requests 抓不到。充值活动一般会同步发一条新闻公告，所以新闻列表监控是主力；轮播位如想 100% 覆盖，需上 Playwright（见末尾）。

## 部署步骤

### 1. 新建仓库
GitHub 上 New Repository，名字随便，比如 `qq-hx-monitor`，**Private** 也行。把本目录所有文件推上去：

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的用户名>/qq-hx-monitor.git
git push -u origin main
```

### 2. 配置推送渠道（至少选一个）
进仓库 **Settings → Secrets and variables → Actions → New repository secret**，按下表加 Secret：

| 渠道 | Secret 名 | 获取方式 |
|---|---|---|
| **Server酱（微信推送，推荐）** | `SERVERCHAN_KEY` | 打开 https://sct.ftqq.com/ 微信扫码登录，复制 SendKey |
| **企业微信群机器人** | `WECOM_WEBHOOK` | 企业微信群 → 群设置 → 群机器人 → 添加，复制 Webhook 地址 |
| **Bark（iOS）** | `BARK_KEY` | App Store 装 Bark，打开 App 复制 Key |
| **Telegram Bot** | `TG_BOT_TOKEN` + `TG_CHAT_ID` | 找 @BotFather 建 Bot 拿 token；找 @userinfobot 拿自己 chat_id |

### 3. 开启 Actions
推完代码后进仓库 **Actions** 标签页，点 **I understand my workflows, go ahead and enable them**。

工作流是 `.github/workflows/monitor.yml`，默认每 **30 分钟**跑一次。也可以在 Actions 页面手动点 **Run workflow** 立即跑一次。

### 4. 首次运行
第一次跑只记录基线，不推送。从第二次开始，只有检测到**新**充值活动才推送。

## 自定义

- **轮询频率**：改 `.github/workflows/monitor.yml` 里的 `cron`，默认 `*/30 * * * *`（每30分钟）。GitHub Actions 免费额度 2000 分钟/月，30分钟一次一天48次，一个月约 36 分钟，随便用。
- **关键词**：改 `monitor.py` 里的 `NEWS_KEYWORDS`。
- **想监控别的页面**：加 URL 到 `NEWS_URL` 列表，仿 `parse_news` 写解析。

## 文件说明

```
qq-hx-monitor/
├── monitor.py                  # 主脚本（纯标准库，无依赖）
├── state.json                  # 运行后自动生成，记录已见过的活动
├── requirements.txt            # 占位（无第三方依赖）
└── .github/workflows/monitor.yml   # GitHub Actions 工作流
```
