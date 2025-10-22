#!/usr/bin/env python3
"""HTTP client for the local WeChat bridge."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import aiohttp


logger = logging.getLogger(__name__)


class WeChatNotifier:
    def __init__(self, bridge_url: str = "http://127.0.0.1:18012", token: str = "") -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.token = token.strip()
        self.session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=45, connect=5, sock_read=35)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Bridge-Token"] = self.token
        return headers

    async def send_message(
        self,
        *,
        account_id: str = "",
        conversation_id: str = "",
        targets: str | Iterable[str] = "",
        text: str = "",
        media_url: str = "",
        media_path: str = "",
    ) -> bool:
        target_list = normalize_targets(targets)
        conversation_id = conversation_id.strip()
        if not conversation_id and not target_list:
            logger.warning("Skip WeChat notification because no conversation is configured")
            return False
        if not text.strip() and not media_url.strip() and not media_path.strip():
            logger.warning("Skip WeChat notification because message is empty")
            return False

        payload = {
            "account_id": account_id.strip(),
            "conversation_id": conversation_id,
            "targets": target_list,
            "text": text.strip(),
            "media_url": media_url.strip(),
            "media_path": media_path.strip(),
        }
        session = await self._get_session()
        async with self._lock:
            try:
                async with session.post(
                    f"{self.bridge_url}/api/wechat/send",
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    data = await response.json(content_type=None)
                    if response.status < 400 and data.get("success"):
                        return True
                    logger.error("WeChat bridge send failed: status=%s data=%s", response.status, data)
                    return False
            except Exception:
                logger.exception("WeChat bridge send request failed")
                return False

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()


def normalize_targets(targets: str | Iterable[str]) -> list[str]:
    if isinstance(targets, str):
        raw_values = [targets]
    else:
        raw_values = list(targets)

    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        for part in str(value).replace("\r", "\n").replace(",", "\n").replace(";", "\n").split("\n"):
            item = part.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return result
