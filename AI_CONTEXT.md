# SMZDM Bot 项目 AI 交接文档

本文档面向后续接手本仓库的 AI 工具或开发者，用于快速理解项目架构、核心数据流、运行/构建方式和高风险修改点；它不替代 `README.md`，而是作为开发交接入口。

## 1. 一句话概览

SMZDM Bot 是一个 Windows 桌面常驻工具：后台定时检索什么值得买好价 API，根据监控方案和关键词筛选商品（仅保留「发现/好价」频道），记录到 SQLite，并通过钉钉机器人或本地微信桥接服务推送通知。

## 2. 当前项目形态

- **后端服务**：Python FastAPI，提供 `/api/*` 管理接口，使用 SQLite 持久化。
- **监控引擎**：异步轮询 SMZDM API，按方案和关键词创建后台任务，客户端过滤只保留 `article_channel_id == "2"`（发现/好价）的结果。
- **桌面壳**：`desktop_app.py` 管理后端子进程、系统托盘、浏览器模式或可选 PyWebView 窗口。
- **前端界面**：React 19 + Vite 7 单页应用，使用 shadcn/ui 组件体系 + Tailwind CSS v4 + TanStack Query 管理异步状态，开发源码在 `frontend/`，构建后由后端从 `static/` 提供。
- **通知渠道**：钉钉 Webhook + ActionCard，微信通过 Go 写的 `wechat_bridge` 本地 HTTP 服务发送。
- **打包方式**：`scripts/build_exe.py` 调用 npm、Go、PyInstaller，输出 Windows onedir 目录。

## 3. 技术栈速查

| 层级 | 技术/文件 | 职责 |
|---|---|---|
| 桌面入口 | `desktop_app.py` | 启动后端、托盘、浏览器/PyWebView、退出清理 |
| 后端入口 | `start.py` | 无桌面壳启动 FastAPI + Uvicorn |
| Web API | `src/web_server.py` | REST API、静态资源、图片目录、微信桥接代理、生命周期事件 |
| 监控核心 | `src/monitor.py` | 拉取商品、频道过滤（仅好价）、价格过滤、入库去重、发送通知、任务管理 |
| 数据库 | `src/database.py` | SQLite schema、CRUD、历史、通知日志、全局设置、SQL 注入防护（列白名单） |
| 运行时路径 | `src/runtime.py` | data/log/static/database 路径、端口、日志配置 |
| 钉钉通知 | `src/dingtalk_notifier.py` | 钉钉 webhook、签名、ActionCard/markdown/link/text |
| 微信通知客户端 | `src/wechat_notifier.py` | Python 侧调用本地微信桥接 HTTP API |
| 微信桥接管理 | `src/wechat_bridge_manager.py` | 启停 Go bridge、健康检查、请求代理 |
| 微信桥接服务 | `wechat_bridge/main.go` | weclaw 账号登录/监听/会话记录/消息发送 |
| 前端入口 | `frontend/src/main.jsx` | React 挂载、QueryClientProvider、Toaster（sonner） |
| 前端主组件 | `frontend/src/App.jsx` | Sidebar 布局、方案列表、详情面板、指标卡片、通知配置 |
| 前端 API 层 | `frontend/src/helpers/api.js` | TanStack Query hooks 封装所有 API 调用 |
| 前端 UI 组件 | `frontend/src/components/ui/*.jsx` | shadcn/ui 组件（button、card、sidebar、dialog、badge 等 14 个） |
| 前端弹窗 | `frontend/src/components/modals/*.jsx` | SchemeModal、KeywordModal、SettingsModal、WechatModal |
| 前端样式 | `frontend/src/index.css` | Tailwind CSS v4 导入 + shadcn/ui 主题变量（亮/暗） |
| 前端工具 | `frontend/src/helpers/utils.js` | `cn()` 类名合并工具（clsx + tailwind-merge） |
| 构建 | `scripts/build_exe.py`、`scripts/smzdm_monitor.spec` | 前端构建、Go bridge 构建、图标生成、PyInstaller 打包 |

