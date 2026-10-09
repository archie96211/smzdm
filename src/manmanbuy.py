"""Optional, browser-free ManManBuy QR login and private session management."""
import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from yarl import URL
from .bark_notifier import BarkConfig, BarkNotifier
from .dingtalk_notifier import DingTalkNotifier
from .merchant_links import canonical_product_url
from .wechat_notifier import WeChatNotifier
from .wxpusher_notifier import WxPusherNotifier

LOGIN = "https://home.manmanbuy.com/reg.ashx"
HISTORY = "https://tool.manmanbuy.com/HistoryLowest.aspx"
API = "https://tool.manmanbuy.com/api.ashx"
# Public website signing parameter, not an account credential.
SIGNING_VALUE = "c5c3f201a8e8fc634d37a766a0299218"
AUTH_COOKIES = {"60014_mmmuser", "mmbuser_ext"}
CHECK_INTERVAL = 900
logger = logging.getLogger(__name__)


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ticket = ""
        self.logged_in = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("id") == "ticket":
            self.ticket = attrs.get("value", "")
        if tag == "a" and "logout.aspx" in attrs.get("href", "").lower():
            self.logged_in = True


def public_product_url(value):
    if urlsplit(value or "").scheme != "https":
        raise ValueError("请使用 HTTPS 商品详情链接")
    canonical = canonical_product_url(value)
    if not canonical:
        raise ValueError("请使用京东、淘宝或天猫的商品详情链接")
    return canonical


class QueryRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class AlertSettings(BaseModel):
    enabled: bool = False
    channels: list[Literal["bark", "dingtalk", "wechat", "wxpusher"]] = Field(default_factory=list)
    wechat_account_id: str = Field(default="", max_length=100)
    wechat_targets: str = Field(default="", max_length=500)


