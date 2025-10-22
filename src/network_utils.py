"""Network helpers for public image URLs and Tencent Cloud metadata."""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import urllib.request
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

TENCENT_PUBLIC_IP_ENDPOINTS = (
    "http://metadata.tencentyun.com/latest/meta-data/public-ipv4",
    "http://metadata.tencentyun.com/meta-data/public-ipv4",
)

PUBLIC_IP_FALLBACK_ENDPOINTS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
)


def _extract_hostname(host_or_url: str) -> str:
    value = (host_or_url or "").strip().strip("[]")
    if not value:
        return ""
    if "://" in value:
        parsed = urlparse(value)
    else:
        parsed = urlparse(f"//{value}", scheme="http")
    return (parsed.hostname or value).strip("[]").lower()


def _read_url(url: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "SMZDMMonitor/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(64).decode("utf-8", errors="ignore").strip()


def parse_public_ipv4(value: str) -> str:
    candidate = (value or "").strip()
    match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", candidate)
    if not match:
        return ""
    try:
        ip = ipaddress.ip_address(match.group(0))
    except ValueError:
        return ""
    if ip.version == 4 and ip.is_global:
        return str(ip)
    return ""


def is_public_host(host_or_url: str) -> bool:
    host = _extract_hostname(host_or_url)
    if not host or host in {"localhost"}:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host and not host.endswith(".local")


def is_loopback_host(host_or_url: str) -> bool:
    host = _extract_hostname(host_or_url)
    if not host or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and is_public_host(parsed.hostname or "")


def detect_public_ipv4(timeout: float = 1.0, allow_external_fallback: bool = True) -> str:
    env_ip = parse_public_ipv4(os.getenv("SMZDM_PUBLIC_IP", ""))
    if env_ip:
        return env_ip

    for endpoint in TENCENT_PUBLIC_IP_ENDPOINTS:
        try:
            public_ip = parse_public_ipv4(_read_url(endpoint, timeout))
            if public_ip:
                logger.info("Detected Tencent Cloud public IPv4: %s", public_ip)
                return public_ip
        except Exception as exc:
            logger.debug("Tencent metadata public IP lookup failed at %s: %s", endpoint, exc)

    if not allow_external_fallback:
        return ""

    for endpoint in PUBLIC_IP_FALLBACK_ENDPOINTS:
        try:
            public_ip = parse_public_ipv4(_read_url(endpoint, timeout))
            if public_ip:
                logger.info("Detected public IPv4 from fallback endpoint: %s", public_ip)
                return public_ip
        except Exception as exc:
            logger.debug("External public IP lookup failed at %s: %s", endpoint, exc)

    return ""