## 4. 目录地图

```text
smzdm/
├── desktop_app.py              # 桌面版主入口
├── start.py                    # 后端服务入口
├── requirements.txt            # Python 运行依赖
├── package.json                # 前端依赖和 npm scripts
├── vite.config.js              # Vite 配置（Tailwind 插件、@ 别名、构建输出）
├── jsconfig.json               # JS 路径别名配置（@/* → frontend/src/*）
├── scripts/
│   ├── build_exe.py            # 一键打包 Windows EXE
│   ├── build_wechat_bridge.py  # 单独构建微信桥接 EXE
│   ├── build_windows.bat       # Windows 构建脚本
│   ├── smzdm_monitor.spec      # PyInstaller 配置
│   └── create_icon.py          # 生成 assets/icon.ico
├── src/
│   ├── web_server.py           # FastAPI 应用和 API 路由
│   ├── monitor.py              # 核心监控逻辑（含频道过滤）
│   ├── database.py             # SQLite 管理（含 SQL 注入防护）
│   ├── runtime.py              # 运行路径/端口/日志
│   ├── dingtalk_notifier.py    # 钉钉通知
│   ├── wechat_notifier.py      # Python 调用微信桥接
│   ├── wechat_bridge_manager.py# 管理 Go bridge 进程
│   ├── image_cache.py          # 商品图本地缓存和图片 URL（仅异步）
│   ├── network_utils.py        # 公网 IP / host 判断工具
│   └── haojia_search.py        # 命令行搜索辅助脚本
├── frontend/
│   ├── index.html
│   └── src/
│       ├── main.jsx            # React 入点（QueryClientProvider + Toaster）
│       ├── App.jsx             # 主应用组件（Sidebar 布局 + 详情面板）
│       ├── index.css           # Tailwind CSS v4 + shadcn/ui 主题变量
│       ├── helpers/
│       │   ├── api.js          # TanStack Query hooks（所有 API 交互）
│       │   └── utils.js        # cn() 类名合并工具
│       └── components/
│           ├── ui/             # shadcn/ui 基础组件（14 个）
│           │   ├── button.jsx
│           │   ├── card.jsx
│           │   ├── input.jsx
│           │   ├── label.jsx
│           │   ├── switch.jsx
│           │   ├── dialog.jsx
│           │   ├── badge.jsx
│           │   ├── select.jsx
│           │   ├── separator.jsx
│           │   ├── sidebar.jsx     # 可折叠侧边栏体系
│           │   ├── tooltip.jsx
│           │   ├── skeleton.jsx
│           │   └── scroll-area.jsx
│           └── modals/         # 业务弹窗
│               ├── SchemeModal.jsx
│               ├── KeywordModal.jsx
│               ├── SettingsModal.jsx
│               └── WechatModal.jsx
├── static/                     # 前端构建产物，由 FastAPI 提供
├── wechat_bridge/
│   ├── main.go                 # Go bridge HTTP 服务
│   ├── go.mod
│   └── README.md
├── data/                       # 运行时数据库、图片缓存，gitignore
└── logs/                       # 运行日志，gitignore
```

## 5. 核心运行流程

### 5.1 桌面版启动

1. 用户运行 `desktop_app.py` 或打包后的 `smzdm_monitor.exe`。
2. `DesktopController` 初始化运行目录、日志、host/port 和 UI 模式。
3. 桌面壳以子进程方式启动后端：实际后端入口是 `start.py`。
4. 桌面壳轮询 `/api/health` 等待后端可用。
5. 启动 `pystray` 托盘菜单。
6. 默认打开浏览器管理界面；如选择嵌入模式，则使用 PyWebView/WebView2。
7. 用户关闭窗口时，桌面壳会保持托盘常驻；退出时会停止后端子进程。

### 5.2 后端服务启动

