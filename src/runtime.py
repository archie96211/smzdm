#!/usr/bin/env python3
"""Runtime paths and process-wide settings for development and packaged EXE."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
import os
import socket
import sys
from pathlib import Path


APP_NAME = "smzdm_monitor"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18080

_server_host = os.getenv("HOST", DEFAULT_HOST)
_server_port = int(os.getenv("PORT", str(DEFAULT_PORT)))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return get_project_root()


def get_resource_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS).resolve()
    return get_project_root()


def get_data_dir() -> Path:
    override = os.getenv("SMZDM_DATA_DIR")
    return Path(override).resolve() if override else get_app_root() / "data"


def get_images_dir() -> Path:
    return get_data_dir() / "images"


def get_log_dir() -> Path:
    override = os.getenv("SMZDM_LOG_DIR")
    return Path(override).resolve() if override else get_app_root() / "logs"


def get_database_path() -> Path:
    override = os.getenv("DATABASE_PATH")
    return Path(override).resolve() if override else get_data_dir() / "smzdm_monitor.db"


def get_log_file() -> Path:
    override = os.getenv("LOG_FILE")
    return Path(override).resolve() if override else get_log_dir() / "smzdm_monitor.log"


def get_static_dir() -> Path:
    return get_resource_root() / "static"


def ensure_runtime_dirs() -> None:
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_images_dir().mkdir(parents=True, exist_ok=True)
    get_log_dir().mkdir(parents=True, exist_ok=True)


def configure_logging(level: str | None = None) -> None:
    ensure_runtime_dirs()
    log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(log_level)
        return
    handlers: list[logging.Handler] = []
    stream = getattr(sys, "stdout", None) or getattr(sys, "stderr", None)
    if stream and hasattr(stream, "write"):
        handlers.append(logging.StreamHandler(stream))
    backup_count = int(os.getenv("LOG_BACKUP_DAYS", "14"))
    handlers.append(
        TimedRotatingFileHandler(
            get_log_file(),
            when="midnight",
            interval=1,
            backupCount=max(1, backup_count),
            encoding="utf-8",
        )
    )
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def set_server_address(host: str, port: int) -> None:
    global _server_host, _server_port
    _server_host = host
    _server_port = int(port)


def get_server_host() -> str:
    return _server_host


def get_server_port() -> int:
    return _server_port


def get_server_base_url() -> str:
    return f"http://{_server_host}:{_server_port}"


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def find_available_port(host: str = DEFAULT_HOST, start: int = DEFAULT_PORT, end: int = 8099) -> int:
    for port in range(start, end + 1):
        if is_port_available(host, port):
            return port
    raise RuntimeError(f"No available port found in {start}-{end}")
