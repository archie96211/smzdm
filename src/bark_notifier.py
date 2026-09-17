#!/usr/bin/env python3
"""Bark HTTP notifications, including client-side AES encryption."""

import base64
import json
import logging
import secrets
import string
from typing import Literal, Optional
from urllib.parse import urlsplit

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)
SECRET_FIELDS = ("device_key", "encryption_key")


class BarkConfig(BaseModel):
    server_url: str = "https://api.day.app"
    device_key: str = Field(default="", max_length=512)
    group: str = Field(default="SMZDM · {scheme}", max_length=200)
    icon: str = Field(default="", max_length=2048)
    image_enabled: bool = False
    sound: str = Field(default="", max_length=100)
    level: Literal["passive", "active", "timeSensitive", "critical"] = "active"
    volume: int = Field(default=5, ge=0, le=10)
    badge: Optional[int] = Field(default=None, ge=0, le=99999)
    archive: Literal["default", "yes", "no"] = "default"
    ttl: Optional[int] = Field(default=None, ge=0, le=315360000)
    open_url: bool = True
    auto_copy: bool = False
    copy_text: str = Field(default="", max_length=500)
    call: bool = False
    encryption: Literal["none", "CBC", "GCM"] = "none"
    encryption_key: str = Field(default="", max_length=128)

    @field_validator("server_url", "icon")
    @classmethod
    def validate_url(cls, value: str, info) -> str:
        value = value.strip().rstrip("/")
        if not value and info.field_name == "icon":
            return value
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
            or (info.field_name == "server_url" and parts.query)
        ):
            raise ValueError(
                "Use an HTTP(S) URL without credentials, query or fragment"
            )
        if info.field_name == "server_url" and parts.path.endswith("/push"):
            raise ValueError(
                "Enter the server base URL without /push or the device key"
            )
        return value

    @field_validator("group", "copy_text")
    @classmethod
    def validate_template(cls, value: str) -> str:
        for _, field, spec, conversion in string.Formatter().parse(value):
            if field is not None and (
                field not in {"scheme", "mall", "keyword", "url"} or spec or conversion
            ):
                raise ValueError(
                    "Supported placeholders: {scheme}, {mall}, {keyword}, {url}"
                )
        return value

    @model_validator(mode="after")
    def validate_encryption(self):
        if self.encryption != "none" and len(
            self.encryption_key.encode("utf-8")
        ) not in {16, 24, 32}:
            raise ValueError("AES key must contain exactly 16, 24 or 32 UTF-8 bytes")
        return self


def public_config(config: BarkConfig) -> dict:
    """Never return saved keys to the browser."""
    result = config.model_dump()
    for field in SECRET_FIELDS:
        result[f"has_{field}"] = bool(result[field])
        result[field] = ""
    return result


def merge_config(values: dict, previous: dict, clear_secrets: list[str]) -> BarkConfig:
    merged = {**previous, **values}
    for field in SECRET_FIELDS:
        if field in clear_secrets:
            merged[field] = ""
        elif not values.get(field):
            merged[field] = previous.get(field, "")
    return BarkConfig.model_validate(merged)


def build_payload(
    config: BarkConfig, title: str, body: str, context: dict, image: str = ""
) -> dict:
    fields = {
        key: str(context.get(key) or "") for key in ("scheme", "mall", "keyword", "url")
    }
    payload = {"title": title, "body": body, "level": config.level}
    group = config.group.format_map(fields)
    if group:
        payload["group"] = group
    if config.icon:
        payload["icon"] = config.icon
    if config.sound:
        payload["sound"] = config.sound
    if config.image_enabled and image and urlsplit(image).scheme in {"http", "https"}:
        payload["image"] = image
    if config.level == "critical":
        payload["volume"] = str(config.volume)
    if config.badge is not None:
        payload["badge"] = config.badge
    if config.archive != "default":
        payload["isArchive"] = "1" if config.archive == "yes" else "0"
    if config.ttl is not None and config.archive != "no":
        payload["ttl"] = config.ttl
    if config.open_url and fields["url"]:
        payload["url"] = fields["url"]
    elif not config.open_url:
        payload["action"] = "none"
    if config.auto_copy:
        payload["autoCopy"] = "1"
    if config.copy_text:
        payload["copy"] = config.copy_text.format_map(fields)
    if config.call:
        payload["call"] = "1"

    if config.encryption != "none":
        # Fresh IV per message; Bark receives it as a UTF-8 string.
        size = 16 if config.encryption == "CBC" else 12
        iv = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(size)
        )
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        key = config.encryption_key.encode("utf-8")
        if config.encryption == "GCM":
            encrypted = AESGCM(key).encrypt(iv.encode("utf-8"), raw, None)
        else:
            padder = padding.PKCS7(128).padder()
            padded = padder.update(raw) + padder.finalize()
            encryptor = Cipher(
                algorithms.AES(key), modes.CBC(iv.encode("utf-8"))
            ).encryptor()
            encrypted = encryptor.update(padded) + encryptor.finalize()
        payload = {"ciphertext": base64.b64encode(encrypted).decode("ascii"), "iv": iv}
    payload["device_key"] = config.device_key
    return payload


class BarkNotifier:
    def __init__(self):
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self.session

    async def send_message(
        self,
        config: BarkConfig,
        title: str,
        body: str,
        context: Optional[dict] = None,
        image: str = "",
    ) -> bool:
        if not config.device_key:
            logger.warning("Bark send skipped: missing device key")
            return False
        try:
            payload = build_payload(config, title, body, context or {}, image)
            # Leave room for the APNs envelope, including encrypted payload expansion.
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 3500:
                logger.warning(
                    "Bark send skipped: payload exceeds notification size budget"
                )
                return False
            session = await self._get_session()
            async with session.post(
                f"{config.server_url}/push", json=payload, allow_redirects=False
            ) as response:
                if response.status != 200:
                    logger.warning("Bark send failed: HTTP %s", response.status)
                    return False
                raw = bytearray()
                async for chunk in response.content.iter_chunked(4096):
                    raw.extend(chunk)
                    if len(raw) > 16384:
                        logger.warning("Bark send failed: response too large")
                        return False
                result = json.loads(raw)
                if isinstance(result, dict) and result.get("code") == 200:
                    logger.info("Bark message accepted by server")
                    return True
                logger.warning("Bark send failed: server rejected notification")
        except Exception as exc:
            # URLs, payloads and server error messages can contain credentials.
            logger.warning("Bark send failed (%s)", type(exc).__name__)
        return False

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
