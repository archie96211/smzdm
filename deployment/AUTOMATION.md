# Automation API and MCP

`/api/v1` requires a Bearer token, configured using `SMZDM_API_TOKEN` or `SMZDM_API_TOKEN_FILE`. With no token it returns 503. Existing desktop/UI routes retain their existing network restrictions; this is not a public multi-user service. Keep the deployment private and explicitly configure allowed networks when required.

The MCP adapter is maintained in this repository under `mcp/`, alongside `skills/smzdm-monitor` and uses stdio on the AI client computer. It adds no LLM or MCP process to the monitoring container.

API features: transactional monitor creation with `Idempotency-Key`, paused-by-default creation, keyword rules, partial monitor/settings updates, redacted readback, runtime status, products/delivery logs and Bark settings. `/api/v1/capabilities` exposes limits and creation schema. Reuse idempotency keys for identical retries; conflicting payloads return 409.

Personal purchase management is available through authenticated `/api/v1/owned-products` and `/api/v1/purchases` (GET/POST/PUT/DELETE). Purchase records include `purchase_channel` (platform code), optional `order_number` (source order reference), optional `store` (specific seller), optional `variant`, `package_count`, `units_per_package`, optional `inner_package_count` and `inner_package_label`, and exact `paid_amount`. Multiple line items may share an order number; it is not unique. Channel codes are returned by `/api/v1/capabilities`. Omitted channels and order numbers on old write clients remain empty when creating records and preserve existing values on updates. The generic SQLite migration adds empty values; assigning historical channels or extracting order numbers from verified notes is a separate, backed-up, user-specific data operation. Product units cannot be changed after purchases exist; a product with purchase records cannot be deleted. The dashboard uses the same SQLite records and shows per-variant and inner-package costs. Owned-product merchant links can be added through the dashboard, `/api/purchase/products/{id}/links`, `/api/v1/owned-products/{id}/links`, or MCP; only supported JD/Taobao/Tmall item pages and Taobao's item-detail affiliate links are accepted. Coupon pages remain invalid item identities.

The authenticated purchase list defaults to 200 records and accepts `limit=1..200&offset=0..` for complete paging in date/ID order. `GET /api/v1/purchases/{record_id}` reads one record. `POST /api/v1/purchases/search` with JSON `{"order_number":"..."}` returns every item for that exact order without placing the order number in the URL. MCP exposes these as `list_my_purchases(limit, offset)`, `get_my_purchase(record_id)` and `find_my_purchases(order_number)`. Before retrying an uncertain write, search its exact order number; the first 200 records are never proof that an older order is absent.

Notifications group newly discovered offers by confirmed item URL first, conservative title matching second. For a Taobao item-detail affiliate link, one public redirect hop extracts the official numeric item ID for cross-source identity; the original SKU-specific affiliate URL is retained because different SKUs may have different prices. A JD-owned affiliate detail link is followed for at most two JD-owned hops to a verified item page. Link resolution is capped at eight offers per polling cycle. The monitor does not query historical prices or call a model in the background. Each grouped offer is saved in SQLite before delivery, then sent as its own basic notification. Failed deliveries remain pending for later polling cycles. A confirmed cheaper plain price can generate a new alert, while equal or higher plain prices are suppressed across restarts.

For a user-selected product, the authenticated `POST /api/v1/deal-context` endpoint and MCP `get_deal_context` tool confirm the item link, query ManManBuy history only when needed, reuse a history result cached within 24 hours, and return at most three likely related owned products with limited purchase summaries. The AI client decides whether the products are semantically comparable. If the deal requires arithmetic, it supplies an expression with exact source quotes to `POST /api/v1/verify-price` or MCP `verify_deal_price`; local Decimal code verifies operands and computes the result. The AI client's own model handles the conversation. No model URL or key is configured in the monitor container. Cookies, credentials, purchase stores and free-form notes are excluded from the deal-context result. Older saved assessments remain available through `/api/v1/monitors/{id}/assessments` and MCP but are not produced by the new background path.

Keyword `source` accepts `smzdm` (default), `manmanbuy`, or `both`. The public ManManBuy discount search does not use the private QR session; that session is only for historical-price queries. Each source gets its own first-fetch baseline and retry backoff. Search page layout may change, so source failures must be checked in logs before assuming a keyword is healthy.

Use 300 seconds as an initial polling interval; API enforces at least 60 seconds. A first fetch saves a baseline and does not notify. HTTP notification success does not establish phone delivery.

Build: `docker compose build`, start: `docker compose up -d`. Data is in the named `/data` volume. Before upgrading, take a SQLite online backup, save the prior compose file, and tag the prior image. Restore code by selecting the saved image; database changes in this branch are additive. Do not remove the volume during normal upgrades.

Runtime defaults: Python slim, no GUI, non-root, health check, 256 MiB RAM/0.5 CPU, read-only root filesystem, bounded temporary directory and rotating logs. Resource limits are deployment starting points, not universal recommendations. Tested on amd64; arm64 runtime validation remains pending.

Secrets belong in a private environment file or secret mount, never examples or source archives. Restrict environment/config file access. Credential setup still uses the UI. The MCP deliberately does not accept raw notification credentials in chat.

## ManManBuy QR connection (optional)

The history-price toolbar opens an official WeChat QR login bridge. The backend
uses aiohttp to request a QR code and poll its status; no browser process, Node
runtime, password form or manual Cookie entry is required. Scan only if you intend
to connect this service to your account. QR codes expire after 60 seconds and
polling stops when the dialog closes or login completes. A pending QR does not
replace the current saved session until login succeeds.

Account cookies are saved separately under `/data/credentials/manmanbuy.json`
(directory 700, file 600), never returned through the settings API. Protect volume
backups accordingly. The service checks a saved session every 15 minutes, even
when the dashboard is closed. The separate ManManBuy settings default to no
alerts; users may enable them and choose one or more configured Bark, DingTalk,
WeChat or WxPusher channels. A WeChat target must be selected. On confirmed
expiration or a verification challenge, each selected channel is alerted once.
Per-channel alert state survives a restart; a successfully validated connection
or new QR login resets it. Failed deliveries retry on the next check, while
transient network failures do not alert.
The dashboard also checks on first use and at most every six hours while open.
The toolbar shows a warning marker and offers re-login. Bark server acceptance
does not prove that a device displayed the notification.

A manual product query verifies the connection. Marketplace authorization or an
additional challenge may still require visiting ManManBuy itself; logged-in does
not guarantee every product is queryable. On-demand historical lookup uses only a confirmed
merchant item URL. If a ManManBuy "go buy" jump is a coupon page, the saved login
session is used to inspect that article's embedded item-detail URL. Coupon-only
pages and anti-bot interstitials without a validated item identity remain unresolved;
their historical price is shown as unavailable, not guessed. External undocumented
endpoints may change; failure does not prevent the source offer from being processed.

## Validation and parked research

The isolated real-offer check and its remaining notification acceptance work are
recorded in [deal-pipeline-validation-2026-09-23.md](research/deal-pipeline-validation-2026-09-23.md).
The app-only 喵小二 affiliate-link experiment is documented in
[miaoxiaoer-super-conversion.md](research/miaoxiaoer-super-conversion.md) and is
parked. No automatic login or conversion adapter is part of this service.