1. `start.py` 调用 `runtime.ensure_runtime_dirs()` 创建数据、日志、图片目录。
2. `runtime.configure_logging()` 配置控制台和按天轮转日志。
3. `web_server.configure_runtime(host, port, auto_start=True)` 设置服务地址和自动监控行为。
4. Uvicorn 启动 `src.web_server.app`。
5. `web_server.py` 模块级初始化：`DingTalkNotifier`、`SMZDMMonitor`（接收共享 notifier）、`WeChatBridgeManager`。
6. FastAPI startup 中初始化图片服务配置、尝试启动微信桥接、延迟启动监控任务。
7. FastAPI shutdown 中停止监控、关闭通知客户端、停止微信桥接。

## 6. 监控数据流

1. **用户创建方案**：前端通过 TanStack Query mutation 调用 `/api/schemes`，后端写入 `monitor_schemes`，并创建初始关键词。
2. **用户配置关键词**：关键词包含 `keyword`、分类/品牌/商城 ID、排序方式、最低/最高价格。
3. **启动监控**：`SMZDMMonitor.start_monitoring()` 获取所有启用方案，为每个方案启动 `monitor_scheme()`。
4. **轮询关键词**：每个方案按 `refresh_interval` 循环，遍历该方案下的关键词。
5. **请求 SMZDM API**：`fetch_products()` 调用 `SMZDM_API_BASE_URL`，默认 `https://api.smzdm.com/v1/list`。
6. **频道过滤**：API 返回混合频道结果，代码在客户端过滤只保留 `article_channel_id == "2"`（发现/好价），过滤掉文章（`"11"`）和好文（`"1"`）。
7. **价格过滤**：`filter_products_by_price()` 从商品价格字段解析数字，按关键词价格区间筛选。
8. **去重入库**：`DatabaseManager.add_product_history()` 将商品写入 `product_history`，同一 `article_id` 依赖唯一约束避免重复通知。
9. **首次运行策略**：方案首次扫描会记录历史但不发送通知，避免老商品刷屏。
10. **新品通知**：后续发现新商品时，按方案配置发送钉钉和/或微信通知，并写 `notification_logs`。
11. **状态查询**：前端通过 TanStack Query 自动轮询 `/api/monitor/status`、`/api/system/info` 和方案详情接口（默认 15 秒）。

## 7. 通知链路

### 7.1 钉钉

- 方案字段：`dingtalk_webhook`、`dingtalk_secret`。
- 通知实现：`src/dingtalk_notifier.py`。
- 商品通知优先使用 ActionCard，包含标题、价格、商城、关键词、链接和图片。
- 图片处理：`src/image_cache.py` 先把商品图缓存到 `data/images/`，再生成外部可访问 URL。
- 钉钉卡片图片需要公网可访问；公网 host/port 来自环境变量或 `global_settings`。

### 7.2 微信

- 方案字段：`wechat_enabled`、`wechat_account_id`、`wechat_targets`。
- Python 侧客户端：`src/wechat_notifier.py`。
- 本地桥接管理：`src/wechat_bridge_manager.py`。
- Go 服务：`wechat_bridge/main.go`，基于 `fastclaw-ai/weclaw`。
- 桥接默认地址：`127.0.0.1:18012`。
- 微信发送建议使用 `conversation_id`，它包含账号和最近收到消息的上下文。
- 微信图片可直接通过 `media_path` 发送本机图片文件，不要求公网 URL。
- 接收方必须先给 bot 发消息，bridge 才能记录会话并拥有可用 context token。

## 8. 数据库模型

`src/database.py` 在初始化时创建并迁移以下主要表：

| 表 | 职责 |
|---|---|
| `monitor_schemes` | 监控方案：名称、刷新间隔、钉钉配置、微信配置、启用状态 |
| `keywords` | 方案下的关键词和筛选条件：分类、品牌、商城、排序、价格区间 |
| `product_history` | 已发现商品历史：商品 ID、标题、价格、链接、图片、本地图片路径等 |
| `notification_logs` | 通知发送记录：渠道、状态、错误信息、时间 |
| `global_settings` | 全局配置：图片服务 host/port 等 |

