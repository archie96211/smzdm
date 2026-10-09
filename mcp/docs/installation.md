# MCP 与 Skill 安装、使用

当前从本地源码安装，尚未发布 PyPI 包。MCP 与 Skill 随 SMZDM 原项目一起维护；下列命令在仓库的 `mcp/` 目录执行；不要把占位地址直接当作生产配置。

## 1. 准备服务

需要支持 `/api/v1` 的 SMZDM 服务、Python 3.10+、uv，以及支持 stdio MCP 的 AI 客户端。旧版服务需先升级。

在服务端私密环境文件中配置 `SMZDM_API_TOKEN`，重启该服务使其生效；客户端使用相同令牌。通知渠道凭据在 SMZDM 管理界面填写。服务端与客户端可以在不同机器上，但客户端必须能访问服务地址。

## 2. 安装 MCP

```sh
uv sync --frozen
```

客户端将使用`mcp/.venv/bin/smzdm-mcp`，因此保留源码目录及虚拟环境。安装本身不启动监控服务；AI 客户端按需启动 MCP，监控仍由服务端常驻执行。

创建 `~/.config/smzdm-mcp/`，目录权限设为 700，在其中安全保存 `api-token` 和 `config.json`，文件权限设为 600。令牌内容与服务端一致，避免写入命令历史或仓库。

`config.json` 示例：

```json
{
  "url": "https://monitor.example.com",
  "token_file": "~/.config/smzdm-mcp/api-token"
}
```

自建 CA 的 HTTPS 服务增加 `ca_file`，指向核验过指纹的公开根证书文件。不要复制 CA 私钥，也不要关闭证书验证。普通受信任 HTTPS 不需要该字段。

可通过 `SMZDM_MCP_CONFIG` 指定配置文件；`SMZDM_URL`、`SMZDM_API_TOKEN_FILE`、`SMZDM_API_TOKEN`、`SMZDM_CA_FILE` 可以覆盖配置。同有 token 文件和直接令牌时，以文件为准。

## 3. 注册到 Codex

在仓库的 `mcp/` 目录执行：

```sh
codex mcp add smzdm -- "$PWD/.venv/bin/smzdm-mcp"
codex mcp get smzdm
```

注册结果应为 enabled、stdio。然后重新连接 MCP 或开启新任务。其他客户端同样使用 stdio，command 填项目 `.venv/bin/smzdm-mcp` 的绝对路径，无需参数。它不是远程 HTTP MCP，不能把业务服务网址填进 MCP 的远程 URL 配置。

## 4. 安装 Skill

Codex 默认 Skill 目录为 `~/.codex/skills`；自定义 CODEX_HOME 时使用对应目录。

```sh
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R ../skills/smzdm-monitor "${CODEX_HOME:-$HOME/.codex}/skills/"
```

首次安装前确认目标不存在；更新已有版本时先备份并比较本地修改。重新开启任务后应能找到 `smzdm-monitor`。其他 Agent 客户端按其 Skill 目录规则安装同一文件夹。

Skill 指导 AI 进行分组、去重和验收，实际读写由 MCP 执行；只安装 Skill 无法操作服务，只安装 MCP 则缺少这些业务操作指导。

## 5. 使用与验收

先说“查看当前监控和服务状态”，只读确认连接正常。

随后可以说：

> 帮我监控三星 990 PRO 2TB，低于 1000 元时用 Bark 提醒，归入数码存储组，每五分钟检查。

AI 应先读取现有方案、复用合适分组，创建后读回关键词、价格条件、通知渠道与启停状态。未指定价格时不猜底价；商品匹配基于关键词与文章信息，不保证精确 SKU 或个人券后价。

暂停：“暂停数码存储组的监控。”

修改：“把该监控价格上限改为 900 元，其余不变。”

排查：“看看最近抓到了什么，为什么没收到通知。”

按需分析：“这件商品划算吗？这是优惠链接、标题和标价……” AI 调用 `get_deal_context` 查一次商品身份、历史价和少量已购候选；有优惠计算时再调用 `verify_deal_price` 核对原文算式。仅有标题时可以参考已购记录，但无法确认对应商品的历史低价。后台监控不调用模型，模型用量只发生在主动对话中；服务端无需配置模型 API。

首次抓取通常只建立历史基线，不发通知。发送记录成功不等于手机已收到。只有明确要求测试时才发测试通知。AI 客户端退出不会停止服务端监控。

## 6. 常见问题

| 现象 | 检查 |
| --- | --- |
| 找不到工具 | MCP 是否 enabled、启动路径是否存在；刷新连接或开新任务 |
| 无法连接 | 客户端网络、域名解析、服务状态；内网地址要求 LAN 或家庭 VPN |
| HTTPS 验证失败 | 主机名、CA 文件及证书有效期；不要禁用验证 |
| 401 | 两端令牌是否一致，服务端是否已重启加载 |
| 403 | 服务端网络允许范围与反向代理来源 |
| 404 | 是否为支持 `/api/v1` 的服务版本 |
| 503 | 服务端是否配置 API 令牌 |
| 创建重试 409 | 读取已有状态；同一 request_id 必须使用同一请求参数 |

测试命令见 [README](../README.md)。烟雾测试会创建、启停和删除测试方案，仅用于隔离测试实例；它不是无副作用的连接检查。

## 7. 更新与移除

更新源码后执行 `uv sync --frozen`，重连 MCP；Skill 更新前保留自己的修改。移除 MCP 用 `codex mcp remove smzdm`，移除 Skill 则删除安装的 `smzdm-monitor` 目录。这些操作不会删除服务端监控，也不会停止正在运行的方案；如需停止，先明确暂停相关方案。
