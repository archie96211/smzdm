#!/usr/bin/env python3
"""Headless development entrypoint for the SMZDM monitor server."""

from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from src import runtime
from src import web_server


logger = logging.getLogger(__name__)


async def main_async() -> None:
    runtime.ensure_runtime_dirs()
    runtime.configure_logging()
    host = runtime.get_server_host()
    port = runtime.get_server_port()
    web_server.configure_runtime(host, port, auto_start=True)

    config = uvicorn.Config(
        web_server.app,
        host=host,
        port=port,
        access_log=True,
        log_level="info",
    )
    server = uvicorn.Server(config)

    stop_event = asyncio.Event()

    def request_shutdown(*_: object) -> None:
        logger.info("收到关闭信号，正在退出...")
        server.should_exit = True
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_shutdown)
        except ValueError:
            pass

    server_task = asyncio.create_task(server.serve())
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {server_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if stop_task in done:
        server.should_exit = True
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.gather(server_task, return_exceptions=True)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
