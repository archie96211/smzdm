# 好价雷达 MCP

本项目内置的 stdio MCP + Agent Skill，通过好价雷达 `/api/v1` 管理监控。不包含 CLI、抓取器或数据库访问代码。现有 MCP 命令和配置名沿用 `smzdm`，以兼容已安装客户端。

完整步骤见 [安装、首次使用与排错](docs/installation.md)。当前为本地源码版本，尚未公开发布。

## 技术与安装

官方 MCP Python SDK 2.2 + HTTPX + Pydantic；依赖锁定在 `uv.lock`。需要 Python 3.10+。

```sh
uv sync --frozen
uv run --frozen smzdm-mcp
```

stdio 的标准输出由 SDK 专用于协议通信。私有配置默认读取 `~/.config/smzdm-mcp/config.json`：

```json
{"url":"http://127.0.0.1:18087","token_file":"/private/path/api-token"}
```

也支持 `SMZDM_MCP_CONFIG`、`SMZDM_URL`、`SMZDM_API_TOKEN_FILE` 或 `SMZDM_API_TOKEN`。token 应与服务端匹配；配置及令牌文件限制为用户可读。不要把实际地址或密钥放到此仓库。

AI 客户端启动命令为安装环境里的 `smzdm-mcp`。将仓库根目录的 `skills/smzdm-monitor` 安装到客户端 Skill 目录。具体注册方法取决于客户端，不需要暴露公网 MCP。

## 能力

工具覆盖能力探测、方案与关键词管理、发现商品和通知日志、Bark 与全局设置，以及个人商品档案、商品直达链接和购买记录的查询、新增、修改、删除（以实际 tools/list 为准）。购买记录须填写实付金额、包装数、每包基础单位数；`purchase_channel` 保存购买平台代码，`order_number` 保存来源订单号（同一订单的多个商品可共用），`store` 仅保存具体店铺；渠道代码列表由 `get_capabilities` 返回。可选 `variant` 区分型号、尺寸和口味。不同规格的单价应分别比较。`get_deal_context` 只在用户问某件商品时获取历史价与少量已购候选；订单号、店铺和备注不会随按需比价候选送出。`verify_deal_price` 根据优惠原文核对算式并在本地计算。后台监控不请求模型，也不主动查询历史价。`list_deal_assessments` 可查看基础提醒及旧版保存的分析记录，旧分析不代表当前自动流程。

若某个 Codex 任务的 stdio MCP 返回 `Transport closed`，先停止写入重试。在同一任务中重新启动 `smzdm-mcp` 子进程可恢复连接；新进程必须继承私密配置环境，先只读调用 `get_capabilities` 和 `list_my_purchases` 核对状态，再继续写入。旧连接不会因服务端重启而自动恢复；不要绕过 MCP 直接修改数据库。

`list_my_purchases` 默认每页 200 条，可传 `limit` 与 `offset` 翻页直到返回空列表；不要把第一页当成全量。已知记录 ID 用 `get_my_purchase` 精确读取；已知来源订单号用 `find_my_purchases` 查同单全部商品。写入结果不确定时先精确查询再考虑重试，避免重复记录。

创建需要 `request_id`，重试沿用同一 ID 和参数。服务端事务保存完整方案，默认暂停。使用 `enabled=true` 显式启动。通知成功仅表示服务接受。

凭据设置通过现有本地管理界面完成，MCP 不收集明文 Key。删除是永久操作；暂停请用启停工具。

当前未实现：元数据检索、无副作用搜索预览、排除词、完整价格时间序列、远程 HTTP MCP、微信扫码授权代理、系统关机/端口变更。历史最低价仅对成功确认商品详情链接且慢慢买返回记录的商品可用。能力 API 明确报告不支持项。

## 检查

```sh
uv run pytest -q
# 仅对隔离测试实例运行；创建、启停后删除测试方案，不开启通知
uv run python scripts/smoke_mcp.py
```

后端与 MCP 在同一仓库维护；旧部署没有 `/api/v1` 时需要先升级服务。UI 与 MCP 共用服务端数据与调度，AI 退出不影响常驻监控。

### Private certificate authorities

For a service using a private HTTPS CA, set `ca_file` in the private JSON config
(or `SMZDM_CA_FILE`) to the trusted public CA certificate path. Verify its
fingerprint with your administrator first. TLS certificate and hostname checks
remain enabled; an invalid or missing CA file stops the connection.
