#!/usr/bin/env python3
"""Headless development entrypoint for the SMZDM monitor server."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from src import runtime
from src import web_server


logger = logging.getLogger(__name__)


async def main_async() -> None:
    runtime.ensure_runtime_dirs()
    runtime.configure_logging()
    host = runtime.get_server_host()
    port = runtime.get_server_port()
    web_server.configure_runtime(host, port, auto_start=os.getenv("AUTO_START_MONITOR", "true").lower() == "true")

    config = uvicorn.Config(
        web_server.app,
        host=host,
        port=port,
        access_log=True,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Uvicorn owns signals and awaits application shutdown before exiting.
    await server.serve()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
