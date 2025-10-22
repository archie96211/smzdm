#!/usr/bin/env python3
"""Process manager and proxy client for the bundled WeChat bridge."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import aiohttp

from . import runtime


logger = logging.getLogger(__name__)


class WeChatBridgeManager:
    def __init__(self) -> None:
        self.addr = os.getenv("WECHAT_BRIDGE_ADDR", "127.0.0.1:18012").strip() or "127.0.0.1:18012"
        self.base_url = f"http://{self.addr}"
        self.token = os.getenv("WECHAT_BRIDGE_TOKEN", "").strip()
        self.process: subprocess.Popen | None = None
        self.started_external = False
        self._session: aiohttp.ClientSession | None = None
        self._status_cache: dict[str, Any] | None = None
        self._status_cache_time: float = 0

    def find_executable(self) -> Path | None:
        candidates = [
            runtime.get_app_root() / "wechat_bridge" / "smzdm_wechat_bridge.exe",
            runtime.get_resource_root() / "wechat_bridge" / "smzdm_wechat_bridge.exe",
            runtime.get_project_root() / "wechat_bridge" / "smzdm_wechat_bridge.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def headers(self) -> dict[str, str]:
        if self.token:
            return {"X-Bridge-Token": self.token}
        return {}

    async def start(self) -> None:
        if await self.is_healthy():
            self.started_external = True
            logger.info("Using existing WeChat bridge at %s", self.base_url)
            return

        exe = self.find_executable()
        if not exe:
            logger.warning("WeChat bridge executable was not found; WeChat features are disabled")
            return

        env = os.environ.copy()
        env["WECHAT_BRIDGE_ADDR"] = self.addr
        env["WECHAT_BRIDGE_DATA_DIR"] = str(runtime.get_data_dir() / "wechat_bridge")
        env["WECHAT_BRIDGE_LOG_DIR"] = str(runtime.get_log_dir())
        if self.token:
            env["WECHAT_BRIDGE_TOKEN"] = self.token

        log_path = runtime.get_log_dir() / "wechat_bridge.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [str(exe)],
            cwd=str(runtime.get_app_root()),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            creationflags=creationflags,
        )
        logger.info("Started WeChat bridge pid=%s at %s", self.process.pid, self.base_url)

        for _ in range(30):
            if await self.is_healthy():
                return
            await asyncio.sleep(0.2)
        logger.warning("WeChat bridge did not become healthy in time")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        return self._session

    async def is_healthy(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=1.5)) as response:
                return response.status == 200
        except Exception:
            return False

    async def request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not await self.is_healthy():
            raise RuntimeError("WeChat bridge is not running")
        url = f"{self.base_url}{path}"
        session = await self._get_session()
        async with session.request(method, url, json=json_body, headers=self.headers()) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(data.get("message") or data.get("detail") or f"HTTP {response.status}")
            return data

    async def _fetch_account(self) -> dict[str, Any] | None:
        """Fetch the single WeChat account from the bridge."""
        try:
            data = await self.request("GET", "/api/wechat/account")
            return data.get("data")
        except Exception:
            logger.debug("Unable to load WeChat account", exc_info=True)
            return None

    async def get_account_status(self) -> dict[str, Any] | None:
        if not await self.is_healthy():
            return None
        return await self._fetch_account()

    def _invalidate_cache(self) -> None:
        self._status_cache = None
        self._status_cache_time = 0

    async def status(self) -> dict[str, Any]:
        now = time.time()
        if self._status_cache is not None and (now - self._status_cache_time) < 2:
            return self._status_cache

        healthy = await self.is_healthy()
        account: dict[str, Any] | None = None
        account_fetch_failed = False
        if healthy:
            try:
                account = await self._fetch_account()
            except Exception:
                logger.debug("Unable to load WeChat account", exc_info=True)
                account_fetch_failed = True

        result = {
            "enabled": self.find_executable() is not None,
            "running": healthy,
            "base_url": self.base_url,
            "started_external": self.started_external,
            "pid": self.process.pid if self.process and self.process.poll() is None else None,
            "account": account,
        }
        if not account_fetch_failed:
            self._status_cache = result
            self._status_cache_time = now
        return result

    async def stop(self) -> None:
        if not self.process or self.started_external:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait, 3)
        self.process = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
