#!/usr/bin/env python3
"""WxPusher 消息推送模块 - 通过 WxPusher 平台推送到微信/APP"""

import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

WXPUSHER_API_URL = "https://wxpusher.zjiecode.com/api/send/message"


class WxPusherNotifier:
    def __init__(self):
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def send_message(
        self,
        app_token: str,
        content: str,
        uid: str = "",
        content_type: int = 3,
        summary: str = "",
        url: str = "",
    ) -> bool:
        if not app_token or not uid:
            logger.warning("WxPusher send skipped: missing app_token or uid")
            return False

        payload = {
            "appToken": app_token,
            "content": content,
            "contentType": content_type,
            "uids": [uid],
        }
        if summary:
            payload["summary"] = summary[:100]
        if url:
            payload["url"] = url

        try:
            session = await self._get_session()
            async with session.post(
                WXPUSHER_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                result = await response.json(content_type=None)
                if result.get("code") == 1000:
                    logger.info("WxPusher message sent successfully")
                    return True
                else:
                    logger.error(
                        "WxPusher send failed: code=%s msg=%s",
                        result.get("code"),
                        result.get("msg", "unknown"),
                    )
                    return False
        except Exception as e:
            logger.error("WxPusher send exception: %s", e)
            return False

    async def send_markdown(
        self, app_token: str, title: str, text: str, uid: str = "", url: str = ""
    ) -> bool:
        return await self.send_message(
            app_token=app_token,
            content=text,
            uid=uid,
            content_type=3,
            summary=title,
            url=url,
        )

    async def test_push(self, app_token: str, uid: str) -> bool:
        content = (
            "## WxPusher 测试消息\n\n"
            "这是一条来自 SMZDM 监控系统的测试消息。\n\n"
            "如果你收到了这条消息，说明 WxPusher 配置成功！"
        )
        return await self.send_message(
            app_token=app_token,
            content=content,
            uid=uid,
            content_type=3,
            summary="SMZDM 测试消息",
        )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
