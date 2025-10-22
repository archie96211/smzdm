# SMZDM WeChat Bridge

This is a small HTTP bridge built on top of `fastclaw-ai/weclaw`. It keeps WeClaw's login and credential storage, then adds `account_id` routing so SMZDM Monitor can send messages through a selected WeChat account.

## Build

From the project root:

```powershell
python build_wechat_bridge.py
```

Output:

```text
wechat_bridge\smzdm_wechat_bridge.exe
```

The script sets `GOTOOLCHAIN=go1.25.0` by default because WeClaw currently requires Go 1.25.

## Bind WeChat Accounts

The bridge uses WeClaw's credential storage. Scan a QR code to bind your WeChat account:

```powershell
go install github.com/fastclaw-ai/weclaw@latest
```

Or use the built-in QR login from the SMZDM Monitor frontend (`POST /api/wechat/login/start`).

WeClaw stores credentials under:

```text
%USERPROFILE%\.weclaw\accounts\
```

**Single-account mode**: The bridge only supports one WeChat account at a time. When a new QR login succeeds, all existing credential files are automatically removed before saving the new one. If multiple credential files are found on startup, only the most recently modified one is kept.

After adding or changing accounts, call `POST /api/wechat/reload` or restart the bridge.

## Run

```powershell
$env:WECHAT_BRIDGE_ADDR = "127.0.0.1:18012"
$env:WECHAT_BRIDGE_TOKEN = "change-me"
.\wechat_bridge\smzdm_wechat_bridge.exe
```

`WECHAT_BRIDGE_TOKEN` is optional. If set, requests must include either `X-Bridge-Token: change-me` or `Authorization: Bearer change-me`.

## API

Health check:

```http
GET /health
```

Get current account:

```http
GET /api/wechat/account
```

Returns the single bound account with `account_id`, `status`, and `last_error` fields. Status can be `online`, `connecting`, `reconnecting`, `session_expired`, `error`, or `stopped`.

Reload credentials:

```http
POST /api/wechat/reload
```

List receiving conversations:

```http
GET /api/wechat/conversations
```

After QR login, send any message from the WeChat user or group that should receive notifications. The bridge records that inbound `from_user_id` and `context_token` as a conversation. Use the returned `id` as `conversation_id`.

Start QR login:

```http
POST /api/wechat/login/start
```

The response contains `id` and `qr_image_data_url`. Show that data URL in the UI, then poll:

```http
GET /api/wechat/login/status/{id}
```

When `status` becomes `confirmed`, the account has been saved to WeClaw's account directory and can be selected by `account_id`.

Cancel QR login:

```http
POST /api/wechat/login/cancel/{id}
```

Send message:

```http
POST /api/wechat/send
Content-Type: application/json

{
  "conversation_id": "selected-account-id:user@im.wechat",
  "text": "SMZDM Monitor test",
  "media_path": "D:\\path\\to\\data\\images\\example.jpg"
}
```

Rules:

- Prefer `conversation_id`; it carries the account and the latest WeChat context token.
- `account_id` is optional when `conversation_id` is provided.
- `to` and `targets` remain as low-level compatibility fields, but they only work reliably after the target has messaged the bot and a context token has been recorded.
- `media_path` and `media_paths` send local files directly from the bridge host.
- `media_url`, `image_url`, and `media_urls` are still supported when the bridge should fetch a remote file.

## Current Scope

- Single-account mode: only one WeChat account is active at a time.
- Session expiry detection: when send errors contain `ret=-14` or `session expired`, the account status is updated to `session_expired`. When `ret=-2` is detected, status becomes `error`.
- It does not replace WeClaw's credential format.
- It only exposes the HTTP bridge needed by SMZDM Monitor.