重要不变量：

- `product_history.article_id` 唯一，用于避免重复通知。
- 删除方案会级联删除关键词、商品历史、通知日志。
- SQLite 连接启用 `PRAGMA busy_timeout`、`foreign_keys`、`synchronous = NORMAL`，使用 `check_same_thread=False` 支持跨线程访问。
- `update_scheme` 和 `update_keyword` 使用列白名单（`_ALLOWED_SCHEME_COLUMNS` / `_ALLOWED_KEYWORD_COLUMNS`）防止 SQL 注入。
- 数据库默认位于 `data/smzdm_monitor.db`，可由环境变量覆盖。

## 9. API 速查

`src/web_server.py` 暴露的主要接口：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 后端健康检查 |
| `GET` | `/` | 返回前端 `index.html` 或基础提示页 |
| `GET` | `/api/schemes` | 获取方案列表 |
| `GET` | `/api/schemes/{scheme_id}` | 获取方案详情、关键词、最近商品、通知统计 |
| `POST` | `/api/schemes` | 创建方案和初始关键词 |
| `PUT` | `/api/schemes/{scheme_id}` | 更新方案 |
| `DELETE` | `/api/schemes/{scheme_id}` | 删除方案 |
| `GET` | `/api/schemes/{scheme_id}/keywords` | 获取方案关键词 |
| `POST` | `/api/schemes/{scheme_id}/keywords` | 新增关键词 |
| `PUT` | `/api/keywords/{keyword_id}` | 更新关键词 |
| `DELETE` | `/api/keywords/{keyword_id}` | 删除关键词 |
| `GET` | `/api/schemes/{scheme_id}/products` | 获取最近商品 |
| `GET` | `/api/monitor/status` | 获取监控运行状态 |
| `POST` | `/api/schemes/{scheme_id}/restart` | 重启某方案监控任务 |
| `POST` | `/api/test-webhook` | 测试钉钉 webhook |
| `GET` | `/api/wechat/status` | 查看微信桥接状态 |
| `GET` | `/api/wechat/accounts` | 获取微信账号 |
| `POST` | `/api/wechat/reload` | 重载微信账号 |
| `GET` | `/api/wechat/conversations` | 获取微信接收会话 |
| `POST` | `/api/wechat/login/start` | 开始微信扫码登录 |
| `GET` | `/api/wechat/login/status/{login_id}` | 查询扫码登录状态 |
| `POST` | `/api/wechat/login/cancel/{login_id}` | 取消扫码登录 |
| `POST` | `/api/test-wechat` | 测试微信发送 |
| `GET` | `/api/system/info` | 系统统计和路径信息 |
| `GET` | `/api/global-settings` | 获取全局设置 |
| `PUT` | `/api/global-settings` | 更新全局设置 |
| `POST` | `/api/desktop/shutdown` | 桌面壳请求后端优雅关闭 |

公网访问注意：默认只允许本机安全访问部分接口；如需公开 API，检查 `SMZDM_ALLOW_PUBLIC_API` 相关逻辑。

## 10. 前端架构

### 10.1 技术栈

- **React 19** + **Vite 7** — 前端框架和构建工具
- **Tailwind CSS v4** — 原子化 CSS，通过 `@tailwindcss/vite` 插件集成
- **shadcn/ui** — UI 组件体系，代码完全拥有，组件在 `frontend/src/components/ui/`
- **TanStack Query v5** — 异步状态管理，替代手动 polling，解决闭包陈旧问题
- **sonner** — Toast 通知
- **lucide-react** — 图标库
- **Radix UI** — 无障碍基础组件（dialog、switch、select、tooltip 等）

### 10.2 组件结构

