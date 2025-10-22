#!/usr/bin/env python3
"""FastAPI server for the SMZDM monitor desktop app."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import runtime
from .database import DatabaseManager
from .dingtalk_notifier import DingTalkNotifier
from .monitor import SMZDMMonitor
from .network_utils import detect_public_ipv4, is_loopback_host
from .wechat_bridge_manager import WeChatBridgeManager


logger = logging.getLogger(__name__)

app = FastAPI(title="什么值得买好价监控系统", version="2.0.0")

db = DatabaseManager(str(runtime.get_database_path()))
notifier = DingTalkNotifier()
monitor = SMZDMMonitor(str(runtime.get_database_path()), notifier=notifier)
wechat_bridge = WeChatBridgeManager()
monitor_task: Optional[asyncio.Task] = None
auto_start_task: Optional[asyncio.Task] = None
monitor_start_lock = asyncio.Lock()
auto_start_monitor = os.getenv("AUTO_START_MONITOR", "true").lower() == "true"
allow_public_api = os.getenv("SMZDM_ALLOW_PUBLIC_API", "").lower() in {"1", "true", "yes"}


class SchemeCreate(BaseModel):
    name: str
    description: str = ""
    keyword: str = ""
    refresh_interval: int = 60
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""
    wechat_enabled: bool = False
    wechat_account_id: str = ""
    wechat_targets: str = ""


class SchemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    refresh_interval: Optional[int] = None
    dingtalk_webhook: Optional[str] = None
    dingtalk_secret: Optional[str] = None
    wechat_enabled: Optional[bool] = None
    wechat_account_id: Optional[str] = None
    wechat_targets: Optional[str] = None
    is_active: Optional[bool] = None


class KeywordCreate(BaseModel):
    keyword: str
    category_id: str = ""
    brand_id: str = ""
    mall_id: str = ""
    order_type: str = "time"
    price_min: float = 0
    price_max: float = 999999


class KeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    mall_id: Optional[str] = None
    order_type: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    is_active: Optional[bool] = None


class TestWebhookRequest(BaseModel):
    webhook_url: str
    secret: str = ""


class TestWeChatRequest(BaseModel):
    account_id: str = ""
    conversation_id: str = ""
    targets: str = ""
    text: str = "SMZDM Monitor WeChat test"
    media_url: str = ""
    media_path: str = ""


class GlobalSettingsUpdate(BaseModel):
    image_server_host: str = Field(default="127.0.0.1")
    image_server_port: int = Field(default=18080, ge=1, le=65535)
    server_port: int = Field(default=18080, ge=1, le=65535)
    dingtalk_webhook: str = Field(default="")
    dingtalk_secret: str = Field(default="")


async def send_scheme_configured_notice(scheme_id: int) -> None:
    scheme = db.get_scheme(scheme_id)
    if not scheme:
        return

    sent_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"{scheme.get('name', '')} 方案已配置"
    text = "\n".join([
        f"### {title}",
        "",
        f"- **方案**: {scheme.get('name', '')}",
        f"- **发送时间**: {sent_time}",
        "",
        "后续只会在发现新增商品时推送。",
    ])

    webhook = scheme.get("dingtalk_webhook") or db.get_config("dingtalk_webhook") or ""
    secret = scheme.get("dingtalk_secret") or db.get_config("dingtalk_secret") or ""
    if webhook:
        try:
            await notifier.send_message(
                webhook_url=webhook,
                message=text,
                secret=secret,
                message_type="markdown",
                title=title,
            )
        except Exception:
            logger.exception("Failed to send DingTalk scheme configured notice")

    if scheme.get("wechat_enabled") and scheme.get("wechat_targets"):
        try:
            await wechat_bridge.request("POST", "/api/wechat/send", {
                "account_id": str(scheme.get("wechat_account_id") or ""),
                "conversation_id": str(scheme.get("wechat_targets") or ""),
                "text": "\n".join([
                    title,
                    f"方案: {scheme.get('name', '')}",
                    f"发送时间: {sent_time}",
                    "后续只会在发现新增商品时推送。",
                ]),
            })
        except Exception:
            logger.exception("Failed to send WeChat scheme configured notice")


def configure_runtime(host: str, port: int, auto_start: bool = True) -> None:
    """Configure server address before uvicorn starts."""
    global auto_start_monitor
    runtime.set_server_address(host, port)
    auto_start_monitor = auto_start


def _mount_static() -> None:
    static_dir = runtime.get_static_dir()
    images_dir = runtime.get_images_dir()
    static_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")


_mount_static()


@app.middleware("http")
async def limit_public_access(request: Request, call_next):
    client_host = request.client.host if request.client else ""
    if allow_public_api or is_loopback_host(client_host) or request.url.path.startswith("/images/"):
        return await call_next(request)
    return JSONResponse(
        {"success": False, "message": "公网访问默认只开放图片缓存 /images/。"},
        status_code=403,
    )


def _setting_value(settings: dict, key: str, default: str = "") -> str:
    value = settings.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value") or default)
    return default


def configure_image_server_defaults() -> None:
    settings = db.get_global_settings()
    current_port = _setting_value(settings, "image_server_port", str(runtime.get_server_port()))

    updates = {}
    env_host = os.getenv("SMZDM_IMAGE_SERVER_HOST", "").strip()
    env_port = os.getenv("SMZDM_IMAGE_SERVER_PORT", "").strip()
    detected_ip = ""

    if env_host:
        updates["image_server_host"] = env_host
    else:
        detected_ip = detect_public_ipv4(timeout=1.0)
        if detected_ip:
            updates["image_server_host"] = detected_ip

    if env_port:
        updates["image_server_port"] = env_port
    elif current_port != str(runtime.get_server_port()):
        updates["image_server_port"] = str(runtime.get_server_port())

    if updates:
        db.update_global_settings(updates)
        logger.info("Image server public settings updated: %s", updates)


async def _ensure_monitor_started() -> bool:
    global monitor_task
    async with monitor_start_lock:
        if monitor_task and monitor_task.done():
            try:
                monitor_task.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Monitor task stopped unexpectedly")
            monitor_task = None
            monitor.running = False

        if monitor.running and monitor_task and not monitor_task.done():
            return True

        active_schemes = [
            scheme for scheme in db.get_schemes()
            if scheme["is_active"] and db.get_keywords(scheme["id"])
        ]
        if not active_schemes:
            monitor.running = False
            return False

        monitor_task = asyncio.create_task(monitor.start_monitoring(), name="smzdm-monitor")
        logger.info("Monitor auto-start queued for %s active scheme(s)", len(active_schemes))
        return True


async def _auto_start_monitor_later() -> None:
    delay = float(os.getenv("SMZDM_AUTO_START_DELAY", "4"))
    if delay > 0:
        logger.info("Monitor auto-start delayed by %.1fs to keep the desktop UI responsive", delay)
        await asyncio.sleep(delay)
    await _ensure_monitor_started()


async def _stop_monitor_task() -> None:
    global monitor_task
    if monitor.running:
        await monitor.stop_monitoring()
    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
        await asyncio.gather(monitor_task, return_exceptions=True)
    monitor_task = None


async def _stop_scheme_task(scheme_id: int) -> None:
    task = monitor.tasks.pop(scheme_id, None)
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _sync_scheme_monitor_state(scheme_id: int, update_data: dict) -> None:
    if "is_active" in update_data:
        if update_data["is_active"]:
            if monitor.running and monitor_task and not monitor_task.done():
                if scheme_id not in monitor.tasks and db.get_keywords(scheme_id):
                    await monitor.restart_scheme(scheme_id)
            else:
                await _ensure_monitor_started()
        else:
            await _stop_scheme_task(scheme_id)
            if monitor.running and not monitor.tasks:
                await _stop_monitor_task()
        return

    if monitor.running and scheme_id in monitor.tasks:
        await monitor.restart_scheme(scheme_id)


@app.get("/api/health")
async def health():
    return {"success": True, "status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_path = runtime.get_static_dir() / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<html><body><h1>SMZDM Monitor</h1><p>前端资源尚未构建，请运行 npm run build。</p></body></html>"
    )


@app.get("/api/schemes")
async def get_schemes():
    return {"success": True, "data": db.get_schemes()}


@app.get("/api/schemes/{scheme_id}")
async def get_scheme(scheme_id: int):
    scheme = db.get_scheme(scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="方案不存在")
    scheme["keywords"] = db.get_keywords(scheme_id)
    scheme["recent_products"] = db.get_recent_products(scheme_id, 50)
    scheme["notification_stats"] = db.get_notification_stats(scheme_id)
    return {"success": True, "data": scheme}


@app.post("/api/schemes")
async def create_scheme(scheme: SchemeCreate):
    try:
        name = scheme.name.strip()
        initial_keyword = scheme.keyword.strip()
        wechat_targets = scheme.wechat_targets.strip()
        if not name:
            raise ValueError("方案名称不能为空")
        if not initial_keyword:
            raise ValueError("新建方案必须填写关键词")
        scheme_id = db.create_scheme(
            name=name,
            description=scheme.description,
            refresh_interval=scheme.refresh_interval,
            dingtalk_webhook=scheme.dingtalk_webhook.strip(),
            dingtalk_secret=scheme.dingtalk_secret.strip(),
            wechat_enabled=scheme.wechat_enabled,
            wechat_account_id=scheme.wechat_account_id.strip(),
            wechat_targets=wechat_targets,
        )
        db.add_keyword(scheme_id, initial_keyword)
        await send_scheme_configured_notice(scheme_id)
        if monitor.running and monitor_task and not monitor_task.done():
            await monitor.restart_scheme(scheme_id)
        else:
            await _ensure_monitor_started()
        return {"success": True, "data": {"id": scheme_id}}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/schemes/{scheme_id}")
async def update_scheme(scheme_id: int, scheme: SchemeUpdate):
    update_data = {key: value for key, value in scheme.model_dump().items() if value is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="没有提供更新数据")
    existing_scheme = db.get_scheme(scheme_id)
    if not existing_scheme:
        raise HTTPException(status_code=404, detail="方案不存在")
    next_wechat_enabled = update_data.get("wechat_enabled", existing_scheme.get("wechat_enabled"))
    next_wechat_targets = str(update_data.get("wechat_targets", existing_scheme.get("wechat_targets") or "")).strip()
    if "wechat_targets" in update_data or next_wechat_enabled:
        update_data["wechat_targets"] = next_wechat_targets
    if not db.update_scheme(scheme_id, **update_data):
        raise HTTPException(status_code=404, detail="方案不存在")
    await _sync_scheme_monitor_state(scheme_id, update_data)
    return {"success": True, "message": "方案更新成功"}


@app.delete("/api/schemes/{scheme_id}")
async def delete_scheme(scheme_id: int):
    if not db.delete_scheme(scheme_id):
        raise HTTPException(status_code=404, detail="方案不存在")
    await _stop_scheme_task(scheme_id)
    if monitor.running and not monitor.tasks:
        await _stop_monitor_task()
    return {"success": True, "message": "方案删除成功"}


@app.get("/api/schemes/{scheme_id}/keywords")
async def get_keywords(scheme_id: int):
    return {"success": True, "data": db.get_keywords(scheme_id)}


@app.post("/api/schemes/{scheme_id}/keywords")
async def add_keyword(scheme_id: int, keyword: KeywordCreate):
    if not db.get_scheme(scheme_id):
        raise HTTPException(status_code=404, detail="方案不存在")
    try:
        keyword_value = keyword.keyword.strip()
        if not keyword_value:
            raise ValueError("关键词不能为空")
        keyword_id = db.add_keyword(
            scheme_id=scheme_id,
            keyword=keyword_value,
            category_id=keyword.category_id,
            brand_id=keyword.brand_id,
            mall_id=keyword.mall_id,
            order_type=keyword.order_type,
            price_min=keyword.price_min,
            price_max=keyword.price_max,
        )
        if monitor.running and scheme_id not in monitor.tasks:
            await monitor.restart_scheme(scheme_id)
        elif not monitor.running:
            await _ensure_monitor_started()
        return {"success": True, "data": {"id": keyword_id}}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/keywords/{keyword_id}")
async def update_keyword(keyword_id: int, keyword: KeywordUpdate):
    update_data = {key: value for key, value in keyword.model_dump().items() if value is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="没有提供更新数据")
    if not db.update_keyword(keyword_id, **update_data):
        raise HTTPException(status_code=404, detail="关键词不存在")
    return {"success": True, "message": "关键词更新成功"}


@app.delete("/api/keywords/{keyword_id}")
async def delete_keyword(keyword_id: int):
    if not db.delete_keyword(keyword_id):
        raise HTTPException(status_code=404, detail="关键词不存在")
    return {"success": True, "message": "关键词删除成功"}


@app.get("/api/schemes/{scheme_id}/products")
async def get_products(scheme_id: int, limit: int = 50):
    return {"success": True, "data": db.get_recent_products(scheme_id, limit)}


@app.get("/api/monitor/status")
async def get_monitor_status():
    return {"success": True, "data": monitor.get_status()}


@app.post("/api/schemes/{scheme_id}/restart")
async def restart_scheme_monitor(scheme_id: int):
    if not db.get_scheme(scheme_id):
        raise HTTPException(status_code=404, detail="方案不存在")
    if not monitor.running:
        await _ensure_monitor_started()
    else:
        await monitor.restart_scheme(scheme_id)
    return {"success": True, "message": "方案监控已重启"}


@app.post("/api/test-webhook")
async def test_webhook(request: TestWebhookRequest):
    try:
        result = await notifier.test_webhook(request.webhook_url, request.secret)
        return {"success": result, "message": "测试成功" if result else "测试失败"}
    except Exception as exc:
        return {"success": False, "message": f"测试失败: {exc}"}


@app.get("/api/wechat/status")
async def get_wechat_status():
    return {"success": True, "data": await wechat_bridge.status()}


@app.get("/api/wechat/account")
async def get_wechat_account():
    try:
        account = await wechat_bridge._fetch_account()
        return {"success": True, "data": account}
    except Exception as exc:
        return {"success": False, "message": str(exc), "data": None}


@app.post("/api/wechat/reload")
async def reload_wechat_accounts():
    result = await wechat_bridge.request("POST", "/api/wechat/reload")
    wechat_bridge._invalidate_cache()
    return result


@app.get("/api/wechat/conversations")
async def get_wechat_conversations(account_id: str = ""):
    suffix = f"?account_id={account_id.strip()}" if account_id.strip() else ""
    return await wechat_bridge.request("GET", f"/api/wechat/conversations{suffix}")


class ConversationRemarkUpdate(BaseModel):
    remark: str = ""


@app.put("/api/wechat/conversations/{conversation_id}/remark")
async def set_conversation_remark(conversation_id: str, body: ConversationRemarkUpdate):
    return await wechat_bridge.request("PUT", f"/api/wechat/conversations/{conversation_id}/remark", {"remark": body.remark.strip()})


@app.post("/api/wechat/login/start")
async def start_wechat_login():
    return await wechat_bridge.request("POST", "/api/wechat/login/start")


@app.get("/api/wechat/login/status/{login_id}")
async def get_wechat_login_status(login_id: str):
    return await wechat_bridge.request("GET", f"/api/wechat/login/status/{login_id}")


@app.post("/api/wechat/login/cancel/{login_id}")
async def cancel_wechat_login(login_id: str):
    return await wechat_bridge.request("POST", f"/api/wechat/login/cancel/{login_id}")


@app.post("/api/test-wechat")
async def test_wechat(request: TestWeChatRequest):
    try:
        data = await wechat_bridge.request("POST", "/api/wechat/send", {
            "account_id": request.account_id.strip(),
            "conversation_id": request.conversation_id.strip(),
            "targets": request.targets.strip(),
            "text": request.text.strip() or "SMZDM Monitor WeChat test",
            "media_url": request.media_url.strip(),
            "media_path": request.media_path.strip(),
        })
        return {"success": bool(data.get("success")), "message": "微信测试发送成功", "data": data}
    except Exception as exc:
        return {"success": False, "message": f"微信测试发送失败: {exc}"}


@app.get("/api/system/info")
async def get_system_info():
    schemes = db.get_schemes()
    total_keywords = sum(len(db.get_keywords(scheme["id"])) for scheme in schemes)
    return {
        "success": True,
        "data": {
            "total_schemes": len(schemes),
            "active_schemes": len([scheme for scheme in schemes if scheme["is_active"]]),
            "total_keywords": total_keywords,
            "monitor_running": monitor.running,
            "running_tasks": len(monitor.tasks),
            "database_path": str(runtime.get_database_path()),
            "data_dir": str(runtime.get_data_dir()),
            "log_file": str(runtime.get_log_file()),
            "server_url": runtime.get_server_base_url(),
        },
    }


@app.get("/api/global-settings")
async def get_global_settings():
    return {"success": True, "data": db.get_global_settings()}


@app.put("/api/global-settings")
async def update_global_settings(settings: GlobalSettingsUpdate):
    db.update_global_settings(settings.model_dump())
    return {"success": True, "message": "全局设置已更新", "data": db.get_global_settings()}


# Reference to uvicorn Server instance, set by run_server_mode or __main__
_uvicorn_server = None


@app.post("/api/desktop/shutdown")
async def desktop_shutdown():
    """Graceful shutdown endpoint for desktop shell."""
    logger.info("Backend graceful shutdown requested by desktop shell")
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
    else:
        import signal
        os.kill(os.getpid(), signal.SIGTERM)
    return {"success": True}


class ServerPortUpdate(BaseModel):
    port: int = Field(ge=1, le=65535)


@app.post("/api/server/restart")
async def restart_server(request: ServerPortUpdate):
    """Save new port and trigger server restart."""
    old_port = runtime.get_server_port()
    new_port = request.port
    db.update_global_settings({"server_port": str(new_port)})
    runtime.set_server_address(runtime.get_server_host(), new_port)
    logger.info("Server restart requested: port %s -> %s", old_port, new_port)
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
    else:
        import signal
        os.kill(os.getpid(), signal.SIGTERM)
    return {"success": True, "message": "服务端口已更新，正在重启...", "new_port": new_port}


@app.on_event("startup")
async def startup_event():
    global auto_start_task
    runtime.ensure_runtime_dirs()
    configure_image_server_defaults()
    await wechat_bridge.start()
    logger.info("SMZDM Web server started at %s", runtime.get_server_base_url())
    if auto_start_monitor:
        auto_start_task = asyncio.create_task(_auto_start_monitor_later(), name="smzdm-monitor-auto-start")


@app.on_event("shutdown")
async def shutdown_event():
    global auto_start_task
    logger.info("SMZDM Web server shutting down")
    if auto_start_task and not auto_start_task.done():
        auto_start_task.cancel()
        await asyncio.gather(auto_start_task, return_exceptions=True)
    auto_start_task = None
    await _stop_monitor_task()
    await notifier.close()
    await wechat_bridge.stop()


if __name__ == "__main__":
    import uvicorn

    runtime.configure_logging()
    runtime.set_server_address(runtime.DEFAULT_HOST, runtime.DEFAULT_PORT)
    uvicorn.run(app, host=runtime.DEFAULT_HOST, port=runtime.DEFAULT_PORT, log_level="info")
