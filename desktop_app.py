#!/usr/bin/env python3
"""Windows desktop entrypoint: FastAPI backend + browser UI + tray."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import winreg
from pathlib import Path


WEBVIEW2_LOW_RESOURCE_ARGS = " ".join(
    [
        "--disable-features=ElasticOverscroll,msWebOOUI",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-extensions",
        "--disable-sync",
        "--disable-gpu",
        "--no-first-run",
    ]
)


def configure_process_environment() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", WEBVIEW2_LOW_RESOURCE_ARGS)
    os.environ.setdefault("SMZDM_AUTO_START_DELAY", "4")
    os.environ.setdefault("SMZDM_MONITOR_CONCURRENCY", "3")


configure_process_environment()

import pystray
from PIL import Image, ImageDraw

from src import runtime


logger = logging.getLogger(__name__)

SW_RESTORE = 9
SW_SHOW = 5
HWND_TOP = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040


class DesktopApi:
    def __init__(self, controller: "DesktopController") -> None:
        self.controller = controller

    def getAppInfo(self) -> dict:
        return {
            "name": "什么值得买好价监控",
            "version": "2.0.0",
            "serverUrl": self.controller.url,
            "dataDir": str(runtime.get_data_dir()),
            "logFile": str(runtime.get_log_file()),
            "isPackaged": runtime.is_frozen(),
        }

    def minimizeToTray(self) -> dict:
        self.controller.hide_window(show_notice=True)
        return {"success": True}

    def openExternal(self, url: str) -> dict:
        webbrowser.open(url)
        return {"success": True}

    def quitApp(self) -> dict:
        self.controller.quit()
        return {"success": True}


class DesktopController:
    def __init__(
        self,
        debug: bool = False,
        browser_mode: bool = True,
        auto_start_monitor: bool = True,
    ) -> None:
        self.debug = debug
        browser_env = os.getenv("SMZDM_BROWSER_MODE", "").lower() in {"1", "true", "yes"}
        self.browser_mode = browser_mode or browser_env
        self.auto_start_monitor = auto_start_monitor and os.getenv("SMZDM_NO_AUTO_MONITOR", "").lower() not in {"1", "true", "yes"}
        self.host = runtime.DEFAULT_HOST
        self.bind_host = os.getenv("SMZDM_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0"
        self.port = self._load_port_from_db()
        runtime.set_server_address(self.host, self.port)
        self.url = runtime.get_server_base_url()
        self.backend_process: subprocess.Popen | None = None
        self.tray_icon: pystray.Icon | None = None
        self.window = None
        self.quitting = False
        self.hidden_to_tray = False
        self.backend_error: Exception | None = None
        self.fallback_mode = False
        self.quit_event = threading.Event()
        self.webview_loaded = threading.Event()
        self._restart_lock = threading.Lock()

    def run(self) -> None:
        runtime.ensure_runtime_dirs()
        runtime.configure_logging()
        logger.info(
            "Desktop app starting. app_root=%s data_dir=%s log_file=%s url=%s bind_host=%s browser_mode=%s auto_start_monitor=%s",
            runtime.get_app_root(),
            runtime.get_data_dir(),
            runtime.get_log_file(),
            self.url,
            self.bind_host,
            self.browser_mode,
            self.auto_start_monitor,
        )
        self.start_backend()
        self.wait_for_backend()
        self.start_tray()
        if self.browser_mode:
            self.start_browser_fallback("已启用浏览器模式")
        elif has_webview2_runtime():
            self.start_window()
        else:
            self.start_browser_fallback("未检测到 Microsoft Edge WebView2 Runtime")
        self.shutdown()

    def _load_port_from_db(self) -> int:
        """Read server_port from database, falling back to env/default."""
        try:
            from src.database import DatabaseManager
            db = DatabaseManager()
            saved = db.get_config("server_port")
            if saved:
                return int(saved)
        except Exception:
            pass
        return int(os.getenv("SMZDM_PORT", str(runtime.DEFAULT_PORT)))

    def start_backend(self) -> None:
        logger.info("Starting FastAPI backend subprocess on %s", self.url)
        if runtime.is_frozen():
            command = [sys.executable]
        else:
            command = [sys.executable, str(Path(__file__).resolve())]
        command.extend([
            "--server",
            "--host",
            self.bind_host,
            "--port",
            str(self.port),
        ])
        if not self.auto_start_monitor:
            command.append("--no-auto-monitor")

        env = os.environ.copy()
        env.update({
            "HOST": self.bind_host,
            "PORT": str(self.port),
            "AUTO_START_MONITOR": "true" if self.auto_start_monitor else "false",
        })
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.backend_process = subprocess.Popen(
            command,
            cwd=str(runtime.get_app_root()),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        logger.info("Backend subprocess started with pid=%s", self.backend_process.pid)
        monitor = threading.Thread(target=self._monitor_backend, daemon=True)
        monitor.start()

    def _monitor_backend(self) -> None:
        """Watch backend process; restart if it exits unexpectedly (e.g. port change)."""
        if not self.backend_process:
            return
        self.backend_process.wait()
        if self.quitting:
            return
        with self._restart_lock:
            if self.quitting or not self.backend_process:
                return
            logger.info("Backend exited unexpectedly (code=%s); checking for port change...", self.backend_process.returncode)
            self.backend_process = None
            new_port = self._load_port_from_db()
            if new_port != self.port:
                logger.info("Port changed %s -> %s, restarting backend", self.port, new_port)
                self.port = new_port
                runtime.set_server_address(self.host, new_port)
                self.url = runtime.get_server_base_url()
            self.start_backend()
            try:
                self.wait_for_backend()
                logger.info("Backend restarted successfully at %s", self.url)
            except Exception as exc:
                logger.error("Backend restart failed: %s", exc)
                self.backend_error = exc

    def wait_for_backend(self, timeout: float = 25.0) -> None:
        deadline = time.time() + timeout
        health_url = f"{self.url}/api/health"
        while time.time() < deadline:
            if self.backend_process and self.backend_process.poll() is not None:
                raise RuntimeError(f"后端服务进程提前退出，退出码: {self.backend_process.returncode}")
            try:
                with urllib.request.urlopen(health_url, timeout=0.5) as response:
                    if response.status == 200:
                        logger.info("Backend is ready at %s", health_url)
                        return
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.2)
        raise TimeoutError("后端服务启动超时")

    def start_window(self) -> None:
        logger.info("Creating PyWebView window")
        import webview

        patch_pywebview_winforms_message_loop()
        api = DesktopApi(self)
        self.window = webview.create_window(
            "什么值得买好价监控",
            self.url,
            js_api=api,
            width=1240,
            height=820,
            min_size=(1040, 680),
            background_color="#0f172a",
            text_select=True,
        )
        self.window.events.closing += self.on_window_closing
        self.window.events.minimized += self.on_window_minimized
        self.window.events.shown += self.on_window_shown
        self.window.events.loaded += self.on_window_loaded
        threading.Thread(target=self.webview_watchdog, name="smzdm-webview-watchdog", daemon=True).start()
        storage_path = str(runtime.get_app_root() / "webview_profile")
        webview.start(
            debug=self.debug,
            gui="edgechromium",
            private_mode=False,
            storage_path=storage_path,
            user_agent="SMZDMMonitor/2.0",
        )
        logger.info("PyWebView event loop stopped")

    def start_browser_fallback(self, reason: str) -> None:
        self.fallback_mode = True
        logger.warning("%s，已打开浏览器兜底：%s", reason, self.url)
        try:
            if self.tray_icon:
                self.tray_icon.notify(f"{reason}，已改用浏览器打开管理页。", "SMZDM Monitor")
        except Exception:
            logger.debug("系统托盘通知不可用", exc_info=True)
        webbrowser.open(self.url)
        while not self.quit_event.wait(0.5):
            pass

    def on_window_shown(self) -> None:
        logger.info("PyWebView window shown")

    def on_window_loaded(self) -> None:
        logger.info("PyWebView content loaded")
        self.webview_loaded.set()

    def webview_watchdog(self) -> None:
        timeout = float(os.getenv("SMZDM_WEBVIEW_LOAD_TIMEOUT", "18"))
        if self.webview_loaded.wait(timeout) or self.quitting:
            return
        logger.warning("PyWebView loaded event was not received within %.1fs. Keeping the embedded window active.", timeout)
        try:
            if self.tray_icon:
                self.tray_icon.notify("内置窗口仍在运行；如页面空白，可从托盘选择“浏览器打开管理页”。", "SMZDM Monitor")
        except Exception:
            logger.debug("系统托盘通知不可用", exc_info=True)

    def on_window_closing(self) -> bool:
        if self.quitting:
            return True
        logger.info("Window close requested; hiding to tray")
        self.schedule_hide(show_notice=True)
        return False

    def on_window_minimized(self) -> None:
        if not self.quitting:
            logger.info("Window minimized; hiding to tray")
            self.schedule_hide(show_notice=False)

    def schedule_hide(self, show_notice: bool = False) -> None:
        def runner() -> None:
            time.sleep(0.08)
            self.hide_window(show_notice=show_notice)

        threading.Thread(target=runner, name="smzdm-hide-window", daemon=True).start()

    def hide_window(self, show_notice: bool = False) -> None:
        if self.hidden_to_tray:
            return
        self.hidden_to_tray = True
        if self.window:
            try:
                self.window.hide()
                logger.info("Window hidden to tray")
            except Exception:
                logger.debug("隐藏窗口失败", exc_info=True)
        if show_notice and self.tray_icon:
            try:
                self.tray_icon.notify("程序已隐藏到托盘，监控仍在后台运行。", "SMZDM Monitor")
            except Exception:
                logger.debug("系统托盘通知不可用", exc_info=True)

    def show_window(self) -> None:
        if not self.window:
            logger.info("No embedded window is available; opening browser management page instead")
            self.open_browser()
            return

        self.hidden_to_tray = False
        def runner() -> None:
            try:
                self.window.show()
                time.sleep(0.05)
                self.window.restore()
                time.sleep(0.05)
                bring_window_to_front("什么值得买好价监控")
                logger.info("Window restored from tray")
            except Exception:
                logger.debug("显示窗口失败", exc_info=True)

        threading.Thread(target=runner, name="smzdm-show-window", daemon=True).start()

    def open_log_dir(self) -> None:
        log_dir = runtime.get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(log_dir))

    def open_browser(self) -> None:
        webbrowser.open(self.url)

    def quit(self) -> None:
        logger.info("Quit requested")
        self.quitting = True
        self.quit_event.set()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                logger.debug("窗口已关闭", exc_info=True)
        self.stop_backend()

    def stop_backend(self) -> None:
        with self._restart_lock:
            if not self.backend_process:
                return

            if self.backend_process.poll() is None:
                try:
                    request = urllib.request.Request(
                        f"{self.url}/api/desktop/shutdown",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(request, timeout=2).read()
                except Exception:
                    logger.debug("Backend graceful shutdown request failed", exc_info=True)

                try:
                    self.backend_process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    logger.warning("Backend did not exit in time; terminating pid=%s", self.backend_process.pid)
                    self.backend_process.terminate()
                    try:
                        self.backend_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logger.warning("Backend did not terminate; killing pid=%s", self.backend_process.pid)
                        self.backend_process.kill()
                        self.backend_process.wait(timeout=3)
            self.backend_process = None

    def shutdown(self) -> None:
        logger.info("Desktop app shutting down")
        self.quitting = True
        if self.tray_icon:
            self.tray_icon.stop()
        self.stop_backend()

    def start_tray(self) -> None:
        logger.info("Starting tray icon")
        image = create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("打开管理页", lambda icon, item: self.open_browser(), default=True),
            pystray.MenuItem("显示内置窗口", lambda icon, item: self.show_window()),
            pystray.MenuItem("查看日志", lambda icon, item: self.open_log_dir()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon, item: self.quit()),
        )
        self.tray_icon = pystray.Icon("smzdm_monitor", image, "什么值得买好价监控", menu)
        self.tray_icon.run_detached()
        logger.info("Tray icon started")


def create_tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=16, fill=(30, 41, 59, 255))
    draw.rounded_rectangle((12, 14, 52, 50), radius=10, fill=(14, 165, 233, 255))
    draw.polygon([(20, 35), (29, 24), (35, 32), (44, 20), (47, 24), (35, 41), (29, 33), (22, 41)], fill=(255, 255, 255, 255))
    draw.ellipse((43, 13, 52, 22), fill=(34, 197, 94, 255))
    return image


def has_webview2_runtime() -> bool:
    if os.getenv("SMZDM_SKIP_WEBVIEW2_CHECK") == "1":
        return True

    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "EdgeWebView" / "Application",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "EdgeWebView" / "Application",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "EdgeWebView" / "Application",
    ]
    if any(path.exists() and any(child.is_dir() for child in path.iterdir()) for path in candidates if str(path)):
        return True

    app_id = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    roots = [
        (winreg.HKEY_CURRENT_USER, fr"Software\Microsoft\EdgeUpdate\Clients\{app_id}"),
        (winreg.HKEY_LOCAL_MACHINE, fr"Software\Microsoft\EdgeUpdate\Clients\{app_id}"),
        (winreg.HKEY_LOCAL_MACHINE, fr"Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{app_id}"),
    ]
    for root, subkey in roots:
        try:
            with winreg.OpenKey(root, subkey) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version:
                    return True
        except OSError:
            continue
    return False


def bring_window_to_front(title: str) -> None:
    if os.name != "nt":
        return

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return

        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.BringWindowToTop(hwnd)
        user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        logger.debug("Bring window to front failed", exc_info=True)


def patch_pywebview_winforms_message_loop() -> None:
    """Release the Python GIL while pywebview waits for the WinForms GUI thread."""
    try:
        import webview.platforms.winforms as winforms
    except Exception:
        logger.exception("Failed to import pywebview WinForms backend for message-loop patch")
        return

    if getattr(winforms, "_smzdm_nonblocking_join_patch", False):
        return

    def create_window(window):
        def create():
            browser = winforms.BrowserView.BrowserForm(window, winforms.cache_dir)
            winforms.BrowserView.instances[window.uid] = browser
            window.events.before_show.set()

            if window.hidden:
                browser.Opacity = 0
                browser.Show()
                browser.Hide()
                browser.Opacity = 1
            elif window.transparent and winforms.is_chromium:
                browser.Show()
                browser.Hide()
            else:
                browser.Show()

            winforms._main_window_created.set()

            if window.uid == "master":

                def timer_tick(sender, e):
                    if winforms._sigint_received:
                        app.Exit()

                timer = winforms.WinForms.Timer()
                timer.Interval = 500
                timer.Tick += timer_tick
                timer.Start()

                app.Run()

        app = winforms.WinForms.Application

        if window.uid == "master":
            winforms.signal.signal(winforms.signal.SIGINT, winforms._sigint_handler)

            if winforms.is_chromium:
                winforms.init_storage()

            if winforms.sys.getwindowsversion().major >= 6:
                winforms.windll.user32.SetProcessDPIAware()

            if winforms.is_cef:
                winforms.CEF.init(window, winforms.cache_dir)

            thread = winforms.Thread(winforms.ThreadStart(create))
            thread.SetApartmentState(winforms.ApartmentState.STA)
            thread.Start()

            while thread.IsAlive:
                time.sleep(0.1)
        else:
            winforms._main_window_created.wait()
            instance = list(winforms.BrowserView.instances.values())[0]
            instance.Invoke(winforms.Func[winforms.Type](create))

    winforms.create_window = create_window
    winforms._smzdm_nonblocking_join_patch = True
    logger.info("Applied pywebview WinForms non-blocking message-loop patch")


def run_server_mode(host: str, port: int, auto_start_monitor: bool, debug: bool = False) -> None:
    runtime.set_server_address(host, port)
    runtime.ensure_runtime_dirs()
    runtime.configure_logging("DEBUG" if debug else None)
    logger.info("Backend server mode starting at %s", runtime.get_server_base_url())

    import uvicorn
    from src import web_server

    web_server.configure_runtime(host, port, auto_start=auto_start_monitor)
    config = uvicorn.Config(
        web_server.app,
        host=host,
        port=port,
        access_log=debug,
        log_level="info" if debug else "warning",
    )
    server = uvicorn.Server(config)
    web_server._uvicorn_server = server

    asyncio.run(server.serve())


def main() -> None:
    parser = argparse.ArgumentParser(description="SMZDM Monitor desktop app")
    parser.add_argument("--debug", action="store_true", help="Enable pywebview dev tools and verbose backend logs")
    parser.add_argument("--browser", action="store_true", help="Open the management UI in the default browser")
    parser.add_argument("--webview", action="store_true", help="Use the embedded PyWebView window instead of the default browser")
    parser.add_argument("--no-auto-monitor", action="store_true", help="Do not auto-start monitoring after backend startup")
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--host", default=runtime.DEFAULT_HOST, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=runtime.DEFAULT_PORT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.server:
        run_server_mode(
            host=args.host,
            port=args.port,
            auto_start_monitor=not args.no_auto_monitor,
            debug=args.debug,
        )
        return

    DesktopController(
        debug=args.debug,
        browser_mode=not args.webview or args.browser,
        auto_start_monitor=not args.no_auto_monitor,
    ).run()


if __name__ == "__main__":
    main()