- `main.jsx`：入口，设置 `QueryClientProvider`（15 秒 staleTime）和 `Toaster`。
- `App.jsx`：主组件，使用 shadcn/ui Sidebar 体系（`SidebarProvider` + `Sidebar` + `SidebarInset`），包含：
  - **AppSidebar**：可折叠侧边栏（icon 模式），方案列表带状态指示灯、通知数 Badge、启用/停用 Switch。
  - **顶栏**：SidebarTrigger 按钮、标题、运行状态 Badge、Tooltip 工具栏（微信、刷新、设置、主题切换）。
  - **MetricCard**：指标卡片（方案数、启用数、运行任务数、关键词数）。
  - **DetailView**：Hero 面板 + 关键词列表 + 商品列表 + 通知配置面板。
  - **WelcomeView**：空状态引导。
  - **DetailSkeleton**：加载骨架屏。
- `helpers/api.js`：TanStack Query hooks 封装（`useSchemes`、`useMonitorStatus`、`useSchemeDetail`、`useCreateScheme` 等），统一 `apiRequest()` fetch 封装。
- `helpers/utils.js`：`cn()` 函数（clsx + tailwind-merge）。
- `components/ui/`：14 个 shadcn/ui 基础组件。
- `components/modals/`：4 个业务弹窗（SchemeModal、KeywordModal、SettingsModal、WechatModal）。

### 10.3 主题系统

- CSS 变量定义在 `index.css` 的 `:root`（亮色）和 `.dark`（暗色）中。
- 通过 `document.documentElement.classList.toggle("dark")` 切换。
- 包含 sidebar 专用变量（`--sidebar`、`--sidebar-foreground`、`--sidebar-accent` 等）。
- Tailwind v4 的 `@theme inline` 将 CSS 变量映射为 Tailwind 颜色类。

### 10.4 路径别名

- `@` → `frontend/src`（在 `vite.config.js` 和 `jsconfig.json` 中配置）。
- 注意：`lib/` 目录被 `.gitignore` 排除，因此工具函数放在 `helpers/` 而非 `lib/`。

## 11. 已修复的 BUG 清单

以下 BUG 在 v2.0.0 重构中修复：

| BUG | 文件 | 描述 |
|---|---|---|
| BUG-1 | `monitor.py` | `stop_monitoring` 缺少幂等守卫，重复调用导致异常 |
| BUG-2 | `monitor.py` + `web_server.py` | `restart_scheme` 非 async，调用方未 await，导致任务泄漏 |
| BUG-3 | `monitor.py` | 任务清理用 `del` 而非 `pop`，KeyError 风险 |
| BUG-4 | `database.py` | SQLite 连接缺少 `check_same_thread=False` 和 `synchronous = NORMAL` |
| BUG-5 | `image_cache.py` | 同步 `cache_image` 方法在异步上下文中创建新事件循环 |
| BUG-6 | 前端 | 手动 `setInterval` polling 导致闭包陈旧，已用 TanStack Query 替代 |
| BUG-7 | `database.py` | `update_scheme`/`update_keyword` 直接拼接列名，SQL 注入风险 |
| BUG-8 | `monitor.py` + `web_server.py` | 每次创建新 `DingTalkNotifier` 实例而非共享，导致 aiohttp session 泄漏 |
| BUG-9 | `web_server.py` + `desktop_app.py` | `/api/desktop/shutdown` 端点仅在桌面壳模式注册，独立启动后端时缺失 |
| BUG-10 | `monitor.py` | API 返回混合频道结果，未过滤非好价内容（文章/好文混入） |

## 12. 开发与验证命令

以下命令按项目根目录执行。

