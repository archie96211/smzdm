# SMZDM Bot — 什么值得买好价监控桌面机器人

> Windows 桌面常驻工具，实时监控什么值得买好价商品，关键词筛选后自动推送到钉钉、微信和 WxPusher。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://github.com/archie96211/smzdm)

SMZDM Bot 是一个 Windows 桌面端的好价监控机器人。它定时检索什么值得买 API，按关键词和价格区间筛选商品，通过钉钉机器人 ActionCard、微信或 WxPusher 实时推送新增好价信息。自带 Web 管理界面，支持系统托盘常驻，适合 Windows Server 和个人电脑 7x24 小时运行。

## 项目特点

与现有的什么值得买监控项目相比，SMZDM Bot 提供：

- **桌面 Web 管理界面** — React 19 + shadcn/ui，可视化配置监控方案、关键词和通知渠道
- **微信扫码推送** — 基于微信桥接，扫码绑定后直接推送图文消息到微信好友或群
- **钉钉 ActionCard 图文通知** — 商品图片、标题、价格、时间一体化展示
- **WxPusher 推送** — 基于 [WxPusher](https://wxpusher.zjiecode.com/) 开源平台，支持 Markdown 图文消息，推送到微信/APP，无需保活
- **多方案并行监控** — 每个方案独立关键词、价格区间、通知渠道
- **Windows 系统托盘** — 后台常驻，双击 EXE 即用，无需命令行

## 技术架构

- 后端：Python FastAPI + SQLite
- 前端：React 19 + Vite 7 + shadcn/ui + Tailwind CSS v4 + TanStack Query
- 桌面壳：pystray 托盘 + 默认浏览器管理页
- 可选内置窗口：PyWebView，需要时用 `--webview` 启用
- 打包：PyInstaller `--onedir`，输出 `dist/smzdm_monitor/smzdm_monitor.exe`
- 微信桥接：Go 版本 WeChat bridge，基于 `fastclaw-ai/weclaw`
- WxPusher 推送：基于 [WxPusher](https://wxpusher.zjiecode.com/) 开源消息推送平台

默认使用浏览器打开管理页，是为了避免低配 Windows Server 或缺少 WebView2 的环境里出现原生窗口卡死。托盘仍然保留，用于打开管理页、显示内置窗口、查看日志和退出程序。

## 工作机制

- 每个监控方案独立启用/停用，程序启动后自动监控所有已启用方案。
- 新建方案后，首次抓到的历史商品只写入数据库，不会批量推送；后续只有新增商品才会推送。
- 新建方案时，如果已经配置钉钉或微信，会发送一条“方案已配置”通知。
- 商品通知包含 SMZDM 原始时间和本机发送时间。
- 钉钉图片使用公网图片地址，微信图片通过本机缓存文件发送，不依赖公网 IP。
- 监控结果只保留「发现/好价」频道（`article_channel_id == "2"`），文章和好文不会混入。

## 功能

- 多方案监控
- 单方案启用和停用
- 关键词管理
- 价格区间过滤
- 商品历史记录
- 钉钉机器人 ActionCard 通知
- WxPusher Markdown 图文通知（支持全局/方案级配置）
- 微信扫码绑定账号（单账号模式）
- 支持选择微信接收会话
- 微信 session 过期自动检测，状态实时同步前端
- 微信发送失败时自动通过钉钉告警提醒重新扫码
- 商品图片本地缓存
- 日志按日期自动轮转
- Windows 托盘常驻
- PyInstaller 文件夹版 EXE
- shadcn/ui 可折叠侧边栏布局
- 亮色/暗色主题切换
- Toast 通知（sonner）
- 骨架屏加载态

## 技术栈与开源依赖

本项目基于以下开源项目构建：

### 后端

- [FastAPI](https://fastapi.tiangolo.com/) — Python Web API 框架
- [Uvicorn](https://www.uvicorn.org/) — ASGI 服务器
- [PyInstaller](https://pyinstaller.org/) — Python 打包为 Windows EXE
- [pystray](https://github.com/moses-palmer/pystray) — 系统托盘常驻

### 前端

- [React 19](https://react.dev/) — UI 库
- [Vite 7](https://vitejs.dev/) — 前端构建工具
- [shadcn/ui](https://ui.shadcn.com/) — UI 组件体系（基于 Radix UI + Tailwind CSS）
- [Radix UI](https://www.radix-ui.com/) — 无样式可访问性组件原语
- [Tailwind CSS v4](https://tailwindcss.com/) — 原子化 CSS 框架
- [TanStack Query](https://tanstack.com/query) — 异步状态管理
- [Lucide React](https://lucide.dev/) — 图标库
- [sonner](https://sonner.emilkowal.ski/) — Toast 通知

### 微信桥接

- [fastclaw-ai/weclaw](https://github.com/fastclaw-ai/weclaw) — 微信桥接核心，提供 WeChat 登录、消息监听和发送能力

### WxPusher 推送

- [WxPusher](https://wxpusher.zjiecode.com/) — 开源实时消息推送平台，支持微信/APP/桌面多端触达
- [WxPusher 文档](https://wxpusher.zjiecode.com/docs/) — API 接入指南
- [WxPusher GitHub](https://github.com/wxpusher/wxpusher-client) — 客户端开源仓库

## 运行数据

EXE 运行后会在程序同目录创建运行数据，不会把开发目录里的旧数据库、旧图片缓存或 webhook secret 打进发布包。

典型目录结构：

```text
dist/smzdm_monitor/
  smzdm_monitor.exe
  _internal/
  data/
    smzdm_monitor.db
    images/
    wechat_bridge/
      conversations.json
  logs/
    smzdm_monitor.log
    smzdm_monitor.log.YYYY-MM-DD
    wechat_bridge-YYYY-MM-DD.log
```

说明：

- `data/smzdm_monitor.db` 是 SQLite 数据库。
- `data/images/` 是商品图片缓存。
- `data/wechat_bridge/` 保存微信会话记录。
- `logs/smzdm_monitor.log` 是主程序日志，按天轮转。
- `logs/wechat_bridge-YYYY-MM-DD.log` 是微信桥接日志，按日期生成。

## 开发环境

安装 Python 依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
```

安装前端依赖：

```powershell
npm.cmd install
```

微信桥接需要 Go。当前项目构建时使用 Go toolchain `1.25.0`：

```powershell
$env:GOTOOLCHAIN = "go1.25.0"
```

## 开发运行

构建前端：

```powershell
npm.cmd run build
```

启动桌面版。默认会打开浏览器管理页，并启动托盘：

```powershell
.\.venv\Scripts\python.exe desktop_app.py
```

显式使用浏览器模式：

```powershell
.\.venv\Scripts\python.exe desktop_app.py --browser
```

强制使用 PyWebView 内置窗口：

```powershell
.\.venv\Scripts\python.exe desktop_app.py --webview
```

只启动后端服务：

```powershell
.\.venv\Scripts\python.exe start.py
```

## 打包 EXE

完整构建：

```powershell
.\.venv\Scripts\python.exe scripts\build_exe.py
```

构建产物：

```text
dist/smzdm_monitor/smzdm_monitor.exe
```

发布时复制整个 `dist/smzdm_monitor/` 文件夹即可，不要只复制单个 EXE。

构建脚本会处理：

- Python 依赖
- React 前端构建
- 微信 Go bridge 构建
- 图标生成
- PyInstaller 打包

常用跳过参数：

```powershell
.\.venv\Scripts\python.exe scripts\build_exe.py --skip-python-deps --skip-npm-install --skip-frontend --skip-icon
```

如果只想跳过微信桥接构建：

```powershell
.\.venv\Scripts\python.exe scripts\build_exe.py --skip-wechat-bridge
```

`scripts/build_windows.bat` 仍然保留，作用是转调 `scripts/build_exe.py`。

## 微信通知

微信通知通过 `wechat_bridge/smzdm_wechat_bridge.exe` 实现，基于微信 ClawBot（iLink Bot）API。桌面程序启动时会自动拉起微信桥接服务，默认只监听本机。

### ClawBot 认证机制

微信 ClawBot 使用两层认证令牌：

- **bot_token** — 主认证令牌，有效期较长（数天至数周），用于登录和 `getupdates` 轮询。
- **context_token** — 会话上下文令牌，用于 `sendmessage` 发送消息。**有效期约 1 小时**，从用户最后一次与 bot 交互（发送消息）开始计算。

### context_token 过期机制（实测数据）

通过定时发送测试消息（每 30 分钟一次），实测 `context_token` 的过期行为：

| 时间点 | 距用户最后交互 | 结果 |
|--------|--------------|------|
| 20:13 | 6 分钟 | ✅ 成功 |
| 20:43 | 36 分钟 | ✅ 成功 |
| 21:14 | 67 分钟 | ❌ 失败 `ret=-2` |

用户在 23:38 重新给 bot 发了一条消息后恢复：

| 时间点 | 距用户最后交互 | 结果 |
|--------|--------------|------|
| 23:45 | 7 分钟 | ✅ 成功 |
| 00:15 | 37 分钟 | ✅ 成功 |
| 00:45 | 67 分钟 | ✅ 成功 |
| 01:15 | 97 分钟 | ❌ 失败 `ret=-2` |

**结论**：`context_token` 在用户最后一次与 bot 交互后约 **1 小时**过期。过期后发送消息会返回 `ret=-2` 错误。

**唯一恢复方式**：用户用微信给 bot 发一条消息（任意内容），桥接服务通过 `getupdates` 轮询获取新消息后会刷新 `context_token`。程序无法自动刷新，必须由用户主动交互。

### 使用流程

1. 打开管理页。
2. 进入微信绑定。
3. 扫码绑定微信账号。
4. 用接收通知的微信好友或微信群先给机器人发一条消息。
5. 回到管理页刷新微信会话。
6. 在方案里启用微信通知，并选择接收会话。
7. 保存方案。

### 关键限制

- 微信发送推荐使用 `conversation_id`，它包含账号和会话上下文。
- 好友或群必须先给机器人发消息，桥接服务才能记录可回复的会话。
- **context_token 约 1 小时过期**：如果用户超过 1 小时未与 bot 交互，后续消息发送会失败（`ret=-2`），需要用户重新给 bot 发一条消息才能恢复。
- 一个方案可以选择一个微信接收会话。
- 单账号模式：新扫码登录会自动清理旧账号，确保只有一个微信账号在线。
- 微信 session 过期或发送失败时，桥接服务会自动更新账号状态，前端实时显示。
- 微信发送失败时，如果配置了钉钉，会自动通过钉钉发送一条告警提醒重新扫码。
- 微信商品图使用本地缓存文件 `media_path` 发送，不需要公网 IP。

> **推荐**：如果需要 7x24 小时无人值守稳定推送，建议使用 WxPusher 通知渠道。WxPusher 是纯 HTTP API 调用，无 token 过期问题，无需用户保活交互。

微信桥接本地接口：

```text
127.0.0.1:18012
```

主要接口：

```text
GET  /api/wechat/account
GET  /api/wechat/conversations
POST /api/wechat/login/start
GET  /api/wechat/login/status/{id}
POST /api/wechat/login/cancel/{id}
POST /api/wechat/send
```

正常情况下不需要直接调用这些接口，前端已经封装。

## 钉钉通知

钉钉机器人使用 ActionCard 消息。

钉钉图片显示逻辑：

1. 程序把商品图缓存到 `data/images/`。
2. 程序生成 `http://公网IP:8000/images/文件名`。
3. 钉钉服务器访问这个公网 URL 获取图片。

因此，钉钉显示图片需要满足：

- 腾讯云安全组放行 TCP `8000`。
- Windows 防火墙放行 TCP `8000`。
- 公网访问 `http://公网IP:8000/images/文件名` 能直接看到图片。

公网 IP 会自动识别腾讯云 metadata，也可以手动指定：

```powershell
$env:SMZDM_PUBLIC_IP = "你的公网IP"
```

或：

```powershell
$env:SMZDM_IMAGE_SERVER_HOST = "你的公网IP"
$env:SMZDM_IMAGE_SERVER_PORT = "8000"
```

注意：微信图片不走这个公网 URL，只有钉钉和 WxPusher 需要公网图片访问。

## WxPusher 通知

[WxPusher](https://wxpusher.zjiecode.com/) 是一个开源的实时消息推送平台，支持通过微信公众号、APP、桌面客户端多端接收消息。与微信桥接不同，WxPusher 是纯 HTTP API 调用，无需保活、无 session 过期问题。

使用流程：

1. 在 [WxPusher 管理后台](https://wxpusher.zjiecode.com/admin/) 创建应用，获取 `AppToken`。
2. 扫码关注应用，获取 `UID`。
3. 打开管理页，点击右上角 WxPusher 按钮（纸飞机图标）。
4. 填入 AppToken 和 UID，点击「发送测试」验证。
5. 保存配置。
6. 新建方案时如果全局 WxPusher 已配置，会自动启用 WxPusher 通知。
7. 也可在方案编辑中单独开启或自定义 WxPusher 配置。

特点：

- 支持 Markdown 格式（`contentType=3`），商品标题、价格、图片一体化展示。
- 图片通过公网 URL 引用（`![商品图片](http://公网IP:18080/images/文件名)`），与钉钉共用同一套图片缓存和公网 IP 机制。
- WxPusher API 不支持图片上传，只接受 URL 引用。
- 消息可附带原文链接（`url` 字段），用户点击可跳转到什么值得买商品页。
- 支持全局配置和方案级配置覆盖，与钉钉逻辑一致。
- 无需保活、无 session 过期问题，比微信桥接更稳定。

WxPusher API：

```text
POST https://wxpusher.zjiecode.com/api/send/message
```

请求示例：

```json
{
  "appToken": "AT_xxx",
  "content": "### 商品标题\n\n- **价格**: ¥99\n![商品图片](http://公网IP:18080/images/xxx.jpg)",
  "contentType": 3,
  "uids": ["UID_xxx"],
  "summary": "商品标题 ¥99",
  "url": "https://www.smzdm.com/p/xxx"
}
```

## 端口和安全

默认端口：

```text
管理服务和图片服务：18080
微信桥接服务：127.0.0.1:18012
```

后端默认绑定：

```text
127.0.0.1:18080
```

公网访问限制：

- `/images/` 允许公网访问，用于钉钉取图。
- 管理页面和管理 API 默认只允许本机访问（127.0.0.1）。
- 如需临时开放管理 API，可设置 `SMZDM_ALLOW_PUBLIC_API=1`，不建议在公网长期使用。

## 环境变量

运行目录：

```text
SMZDM_DATA_DIR          指定 data 目录
SMZDM_LOG_DIR           指定 logs 目录
LOG_FILE                指定主日志文件
```

服务端口：

```text
SMZDM_PORT              桌面入口使用的服务端口，默认 18080
SMZDM_BIND_HOST         后端绑定地址，默认 127.0.0.1
PORT                    后端进程内部端口
HOST                    后端进程内部绑定地址
```

桌面模式：

```text
SMZDM_BROWSER_MODE      设置为 1 时固定使用浏览器模式
SMZDM_SKIP_WEBVIEW2_CHECK 设置为 1 时跳过 WebView2 检测
SMZDM_WEBVIEW_LOAD_TIMEOUT PyWebView 加载等待秒数，默认 18
```

监控行为：

```text
SMZDM_NO_AUTO_MONITOR   设置为 1 时不自动开始监控
SMZDM_AUTO_START_DELAY  启动后延迟开始监控秒数，默认 4
SMZDM_MONITOR_CONCURRENCY 抓取并发数，默认 3
SMZDM_API_BASE_URL      SMZDM API 地址
```

图片公网地址：

```text
SMZDM_PUBLIC_IP
SMZDM_IMAGE_SERVER_HOST
SMZDM_IMAGE_SERVER_PORT
```

日志：

```text
LOG_LEVEL               默认 INFO
LOG_BACKUP_DAYS         主日志保留天数，默认 14
```

公网 API：

```text
SMZDM_ALLOW_PUBLIC_API  设置为 1 时允许公网访问管理 API
```

## API 概览

方案：

```text
GET    /api/schemes
GET    /api/schemes/{scheme_id}
POST   /api/schemes
PUT    /api/schemes/{scheme_id}
DELETE /api/schemes/{scheme_id}
POST   /api/schemes/{scheme_id}/restart
```

关键词：

```text
GET    /api/schemes/{scheme_id}/keywords
POST   /api/schemes/{scheme_id}/keywords
PUT    /api/keywords/{keyword_id}
DELETE /api/keywords/{keyword_id}
```

商品历史：

```text
GET /api/schemes/{scheme_id}/products
```

状态和配置：

```text
GET /api/health
GET /api/monitor/status
GET /api/system/info
GET /api/global-settings
PUT /api/global-settings
```

测试通知：

```text
POST /api/test-webhook
POST /api/test-wechat
POST /api/test-wxpusher
```

微信：

```text
GET  /api/wechat/status
GET  /api/wechat/account
POST /api/wechat/reload
GET  /api/wechat/conversations
POST /api/wechat/login/start
GET  /api/wechat/login/status/{login_id}
POST /api/wechat/login/cancel/{login_id}
```

## 项目结构

```text
desktop_app.py             桌面入口，启动后端、托盘和管理页
start.py                   只运行 FastAPI 后端的开发入口
requirements.txt           Python 运行依赖
package.json               前端依赖和 npm scripts（npm 要求在根目录）
package-lock.json          前端依赖锁定文件
vite.config.js             Vite 配置（Tailwind 插件、@ 别名、构建输出）
jsconfig.json              JS 路径别名配置（@/* → frontend/src/*）
LICENSE                    MIT 开源许可证

scripts/                   构建脚本目录
  build_exe.py             Windows EXE 一键打包
  build_wechat_bridge.py   单独构建微信桥接 EXE
  build_windows.bat        Windows 构建批处理
  smzdm_monitor.spec       PyInstaller 配置
  create_icon.py           图标生成脚本

src/runtime.py             路径、端口、日志配置
src/web_server.py          FastAPI API 和静态前端服务
src/monitor.py             SMZDM 监控核心
src/database.py            SQLite 数据库管理
src/dingtalk_notifier.py   钉钉发送模块
src/wxpusher_notifier.py   WxPusher 发送模块
src/wechat_notifier.py     微信发送客户端
src/wechat_bridge_manager.py 微信桥接进程管理
src/image_cache.py         图片缓存服务
src/network_utils.py       公网 IP 和地址判断

frontend/                  React 19 + Vite 7 + shadcn/ui 前端源码
  frontend/src/main.jsx     React 入口（QueryClientProvider + Toaster）
  frontend/src/App.jsx      主组件（Sidebar 布局 + 详情面板）
  frontend/src/index.css    Tailwind CSS v4 + 主题变量
  frontend/src/helpers/     API hooks 和工具函数
  frontend/src/components/  shadcn/ui 组件和业务弹窗（含 WxPusherModal）
static/                    前端构建产物
wechat_bridge/             Go 微信桥接服务（基于 fastclaw-ai/weclaw）
assets/                    图标资源
data/                      开发期运行数据（gitignore）
logs/                      开发期日志（gitignore）
```

> **关于根目录配置文件**：`package.json`、`vite.config.js`、`jsconfig.json` 等 JSON/JS 文件位于根目录是全栈项目的标准布局——npm 和 Vite 要求配置文件在项目根目录，无法移动到子目录。

## 常见问题

### 服务器拉不起原生窗口

这是正常行为。默认使用浏览器管理页，适合 Windows Server 和 2 核 4G 机器。需要内置窗口时再使用：

```powershell
.\.venv\Scripts\python.exe desktop_app.py --webview
```

### 打开 EXE 后有两个 smzdm_monitor.exe 进程

这是正常现象。一个是桌面壳和托盘，另一个是后端服务进程。这样可以降低窗口卡死对后端服务的影响。

### 钉钉图片是灰框

优先检查：

1. `data/images/` 是否生成了图片。
2. 通知里的图片 URL 是否是 `http://公网IP:18080/images/...`。
3. 腾讯云安全组是否放行 TCP `18080`。
4. Windows 防火墙是否放行 TCP `18080`。
5. 从公网浏览器访问图片 URL 是否能打开。

### 微信发不出消息

优先检查：

1. 是否已经扫码绑定微信账号。
2. 接收通知的好友或群是否先给机器人发过消息。
3. 前端方案里是否选择了微信接收会话。
4. `logs/wechat_bridge-YYYY-MM-DD.log` 是否有发送错误。
5. `logs/smzdm_monitor.log` 是否有桥接服务错误。

### 微信不显示商品图

微信图片使用本地缓存文件发送，不走公网 IP。优先检查：

1. `data/images/` 是否有对应图片文件。
2. 微信桥接日志里是否有 `media_path` 或文件读取错误。
3. 图片文件是否仍存在，且桥接进程有权限读取。

### 新建方案后没有推送历史商品

这是设计行为。新建方案首次抓取只缓存历史数据，避免一次性推送大量旧商品。保存方案时只会发送一条“方案已配置”通知，之后有新增商品才推送。

### 搜索结果里混入了文章

SMZDM API 不支持频道过滤参数，返回结果包含好价、文章、好文等混合内容。代码已在客户端过滤只保留 `article_channel_id == "2"`（发现/好价）。如果仍出现文章内容，检查 `src/monitor.py` 的 `fetch_products()` 方法中的过滤逻辑是否被修改。

## 验证命令

Python 静态检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile src\runtime.py src\monitor.py src\web_server.py src\wechat_bridge_manager.py src\wechat_notifier.py src\image_cache.py desktop_app.py scripts\build_exe.py
```

前端构建：

```powershell
npm.cmd run build
```

微信桥接测试：

```powershell
cd wechat_bridge
$env:GOTOOLCHAIN = "go1.25.0"
go test ./...
```

快速打包验证：

```powershell
.\.venv\Scripts\python.exe scripts\build_exe.py --skip-python-deps --skip-npm-install --skip-frontend --skip-icon
```

---

最后更新：2026-06-29（v2.2 新增 WxPusher 推送渠道）
