from __future__ import annotations

import logging
import multiprocessing
import os
import socket
import threading
import time
import webbrowser
from html import escape
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
import webview

from learner_fastapi_firebase.app.config import get_settings


class DesktopApi:
    def open_external_auth(self, url: str) -> bool:
        if not (url.startswith("http://localhost:") or url.startswith("http://127.0.0.1:")):
            raise ValueError("Only local authentication URLs may be opened externally.")
        return bool(webbrowser.open(url, new=1))


def _log_dir() -> Path:
    configured = os.getenv("STOCKSIGHT_LOG_DIR")
    if configured:
        return Path(configured).expanduser()
    local_app_data = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return local_app_data / "StockSight Learner"


def _configure_logging() -> Path | None:
    options = {
        "level": os.getenv("LOG_LEVEL", "INFO").upper(),
        "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
    }
    try:
        log_path = _log_dir().resolve() / "stocksight_desktop.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=log_path, encoding="utf-8", **options)
    except OSError as exc:
        logging.basicConfig(**options)
        logging.getLogger(__name__).warning("Desktop log file is unavailable: %s", exc)
        return None
    return log_path


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) != 0


def _choose_port(host: str, preferred: int) -> int:
    if preferred > 0 and _port_available(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout_seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.5) as response:
                return int(response.status) < 500
        except (OSError, URLError):
            time.sleep(0.25)
    return False


def _error_html(url: str, log_path: Path | None) -> str:
    log_note = (
        f" Details are written to <code>{escape(str(log_path))}</code>."
        if log_path is not None
        else ""
    )
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>StockSight Learner</title>
        <style>
            body {{ font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f7fb; color: #0f172a; }}
            main {{ max-width: 680px; margin: 12vh auto; padding: 32px; background: #fff; border: 1px solid #dbe3ef; border-radius: 12px; }}
            h1 {{ margin-top: 0; }}
            code {{ background: #eef2f7; padding: 2px 6px; border-radius: 6px; }}
        </style>
    </head>
    <body>
        <main>
            <h1>StockSight could not finish starting.</h1>
            <p>The local app server did not respond at <code>{escape(url)}</code>.</p>
            <p>Close this window and launch StockSight again.{log_note}</p>
        </main>
    </body>
    </html>
    """


def main() -> None:
    log_path = _configure_logging()
    # The public Appwrite endpoint and project ID are built into the desktop
    # app. Users never need to create a Firebase configuration file.
    os.environ.setdefault("APPWRITE_ENDPOINT", "https://sgp.cloud.appwrite.io/v1")
    os.environ.setdefault("APPWRITE_PROJECT_ID", "6a84091e00308fab3517")
    os.environ.setdefault("APPWRITE_DATABASE_ID", "6a840e69001dca03b9d4")
    os.environ.setdefault("APPWRITE_STATE_TABLE_ID", "learner_staate")
    # The Function ID is public configuration only. The NVIDIA API key remains
    # a Secret in Appwrite and is never packaged into the Windows installer.
    os.environ.setdefault("APPWRITE_AI_FUNCTION_ID", "6a8450bf0020e0abf40b")
    # Pro's optional source bridge is a fixed project Function ID. Provider
    # credentials remain in Appwrite; users never configure them locally.
    os.environ.setdefault("APPWRITE_MARKET_INTEL_FUNCTION_ID", "stocksight_market_intel")
    settings = get_settings()
    configured_host = os.getenv("APP_HOST", settings.app_host)
    bind_host = os.getenv(
        "APP_BIND_HOST",
        "127.0.0.1" if configured_host in {"127.0.0.1", "0.0.0.0", "::"} else configured_host,
    )
    browser_host = os.getenv(
        "APP_BROWSER_HOST",
        # Keep the browser address on the exact same IPv4 loopback interface
        # as Uvicorn.  On some Windows installations `localhost` resolves to
        # IPv6 first while the server is bound to 127.0.0.1, producing a false
        # "could not finish starting" screen.
        "127.0.0.1" if configured_host in {"127.0.0.1", "0.0.0.0", "::"} else configured_host,
    )
    preferred_port = int(os.getenv("APP_PORT", str(settings.app_port)))
    port = _choose_port(bind_host, preferred_port)
    url = f"http://{browser_host}:{port}"
    readiness_url = f"{url}/health"

    from learner_fastapi_firebase.app.main import app

    config = uvicorn.Config(
        app,
        host=bind_host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, name="stocksight-server", daemon=True)
    server_thread.start()

    # Do not use the dashboard itself as a startup probe: it may make cloud
    # requests before the person has signed in.  The health route only proves
    # that the local server is ready to accept the WebView connection.
    if _wait_for_server(readiness_url):
        window = webview.create_window(
            "StockSight Learner",
            url,
            js_api=DesktopApi(),
            width=1280,
            height=860,
            min_size=(1040, 720),
            confirm_close=False,
        )
    else:
        logging.error("StockSight server failed to respond at %s", url)
        window = webview.create_window(
            "StockSight Learner",
            html=_error_html(url, log_path),
            js_api=DesktopApi(),
            width=780,
            height=520,
            min_size=(640, 420),
            confirm_close=False,
        )

    try:
        webview.start()
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