### 12.1 Python 后端开发

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start.py
```

### 12.2 桌面壳开发

```powershell
.\.venv\Scripts\python.exe desktop_app.py
```

### 12.3 前端开发/构建

```powershell
npm install
npm run dev      # 开发服务器 http://127.0.0.1:5173
npm run build    # 构建到 static/
```

`npm run build` 会生成或更新 `static/`，后端根路由依赖这里的 `index.html`。

### 12.4 微信桥接构建

```powershell
python scripts/build_wechat_bridge.py
```

要求 Go 在 PATH 中，脚本默认设置 `GOTOOLCHAIN=go1.25.0`。

### 12.5 Windows 打包

```powershell
python scripts/build_exe.py
```

常用跳过项：

```powershell
python scripts/build_exe.py --skip-npm-install --skip-wechat-bridge
```

输出位置：`dist/smzdm_monitor/smzdm_monitor.exe`。

### 12.6 快速语法检查

```powershell
python -m compileall desktop_app.py start.py src
```

## 13. 环境变量速查

| 环境变量 | 默认/说明 |
|---|---|
| `HOST` | 后端 host 默认来自 `src/runtime.py`，通常为 `127.0.0.1` |
| `PORT` | 后端默认端口 `8000` |
| `SMZDM_PORT` | 桌面壳使用的后端端口 |
| `SMZDM_BIND_HOST` | 后端绑定地址，桌面壳默认 `0.0.0.0` |
| `SMZDM_DATA_DIR` | 覆盖运行数据目录 |
| `SMZDM_LOG_DIR` | 覆盖日志目录 |
| `DATABASE_PATH` | 覆盖 SQLite 文件路径 |
| `LOG_FILE` | 覆盖主日志文件路径 |
| `LOG_LEVEL` | 默认 `INFO` |
| `LOG_BACKUP_DAYS` | 日志轮转保留天数，默认 `14` |
| `AUTO_START_MONITOR` | 后端是否自动启动监控，默认 true |
| `SMZDM_NO_AUTO_MONITOR` | 桌面壳禁用自动监控 |
| `SMZDM_AUTO_START_DELAY` | 后端延迟自动启动监控秒数，默认 `4` |
| `SMZDM_MONITOR_CONCURRENCY` | 关键词监控并发数，默认 `3` |
| `SMZDM_API_BASE_URL` | SMZDM API 地址 |
| `SMZDM_IMAGE_SERVER_HOST` | 强制设置通知图片服务 host |
| `SMZDM_IMAGE_SERVER_PORT` | 强制设置通知图片服务 port |
| `SMZDM_PUBLIC_IP` | 手动指定公网 IPv4 |
| `SMZDM_ALLOW_PUBLIC_API` | 允许公网访问管理 API，默认关闭 |
| `SMZDM_BROWSER_MODE` | 强制桌面壳使用浏览器模式 |
| `SMZDM_WEBVIEW_LOAD_TIMEOUT` | PyWebView 加载等待时间 |
| `SMZDM_SKIP_WEBVIEW2_CHECK` | 跳过 WebView2 检查 |
| `WECHAT_BRIDGE_ADDR` | Go bridge 监听地址，默认 `127.0.0.1:18012` |
| `WECHAT_BRIDGE_URL` | Python 通知客户端访问 bridge 的 URL，默认 `http://127.0.0.1:18012` |
| `WECHAT_BRIDGE_TOKEN` | bridge 访问令牌，Python/Go 两侧需一致 |
| `WECHAT_BRIDGE_DATA_DIR` | bridge 会话记录目录 |
| `WECHAT_BRIDGE_LOG_DIR` | bridge 日志目录 |

## 14. 高风险修改点

1. **监控任务生命周期**
   - `SMZDMMonitor.tasks` 按方案维护后台任务。
   - `restart_scheme` 是 async 方法，调用方必须 await。
   - 修改方案、删除方案、重启方案时要考虑正在运行的任务取消和重建。
   - 不要在监控循环中加入阻塞调用。

2. **频道过滤**
   - `fetch_products()` 在客户端过滤只保留 `article_channel_id == "2"`（发现/好价）。
   - SMZDM API 不支持 `c=faxian` 参数过滤，必须依赖客户端过滤。
   - 移除该过滤会导致文章和好文内容混入监控结果。

