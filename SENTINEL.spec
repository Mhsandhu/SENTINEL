# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for SENTINEL Desktop Application.
Generated for one-directory mode (--onedir).
"""

import os
import sys
import importlib
from PyInstaller.utils.hooks import copy_metadata, collect_all

block_cipher = None

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.abspath(".")
VENV_SP = os.path.join(
    os.path.dirname(sys.executable), "..", "Lib", "site-packages"
)
if not os.path.isdir(VENV_SP):
    VENV_SP = os.path.join(
        os.path.dirname(sys.executable), "Lib", "site-packages"
    )

# ─── Data files to bundle ────────────────────────────────────────────────────
added_data = [
    # SENTINEL project files
    (os.path.join(PROJECT_DIR, "app.py"),           "."),
    (os.path.join(PROJECT_DIR, "modules"),           "modules"),
    (os.path.join(PROJECT_DIR, "models"),             "models"),
    (os.path.join(PROJECT_DIR, "assets"),             "assets"),
    (os.path.join(PROJECT_DIR, ".streamlit"),         ".streamlit"),
]

# Add database & vault dirs if they exist
for d in ("database", "data", "vault_storage", "config"):
    p = os.path.join(PROJECT_DIR, d)
    if os.path.isdir(p):
        added_data.append((p, d))

# ─── Package metadata (required for importlib.metadata) ──────────────────────
metadata_packages = [
    "streamlit", "altair", "pyarrow", "pandas", "numpy", "Pillow",
    "click", "tornado", "protobuf", "packaging", "rich", "watchdog",
    "toml", "gitdb", "pydeck", "cachetools", "tenacity", "jsonschema",
    "pyautogui", "mediapipe", "opencv-contrib-python-headless",
    "pywebview", "SpeechRecognition", "pyttsx3",
    "typing_extensions", "jinja2", "markupsafe", "requests", "urllib3",
    "certifi", "charset-normalizer", "idna", "blinker", "matplotlib",
]
for pkg in metadata_packages:
    try:
        added_data += copy_metadata(pkg)
    except Exception:
        pass   # package not installed — skip

# ─── Streamlit static / runtime files ────────────────────────────────────────
try:
    import streamlit
    st_dir = os.path.dirname(streamlit.__file__)
    added_data.append((os.path.join(st_dir, "static"),   os.path.join("streamlit", "static")))
    added_data.append((os.path.join(st_dir, "runtime"),  os.path.join("streamlit", "runtime")))
    # Streamlit also needs its 'proto' compiled files
    proto_dir = os.path.join(st_dir, "proto")
    if os.path.isdir(proto_dir):
        added_data.append((proto_dir, os.path.join("streamlit", "proto")))
except Exception:
    pass

# ─── MediaPipe models / data ─────────────────────────────────────────────────
try:
    import mediapipe
    mp_dir = os.path.dirname(mediapipe.__file__)
    added_data.append((mp_dir, "mediapipe"))
except Exception:
    pass

# ─── Hidden imports ──────────────────────────────────────────────────────────
hidden_imports = [
    # Streamlit core
    "streamlit",
    "streamlit.web",
    "streamlit.web.cli",
    "streamlit.web.server",
    "streamlit.web.server.server",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner",
    "streamlit.runtime.scriptrunner.script_runner",
    "streamlit.runtime.caching",
    "streamlit.runtime.caching.cache_data_api",
    "streamlit.runtime.caching.cache_resource_api",
    "streamlit.runtime.state",
    "streamlit.components",
    "streamlit.components.v1",
    "streamlit.elements",
    "streamlit.commands",
    "streamlit.commands.page_config",
    "streamlit.proto",
    # Streamlit deps
    "altair",
    "altair.vegalite",
    "altair.vegalite.v5",
    "vega_datasets",
    "pyarrow",
    "pyarrow.vendored",
    "pyarrow.vendored.version",
    "pandas",
    "pandas.core",
    "numpy",
    "numpy.core",
    "PIL",
    "PIL.Image",
    "toml",
    "tomli",
    "click",
    "rich",
    "pygments",
    "validators",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "tornado",
    "tornado.web",
    "tornado.websocket",
    "tornado.ioloop",
    "tornado.httpserver",
    "cachetools",
    "pydeck",
    "gitdb",
    "tenacity",
    "jsonschema",
    "referencing",
    # MediaPipe
    "mediapipe",
    "mediapipe.tasks",
    "mediapipe.tasks.python",
    "mediapipe.tasks.python.vision",
    "mediapipe.tasks.python.vision.hand_landmarker",
    "mediapipe.tasks.python.vision.face_landmarker",
    "mediapipe.tasks.python.components",
    "mediapipe.tasks.python.core",
    "mediapipe.python",
    "mediapipe.python._framework_bindings",
    # OpenCV
    "cv2",
    # pywebview
    "webview",
    "webview.platforms",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
    # SQLite
    "sqlite3",
    # Standard lib
    "multiprocessing",
    "multiprocessing.popen_spawn_win32",
    "encodings",
    "encodings.utf_8",
    "encodings.cp1252",
    "email",
    "email.mime",
    "email.mime.text",
    "email.mime.multipart",
    # Other
    "pyautogui",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "speech_recognition",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.backends",
    "matplotlib.backends.backend_agg",
]

# ─── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ["desktop_app.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=added_data,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "scipy",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SENTINEL",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # no black console window
    icon="logo.ico",          # app icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SENTINEL",
)
