"""
SENTINEL Desktop Application
=============================
Launches the SENTINEL security system in a native desktop window.
Uses pywebview for the native window and Streamlit as the backend.

Usage:
    python desktop_app.py          (run from source)
    SENTINEL.exe                   (run from built installer)
"""

import multiprocessing
import os
import sys
import socket
import time
import threading
import logging
import traceback

# ─── Logging (file + console) ────────────────────────────────────────────────
LOG_FILE = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__)),
    "sentinel_desktop.log",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("SENTINEL")

# ─── Configuration ───────────────────────────────────────────────────────────
APP_TITLE = "SENTINEL — AI-Powered Security System"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
MIN_WIDTH = 1024
MIN_HEIGHT = 700
SERVER_TIMEOUT = 45          # seconds to wait for Streamlit to start
ICON_NAME = \"logo.ico\"


def get_base_dir():
    """Return project root whether running as script or frozen .exe."""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: data files are in _internal next to the exe
        exe_dir = os.path.dirname(sys.executable)
        internal = os.path.join(exe_dir, "_internal")
        if os.path.isdir(internal) and os.path.isfile(os.path.join(internal, "app.py")):
            return internal
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


def find_free_port():
    """Bind to port 0 and let the OS assign an available port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def wait_for_server(port: int, timeout: int = SERVER_TIMEOUT) -> bool:
    """Poll until the Streamlit server is accepting connections."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_is_open(port):
            return True
        time.sleep(0.4)
    return False


# ─── Streamlit Server ────────────────────────────────────────────────────────

class StreamlitServer:
    """Manages the Streamlit backend process."""

    def __init__(self, port: int, base_dir: str):
        self.port = port
        self.base_dir = base_dir
        self.process = None
        self._thread = None

    # ── launch via subprocess (works in script mode) ──
    def _launch_subprocess(self):
        import subprocess
        app_py = os.path.join(self.base_dir, "app.py")
        python = sys.executable
        cmd = [
            python, "-m", "streamlit", "run", app_py,
            "--server.port",       str(self.port),
            "--server.headless",   "true",
            "--server.address",    "localhost",
            "--browser.gatherUsageStats", "false",
            "--global.developmentMode",   "false",
        ]
        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        self.process = subprocess.Popen(
            cmd, cwd=self.base_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creation,
        )

    # ── launch in-process (works in frozen / PyInstaller mode) ──
    def _launch_inprocess(self):
        try:
            app_py = os.path.join(self.base_dir, "app.py")
            log.info(f"Frozen mode — app.py at: {app_py}")
            log.info(f"Base dir: {self.base_dir}")
            os.chdir(self.base_dir)

            # Patch streamlit static path for frozen builds
            try:
                import streamlit as _st
                st_pkg = os.path.dirname(_st.__file__)
                static = os.path.join(st_pkg, "static")
                if not os.path.isdir(static):
                    alt = os.path.join(self.base_dir, "streamlit", "static")
                    if os.path.isdir(alt):
                        import streamlit.web.server.server_util as _su
                        _su._get_static_dir = lambda: alt
                        log.info(f"Patched static dir → {alt}")
            except Exception as e:
                log.warning(f"Static-dir patch skipped: {e}")

            # Patch signal handler — Streamlit tries to register signals
            # but we're in a daemon thread, so it fails.
            try:
                import streamlit.web.bootstrap as _bootstrap
                _bootstrap._set_up_signal_handler = lambda *a, **kw: None
                log.info("Patched signal handler for thread safety")
            except Exception as e:
                log.warning(f"Signal patch skipped: {e}")

            sys.argv = [
                "streamlit", "run", app_py,
                "--server.port",       str(self.port),
                "--server.headless",   "true",
                "--server.address",    "localhost",
                "--browser.gatherUsageStats", "false",
                "--global.developmentMode",   "false",
            ]
            from streamlit.web.cli import main as st_main
            st_main()
        except Exception:
            log.error(f"In-process Streamlit failed:\n{traceback.format_exc()}")

    def start(self):
        frozen = getattr(sys, "frozen", False)
        log.info(f"Frozen={frozen}, port={self.port}, base={self.base_dir}")
        target = self._launch_inprocess if frozen else self._launch_subprocess
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()


# ─── Desktop Window ──────────────────────────────────────────────────────────

class SentinelDesktop:
    """Main desktop application controller."""

    def __init__(self):
        self.base_dir = get_base_dir()
        self.port = find_free_port()
        self.server = StreamlitServer(self.port, self.base_dir)

    def _get_icon_path(self):
        p = os.path.join(self.base_dir, "assets", ICON_NAME)
        return p if os.path.isfile(p) else None

    def run(self):
        import webview

        # ── Loading splash HTML ──
        LOADING_HTML = """
        <!DOCTYPE html><html><head><style>
        body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
             background:#0c0f1a;font-family:'Segoe UI',sans-serif;color:#e2e8f0;}
        .box{text-align:center}
        h1{font-size:2.2rem;margin:0 0 .6rem;color:#6366f1}
        p{font-size:1rem;opacity:.7}
        .spinner{width:48px;height:48px;border:4px solid #1e2235;border-top:4px solid #6366f1;
                 border-radius:50%;animation:spin 1s linear infinite;margin:1.5rem auto}
        @keyframes spin{to{transform:rotate(360deg)}}
        </style></head><body><div class='box'>
        <h1>SENTINEL</h1><p>AI-Powered Security System</p>
        <div class='spinner'></div>
        <p style='font-size:.85rem;margin-top:.4rem'>Starting server &hellip;</p>
        </div></body></html>"""

        # 1. Create window with loading page immediately
        window = webview.create_window(
            APP_TITLE,
            html=LOADING_HTML,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
            resizable=True,
            text_select=True,
            confirm_close=False,
        )

        def _on_shown():
            """Called after the webview window is visible."""
            try:
                # 2. Start Streamlit
                log.info(f"Starting server on port {self.port} ...")
                self.server.start()

                # 3. Wait for readiness
                if not wait_for_server(self.port):
                    log.error("Server did not start in time.")
                    window.load_html("<body style='background:#0c0f1a;color:#f87171;"
                                     "font-family:sans-serif;display:flex;align-items:center;"
                                     "justify-content:center;height:100vh'>"
                                     "<h2>Failed to start server — see sentinel_desktop.log</h2></body>")
                    return

                time.sleep(1)
                log.info("Server ready — loading app.")
                window.load_url(f"http://localhost:{self.port}")
            except Exception:
                log.error(f"Startup error:\n{traceback.format_exc()}")

        # 4. Start webview (blocks until window closed)
        webview.start(func=_on_shown, debug=False, gui="edgechromium")

        # 5. Cleanup
        log.info("Window closed — shutting down.")
        self.server.stop()


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    multiprocessing.freeze_support()
    app = SentinelDesktop()
    app.run()


if __name__ == "__main__":
    main()