class Connection:
    def __init__(self, directory, database=None):
        self.path = Path(directory) / "credentials" / "manmanbuy.json"
        self.alert_path = self.path.with_name("manmanbuy-alert.json")
        self.database = database
        self.notifier = BarkNotifier()
        self.dingtalk_notifier = DingTalkNotifier()
        self.wechat_notifier = WeChatNotifier(
            bridge_url=os.getenv("WECHAT_BRIDGE_URL", "http://127.0.0.1:18012"),
            token=os.getenv("WECHAT_BRIDGE_TOKEN", ""),
        )
        self.wxpusher_notifier = WxPusherNotifier()
        self.watch_task = None
        self.lock = asyncio.Lock()
        self.client = None
        self.pending = None
        self.state = "disconnected"
        self.checked_at = None
        self.last_error = None
        self.last_login = 0

    async def get_client(self):
        if self.client is None or self.client.closed:
            jar = aiohttp.CookieJar()
            if self.path.exists():
                try:
                    saved = json.loads(self.path.read_text())
                    for item in saved["cookies"]:
                        cookie = SimpleCookie()
                        cookie[item["name"]] = item["value"]
                        cookie[item["name"]]["domain"] = ".manmanbuy.com"
                        cookie[item["name"]]["path"] = "/"
                        cookie[item["name"]]["secure"] = True
                        if item["name"] in AUTH_COOKIES:
                            jar.update_cookies(cookie, response_url=URL(HISTORY))
                    self.state = "unverified"
                except (ValueError, KeyError, OSError, TypeError):
                    self.state = "expired"
            self.client = aiohttp.ClientSession(cookie_jar=jar,
                timeout=aiohttp.ClientTimeout(total=15), headers={"User-Agent": "Mozilla/5.0"})
        return self.client

    def status(self):
        labels = {"disconnected": "尚未连接慢慢买", "unverified": "登录已保存，等待验证",
                  "connected": "已连接慢慢买", "expired": "登录已失效，请重新扫码登录",
                  "verification_required": "慢慢买要求完成验证，请前往官方页面处理"}
        return {"state": self.state, "message": labels[self.state], "checked_at": self.checked_at,
                "last_error": self.last_error, "has_session": self.path.exists()}

    def alert_sent(self):
        try:
            return set(json.loads(self.alert_path.read_text()).get("sent", []))
        except (OSError, ValueError, TypeError, AttributeError):
            return set()

    def clear_alert(self):
        self.alert_path.unlink(missing_ok=True)

    def record_alert(self, channels):
        self.alert_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = self.alert_path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"sent": sorted(channels)}, stream)
        os.replace(temp, self.alert_path)

    def alert_settings(self):
        try:
            return AlertSettings.model_validate_json(
                self.database.get_config("manmanbuy_alert") or "{}")
        except (ValueError, TypeError, AttributeError):
            return AlertSettings()

    def available_channels(self):
        if self.database is None:
            return {}
        bark = self.database.get_bark_config()
        return {
            "bark": bool(bark.get("device_key")),
            "dingtalk": bool(self.database.get_config("dingtalk_webhook")),
            "wechat": os.getenv("SMZDM_WECHAT_BRIDGE_ENABLED", "true").lower() == "true",
            "wxpusher": bool(self.database.get_config("wxpusher_app_token")
                             and self.database.get_config("wxpusher_uid")),
        }

    async def send_alert(self, channel, settings):
        title = "慢慢买登录需要处理"
        body = self.status()["message"] + "。打开好价雷达，进入「慢慢买历史价格」重新连接或完成验证。"
        if channel == "bark":
            config = BarkConfig.model_validate(self.database.get_bark_config())
            return await self.notifier.send_message(
                config, title, body, {"scheme": "系统", "url": ""})
        if channel == "dingtalk":
            return await self.dingtalk_notifier.send_text(
                self.database.get_config("dingtalk_webhook"), f"{title}：{body}",
                self.database.get_config("dingtalk_secret") or "")
        if channel == "wechat":
            return await self.wechat_notifier.send_message(
                account_id=settings.wechat_account_id,
                conversation_id=settings.wechat_targets, text=f"{title}\n{body}")
        if channel == "wxpusher":
            return await self.wxpusher_notifier.send_markdown(
                self.database.get_config("wxpusher_app_token"), title, body,
                uid=self.database.get_config("wxpusher_uid"))
        return False

    async def check_and_alert(self):
        async with self.lock:
            if not self.path.exists():
                self.clear_alert()
                return
            settings = self.alert_settings()
            if not settings.enabled:
                return
            if self.state != "verification_required":
                try:
                    await self.validate()
                except (aiohttp.ClientError, asyncio.TimeoutError, HTTPException) as exc:
                    self.last_error = type(exc).__name__
                    return
            if self.state == "connected":
                self.clear_alert()
                return
            if self.state not in {"expired", "verification_required"}:
                return
            sent = self.alert_sent()
            available = self.available_channels()
            for channel in dict.fromkeys(settings.channels):
                if channel in sent or not available.get(channel):
                    continue
                try:
                    success = await self.send_alert(channel, settings)
                except Exception as exc:
                    logger.warning("ManManBuy alert send failed: %s", type(exc).__name__)
                    continue
                if success:
                    sent.add(channel)
                    self.record_alert(sent)

    async def watch_session(self):
        while True:
            try:
                await self.check_and_alert()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed check must not stop the deal monitor or the next check.
                logger.exception("ManManBuy session check failed")
            await asyncio.sleep(CHECK_INTERVAL)

    def save(self, client):
        cookies = [{"name": c.key, "value": c.value} for c in client.cookie_jar if c.key in AUTH_COOKIES]
        if not any(c["name"] == "60014_mmmuser" and c["value"] for c in cookies):
            raise HTTPException(502, "官方登录未返回可保存的会话，请重新登录")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        temp = self.path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"cookies": cookies}, stream)
        temp.chmod(0o600)
        os.replace(temp, self.path)

    async def json_request(self, client, method, url, **kwargs):
        async with client.request(method, url, allow_redirects=False, **kwargs) as response:
            if response.status != 200:
                raise HTTPException(502, "慢慢买暂时不可用，请稍后重试")
            try:
                return await response.json(content_type=None)
            except (ValueError, UnicodeError):
                raise HTTPException(502, "慢慢买返回格式发生变化，请稍后重试") from None

    async def clear_pending(self):
        if self.pending:
            await self.pending["client"].close()
            self.pending = None

    async def start_login(self):
        if time.monotonic() - self.last_login < 5:
            raise HTTPException(429, "请稍候再刷新二维码")
        self.last_login = time.monotonic()
        await self.clear_pending()
        client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        try:
            result = await self.json_request(client, "POST", LOGIN,
                params={"method": "weixinQrCodeToken", "timestamp": str(int(time.time()*1000))})
            data = result.get("data") or {}
            qr = data.get("qrCodeURL", "")
            parsed = urlsplit(qr)
            if result.get("code") != 2000 or parsed.scheme != "https" or parsed.hostname != "mp.weixin.qq.com" or not data.get("sceneStr"):
                raise HTTPException(502, "无法获取官方登录二维码，请稍后重试")
            login_id = secrets.token_urlsafe(24)
            self.pending = {"id": login_id, "scene": data["sceneStr"], "client": client,
                            "deadline": time.monotonic()+60, "last_poll": 0}
            return {"login_id": login_id, "qr_url": qr, "expires_in": 60}
        except BaseException:
            await client.close()
            raise

    async def poll_login(self, login_id):
        pending = self.pending
        if not pending or not secrets.compare_digest(pending["id"], login_id):
            raise HTTPException(404, "登录请求已结束，请重新获取二维码")
        if time.monotonic() >= pending["deadline"]:
            await self.clear_pending()
            return {"state": "qr_expired"}
        if time.monotonic()-pending["last_poll"] < 2:
            return {"state": "waiting"}
        pending["last_poll"] = time.monotonic()
        result = await self.json_request(pending["client"], "POST", LOGIN,
            params={"method": "weixinQrCodeCheck", "sceneStr": pending["scene"], "timestamp": str(int(time.time()*1000))})
        if (result.get("data") or {}).get("status") != 1:
            return {"state": "waiting"}
        self.save(pending["client"])
        if self.client:
            await self.client.close()
        self.client = pending["client"]
        self.pending = None
        self.state = "unverified"
        await self.validate()
        if self.state == "connected":
            self.clear_alert()
        return self.status()

    async def page(self):
        client = await self.get_client()
        async with client.get(HISTORY, allow_redirects=False) as response:
            if response.status != 200:
                raise HTTPException(502, "慢慢买暂时不可用，请稍后重试")
            html = await response.text()
        parser = Inputs()
        parser.feed(html)
        self.checked_at = int(time.time())
        self.last_error = None
        self.state = "connected" if parser.logged_in else "expired"
        return parser

    async def validate(self):
        if not self.path.exists() and self.client is None:
            return self.status()
        await self.page()
        return self.status()

    async def query(self, url):
        try:
            url = public_product_url(url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        parser = await self.page()
        if self.state != "connected":
            raise HTTPException(409, "请先连接慢慢买或重新登录")
        if not parser.ticket:
            raise HTTPException(502, "查询页面发生变化，暂时无法查价")
        data = {"method": "getHistoryTrend", "key": url, "t": str(int(time.time()*1000))}
        encode = lambda s: quote(s, safe="~()*!.'-")
        signed = SIGNING_VALUE + "".join(encode(k)+encode(data[k]) for k in sorted(data)) + SIGNING_VALUE
        data["token"] = hashlib.md5(signed.upper().encode()).hexdigest().upper()
        client = await self.get_client()
        result = await self.json_request(client, "POST", API, data=data, headers={
            "Authorization": "BasicAuth "+parser.ticket[-4:]+parser.ticket[:-4],
            "Origin": "https://tool.manmanbuy.com", "Referer": HISTORY,
            "X-Requested-With": "XMLHttpRequest"})
        if result in (402, 403, 4030):
            self.state = "verification_required"
            raise HTTPException(409, self.status()["message"])
        if not isinstance(result, dict):
            raise HTTPException(502, "查询结果格式异常")
        if result.get("code") == 4:
            self.state = "expired"
            raise HTTPException(409, self.status()["message"])
        data = result.get("data") or {}
        if data.get("auth"):
            raise HTTPException(409, "该商品平台需要额外授权，请在慢慢买官方页面完成后重试")
        if result.get("code") != 0:
            raise HTTPException(502, "慢慢买暂时未能返回价格数据")
        return {"source": "manmanbuy", "queried_at": int(time.time()),
                "has_history": data.get("haveTrend") == 1,
                "product_name": data.get("spName"), "lowest_price": data.get("lowerPrice"),
                "lowest_date": data.get("lowerDate"), "average_60_days": data.get("avgPrice60"),
                "coverage": "来源标注近13个月；实际数据覆盖可能更短"}

    async def close(self):
        if self.watch_task and not self.watch_task.done():
            self.watch_task.cancel()
            await asyncio.gather(self.watch_task, return_exceptions=True)
        self.watch_task = None
        await self.clear_pending()
        if self.client:
            await self.client.close()
        await self.notifier.close()
        await self.dingtalk_notifier.close()
        await self.wechat_notifier.close()
        await self.wxpusher_notifier.close()


def install(app, directory, database=None):
    connection = Connection(directory, database)
    async def same_origin(request: Request):
        origin = request.headers.get("origin")
        if request.method != "GET" and origin and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "请从本服务页面操作")

    router = APIRouter(prefix="/api/manmanbuy", dependencies=[Depends(same_origin)])

    async def run(action):
        async with connection.lock:
            try:
                return await action()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                connection.last_error = "连接暂时失败，已保留登录状态，请稍后重试"
                raise HTTPException(502, connection.last_error) from None

    @router.get("/status")
    async def status():
        async with connection.lock:
            await connection.get_client()
            if connection.pending and time.monotonic() >= connection.pending["deadline"]:
                await connection.clear_pending()
        if (connection.path.exists() and connection.state != "verification_required"
                and (connection.checked_at is None or time.time()-connection.checked_at > 21600)):
            try:
                await run(connection.validate)
            except HTTPException:
                pass
        return connection.status()

    @router.get("/alerts")
    async def alert_settings():
        return {"settings": connection.alert_settings().model_dump(),
                "available": connection.available_channels()}

    @router.put("/alerts")
    async def update_alert_settings(settings: AlertSettings):
        if database is None:
            raise HTTPException(503, "通知设置不可用")
        if settings.enabled:
            if not settings.channels:
                raise HTTPException(422, "请至少选择一个通知渠道")
            available = connection.available_channels()
            missing = [channel for channel in settings.channels if not available.get(channel)]
            if missing:
                raise HTTPException(422, "所选通知渠道尚未配置：" + "、".join(missing))
            if "wechat" in settings.channels and not settings.wechat_targets.strip():
                raise HTTPException(422, "请选择微信会话")
        database.set_config("manmanbuy_alert", settings.model_dump_json(),
                            "ManManBuy session alert settings")
        return {"settings": settings.model_dump(), "available": connection.available_channels()}

    @router.post("/login")
    async def login():
        return await run(connection.start_login)

    @router.get("/login/{login_id}")
    async def poll(login_id: str):
        return await run(lambda: connection.poll_login(login_id))

    @router.post("/validate")
    async def validate():
        return await run(connection.validate)

    @router.post("/query")
    async def query(request: QueryRequest):
        result = await run(lambda: connection.query(request.url))
        if database is not None:
            database.record_historical_price_check(request.url, result)
        return result

    @router.delete("/session")
    async def disconnect():
        async with connection.lock:
            await connection.close()
            connection.path.unlink(missing_ok=True)
            connection.clear_alert()
            connection.client = None
            connection.state = "disconnected"
            connection.checked_at = None
            connection.last_error = None
        return connection.status()

    app.include_router(router)
    if database is not None:
        @app.on_event("startup")
        async def start_session_watch():
            connection.watch_task = asyncio.create_task(
                connection.watch_session(), name="manmanbuy-session-watch")
    app.on_event("shutdown")(connection.close)
    return connection