3. **首次运行不通知**
   - 方案首次扫描只入库不推送，这是防止老商品刷屏的重要行为。
   - 修改 `monitor_scheme()` 时不要误删该逻辑。

4. **SQLite 去重与并发**
   - 商品去重依赖 `article_id` 唯一约束。
   - 多任务会并发写 SQLite，连接使用 `check_same_thread=False` + `busy_timeout` + `synchronous = NORMAL`。
   - `update_scheme`/`update_keyword` 使用列白名单防止 SQL 注入，新增列时需同步更新白名单。

5. **图片公网可访问性**
   - 钉钉卡片图片必须能被钉钉服务器访问。
   - 本地 `127.0.0.1` 图片 URL 对钉钉无效；公网 host/端口配置错误会导致图片不显示。
   - `image_cache.py` 仅保留异步方法，不要重新添加同步包装器。

6. **微信 conversation context**
   - bridge 需要接收方先发消息，记录 context token 后再可靠发送。
   - 直接使用裸 `to`/`targets` 兼容字段可能不稳定。

7. **PyInstaller 路径**
   - 开发模式和打包模式的 app root/resource root 不同。
   - 统一使用 `src/runtime.py`，不要在新代码里硬编码 `data/`、`static/`、`logs/` 相对路径。

8. **前端路径别名**
   - `@` 指向 `frontend/src`，不要使用 `@/lib/`（被 `.gitignore` 排除），使用 `@/helpers/`。
   - shadcn/ui 组件是 JSX（非 TSX），不支持 TypeScript `type` 导入语法。

9. **敏感/运行文件**
   - `.gitignore` 排除了 `config.py`、`lib/`、数据库、日志、测试脚本、构建产物、微信 bridge EXE。
   - 后续 AI 不应假设这些文件都已纳入版本控制或可安全读取/修改。

## 15. 后续 AI 接手建议

### 15.1 新任务优先阅读顺序

1. `README.md`：项目面向用户/开发者的完整说明。
2. `AI_CONTEXT.md`：当前交接摘要。
3. `src/web_server.py`：API 和服务生命周期。
4. `src/monitor.py`：监控和通知主逻辑（含频道过滤）。
5. `src/database.py`：数据结构和持久化约束（含 SQL 注入防护）。
6. `frontend/src/App.jsx`：前端主组件和布局。
7. `frontend/src/helpers/api.js`：TanStack Query hooks 和 API 封装。
8. `desktop_app.py`：桌面常驻和打包运行形态。
9. `wechat_bridge/main.go`：微信桥接能力边界。

### 15.2 修改后建议验证

- 后端改动：运行 `python -m compileall desktop_app.py start.py src`。
- API 改动：启动 `python start.py` 后访问 `/api/health` 和相关接口。
- 前端改动：运行 `npm run build`，确认 `static/` 更新；用浏览器验证 UI 渲染和 API 联动。
- 微信相关：先确认 bridge `/health`、`/api/wechat/account`，再测 `/api/test-wechat`。
- 打包相关：运行 `python scripts/build_exe.py` 或按需跳过已构建部分。

### 15.3 不要轻易做的事

- 不要把 `data/`、`logs/`、`dist/`、`node_modules/` 加入版本控制。
- 不要硬编码钉钉 webhook、微信 token、公网 IP 等敏感配置。
- 不要把监控任务改成多进程，除非同步设计 API 控制、SQLite 并发和进程生命周期。
- 不要在没有确认微信上下文机制的情况下改 bridge 的 `conversation_id` 逻辑。
- 不要把旧缓存图片或本地数据库打入发布包。
- 不要移除 `fetch_products()` 中的频道过滤逻辑。
- 不要在前端 JSX 文件中使用 TypeScript `type` 导入语法。
- 不要使用 `@/lib/` 路径别名（被 `.gitignore` 排除），使用 `@/helpers/`。

---

最后更新：2026-06-28
