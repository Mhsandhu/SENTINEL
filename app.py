"""
SENTINEL — AI-Powered Face Recognition & Gesture Control System
Cyberpunk HUD Edition

Run with:  streamlit run app.py
"""

import streamlit as st
import numpy as np
import os
import sys
import subprocess
import time
from datetime import datetime
from PIL import Image
import io
import json

# ── Project paths ─────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from modules import database as db
from modules import logger
from modules import vault_manager as vault
from modules.face_recognition import FaceRecognizer, ensure_face_model, ensure_hand_model
from modules import voice_commands as vc

# ── Page config ───────────────────────────────
st.set_page_config(
    page_title="SENTINEL",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Load CSS ──────────────────────────────────
def load_css():
    css_path = os.path.join(PROJECT_ROOT, "assets", "styles", "custom.css")
    if os.path.exists(css_path):
        with open(css_path, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ── Init ──────────────────────────────────────
def init_app():
    db.init_db()
    if "models_ready" not in st.session_state:
        with st.spinner("⟨ DOWNLOADING AI CORES ⟩"):
            ensure_face_model()
            ensure_hand_model()
        st.session_state.models_ready = True

    defaults = {
        "logged_in": False,
        "user_id": None,
        "username": None,
        "reg_step": 0,
        "reg_frames": [],
        "reg_username": "",
        "reg_email": "",
        "reg_password": "",
        "nav_page": "Dashboard",
        "voice_history": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


@st.cache_resource
def get_face_recognizer():
    return FaceRecognizer()


# ═══════════════════════════════════════════════
#  HTML HELPERS
# ═══════════════════════════════════════════════

def hud_header(title, subtitle=""):
    """Render a HUD-style page header."""
    ts = datetime.now().strftime("%H:%M:%S")
    st.markdown(f"""
    <div class="status-bar">
        <span>⟨ SENTINEL v2.0 ⟩</span>
        <span>MODULE: {title.upper()}</span>
        <span class="status-online">● ONLINE</span>
        <span>SYS.TIME {ts}</span>
    </div>
    """, unsafe_allow_html=True)

    sub_html = f'<p style="color:#4a6670; font-family: Share Tech Mono, monospace; font-size:0.85rem; letter-spacing:2px; margin-top:4px;">{subtitle}</p>' if subtitle else ""
    st.markdown(f"""
    <div style="margin-bottom: 20px;">
        <h1 style="margin-bottom:0;">{title}</h1>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def cyber_stat_card(icon, value, label):
    """Render a HUD stat card."""
    return f"""
    <div class="cyber-stat">
        <div class="cyber-stat-icon">{icon}</div>
        <div class="cyber-stat-number">{value}</div>
        <div class="cyber-stat-label">{label}</div>
    </div>
    """


def hud_card(icon, title, description):
    """Render a HUD action card."""
    return f"""
    <div class="hud-card">
        <h3>{icon} {title}</h3>
        <p>{description}</p>
    </div>
    """


# ═══════════════════════════════════════════════
#  AUTH PAGES
# ═══════════════════════════════════════════════
def auth_page():
    col1, col_center, col3 = st.columns([1, 2, 1])

    with col_center:
        # Animated logo
        st.markdown("""
        <div class="sentinel-logo">
            <h1>◈ SENTINEL ◈</h1>
            <div class="tagline">SECURE ACCESS · TOUCHLESS CONTROL</div>
            <div class="version">[ v2.0 // cyberpunk edition ]</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["◇ AUTHENTICATE", "◇ REGISTER"])

        with tab_login:
            login_page()

        with tab_register:
            register_page()
        st.markdown('</div>', unsafe_allow_html=True)


def login_page():
    st.markdown("#### ⟨ FACE BIOMETRIC SCAN ⟩")

    img_data = st.camera_input("Position face within frame", key="login_cam")

    if img_data is not None:
        image = Image.open(img_data).convert("RGB")
        frame = np.array(image)

        with st.spinner("⟨ SCANNING BIOMETRICS ⟩"):
            recognizer = get_face_recognizer()
            stored = db.get_all_face_encodings()

            if not stored:
                st.warning("◇ No registered operatives. Register first.")
                return

            matched, user_info, score = recognizer.verify_face(frame, stored)

        if matched:
            st.session_state.logged_in = True
            st.session_state.user_id = user_info["user_id"]
            st.session_state.username = user_info["username"]
            db.update_last_login(user_info["user_id"])
            logger.log_login_success(user_info["user_id"], "face")

            st.success(f"◇ IDENTITY CONFIRMED — Welcome, **{user_info['username']}** // Match: {score*100:.1f}%")
            time.sleep(1)
            st.rerun()
        else:
            score_pct = score * 100 if score > 0 else 0
            st.error(f"◇ ACCESS DENIED — Best match: {score_pct:.1f}% (threshold: 80%)")
            logger.log_login_failed(reason=f"Best score: {score_pct:.1f}%")

    st.divider()
    st.markdown("#### ⟨ BACKUP: CIPHER ACCESS ⟩")

    with st.form("password_login"):
        username = st.text_input("OPERATIVE ID")
        password = st.text_input("CIPHER KEY", type="password")
        submit = st.form_submit_button("◈ AUTHENTICATE")

        if submit and username and password:
            user = db.get_user_by_username(username)
            if user and user["password_hash"] and db.verify_password(password, user["password_hash"]):
                st.session_state.logged_in = True
                st.session_state.user_id = user["user_id"]
                st.session_state.username = user["username"]
                db.update_last_login(user["user_id"])
                logger.log_login_success(user["user_id"], "password")
                st.success(f"◇ ACCESS GRANTED — {username}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("◇ AUTHENTICATION FAILED — Invalid credentials")
                logger.log_login_failed(reason=f"Bad password for '{username}'")


def register_page():
    step = st.session_state.reg_step

    if step == 0:
        st.markdown("#### ⟨ STEP 1 // OPERATIVE DETAILS ⟩")
        with st.form("reg_form"):
            username = st.text_input("OPERATIVE ID *")
            email = st.text_input("COMMS CHANNEL (email)")
            password = st.text_input("BACKUP CIPHER (optional)", type="password")
            submit = st.form_submit_button("◈ PROCEED →")

            if submit:
                if not username.strip():
                    st.error("◇ Operative ID required.")
                elif db.get_user_by_username(username.strip()):
                    st.error("◇ Operative ID already registered.")
                else:
                    st.session_state.reg_username = username.strip()
                    st.session_state.reg_email = email.strip()
                    st.session_state.reg_password = password
                    st.session_state.reg_frames = []
                    st.session_state.reg_step = 1
                    st.rerun()

    elif step == 1:
        captured = len(st.session_state.reg_frames)
        st.markdown(f"#### ⟨ STEP 2 // BIOMETRIC CAPTURE ({captured + 1}/5) ⟩")

        prompts = [
            "◇ SCAN: Face camera directly",
            "◇ SCAN: Rotate head LEFT 15°",
            "◇ SCAN: Rotate head RIGHT 15°",
            "◇ SCAN: Tilt head UP slightly",
            "◇ SCAN: Face camera — final capture",
        ]
        idx = min(captured, 4)
        st.info(prompts[idx])

        # Progress bar
        st.progress(captured / 5, text=f"Biometric samples: {captured}/5")

        img_data = st.camera_input("Capture biometric sample", key=f"reg_cam_{idx}")

        if img_data is not None:
            image = Image.open(img_data).convert("RGB")
            frame = np.array(image)
            recognizer = get_face_recognizer()
            enc = recognizer.extract_encoding(frame)

            if enc is not None:
                st.session_state.reg_frames.append(frame)
                st.success(f"◇ Sample {len(st.session_state.reg_frames)}/5 acquired ✓")
                if len(st.session_state.reg_frames) >= 5:
                    st.session_state.reg_step = 2
                    st.rerun()
                else:
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.warning("◇ No face detected in frame. Retry.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← ABORT"):
                st.session_state.reg_step = 0
                st.session_state.reg_frames = []
                st.rerun()
        with col2:
            if captured >= 3:
                if st.button("SKIP → COMPLETE"):
                    st.session_state.reg_step = 2
                    st.rerun()

    elif step == 2:
        st.markdown("#### ⟨ STEP 3 // CONFIRM REGISTRATION ⟩")

        st.markdown(f"""
        <div class="hud-card">
            <p>◇ <strong>OPERATIVE:</strong> {st.session_state.reg_username}</p>
            <p>◇ <strong>COMMS:</strong> {st.session_state.reg_email or 'N/A'}</p>
            <p>◇ <strong>BIOMETRIC SAMPLES:</strong> {len(st.session_state.reg_frames)}</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("◈ CONFIRM REGISTRATION", type="primary"):
                with st.spinner("⟨ ENCODING BIOMETRICS ⟩"):
                    recognizer = get_face_recognizer()
                    encoding, msg = recognizer.register_face(st.session_state.reg_frames)

                if encoding is not None:
                    ok, db_msg = db.add_user(
                        username=st.session_state.reg_username,
                        email=st.session_state.reg_email or None,
                        face_encoding=encoding,
                        password=st.session_state.reg_password or None,
                    )
                    if ok:
                        user = db.get_user_by_username(st.session_state.reg_username)
                        if user:
                            logger.log_registration(user["user_id"], user["username"])
                        st.success(f"◇ REGISTRATION COMPLETE — {db_msg}")
                        st.session_state.reg_step = 0
                        st.session_state.reg_frames = []
                    else:
                        st.error(db_msg)
                else:
                    st.error(msg)

        with col2:
            if st.button("← BACK TO CAPTURE"):
                st.session_state.reg_step = 1
                st.rerun()


# ═══════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════
def dashboard_page():
    hud_header(f"Welcome, {st.session_state.username}", "SENTINEL Command Center")

    # Custom stat cards
    stats = vault.get_storage_stats(st.session_state.user_id)
    logs = db.get_user_logs(st.session_state.user_id, limit=500)
    login_count = sum(1 for l in logs if l["action_type"] == "login")
    gesture_count = sum(1 for l in logs if l["action_type"] == "gesture_used")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(cyber_stat_card("📁", stats["total_files"], "VAULT FILES"), unsafe_allow_html=True)
    with col2:
        st.markdown(cyber_stat_card("💾", stats["size_formatted"], "STORAGE"), unsafe_allow_html=True)
    with col3:
        st.markdown(cyber_stat_card("🔓", login_count, "AUTH EVENTS"), unsafe_allow_html=True)
    with col4:
        st.markdown(cyber_stat_card("🤚", gesture_count, "GESTURES"), unsafe_allow_html=True)

    st.divider()

    # Quick action cards
    st.markdown("## ⟨ QUICK ACCESS ⟩")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(hud_card("🤚", "GESTURE CTRL", "Control system with hand gestures"), unsafe_allow_html=True)
        if st.button("◈ LAUNCH", key="dash_gesture", use_container_width=True):
            st.session_state.nav_page = "Gesture Control"
            st.rerun()

    with col2:
        st.markdown(hud_card("🔒", "SECURE VAULT", "Access encrypted file storage"), unsafe_allow_html=True)
        if st.button("◈ OPEN", key="dash_vault", use_container_width=True):
            st.session_state.nav_page = "My Vault"
            st.rerun()

    with col3:
        st.markdown(hud_card("🎙️", "VOICE CTRL", "Navigate with voice commands"), unsafe_allow_html=True)
        if st.button("◈ ACTIVATE", key="dash_voice", use_container_width=True):
            st.session_state.nav_page = "Voice Commands"
            st.rerun()

    with col4:
        st.markdown(hud_card("📋", "SYS LOGS", "Monitor all system activity"), unsafe_allow_html=True)
        if st.button("◈ VIEW", key="dash_logs", use_container_width=True):
            st.session_state.nav_page = "Activity Logs"
            st.rerun()

    st.divider()

    # Recent activity with HUD styling
    st.markdown("## ⟨ RECENT ACTIVITY ⟩")
    recent = logger.get_formatted_logs(st.session_state.user_id, limit=10)
    if recent:
        for log in recent:
            color_class = "log-success" if log["success"] else "log-failed"
            st.markdown(f"""
            <div class="log-entry {color_class}">
                {log['icon']} {log['status']}  <strong>{log['action']}</strong> — {log['details']}
                <span class="log-timestamp">{log['timestamp']}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("◇ No activity recorded yet.")


# ═══════════════════════════════════════════════
#  GESTURE CONTROL
# ═══════════════════════════════════════════════
def gesture_page():
    hud_header("Gesture Control", "Hand tracking neural interface")

    settings = db.get_gesture_settings(st.session_state.user_id)
    sensitivity = settings.get("sensitivity", 5)

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### ⟨ CONTROLLER LAUNCH ⟩")

        st.markdown("""
        <div class="hud-card">
            <p>◇ Opens a camera window for real-time gesture detection</p>
            <p>◇ Press <strong>Q</strong> in the camera window to terminate</p>
            <p>◇ Gestures are mapped to system-level keyboard shortcuts</p>
        </div>
        """, unsafe_allow_html=True)

        new_sensitivity = st.slider("◇ NEURAL SENSITIVITY", 1, 10, sensitivity,
                                     help="Higher = more responsive, may cause false triggers")

        if new_sensitivity != sensitivity:
            db.update_gesture_settings(st.session_state.user_id, True, new_sensitivity)
            sensitivity = new_sensitivity

        if st.button("◈ INITIALIZE GESTURE CONTROL", type="primary", use_container_width=True):
            logger.log_gesture_session_start(st.session_state.user_id)
            script = os.path.join(PROJECT_ROOT, "modules", "gesture_control.py")
            subprocess.Popen([sys.executable, script, str(sensitivity), str(st.session_state.user_id)])
            st.success("◇ GESTURE CONTROL INITIALIZED — Camera window active")
            st.balloons()

    with col2:
        st.markdown("### ⟨ GESTURE MAP ⟩")

        gestures = [
            ("✊", "FIST", "Minimize All"),
            ("🖐️", "PALM", "Play/Pause"),
            ("✌️", "PEACE", "Screenshot"),
            ("👍", "THUMBS UP", "Vol +"),
            ("🤘", "ROCK ON", "Vol -"),
            ("3️⃣", "THREE", "Alt+Tab"),
            ("🤙", "PINKY", "Mute"),
            ("👉", "GUN", "Enter"),
            ("←", "SWIPE L", "Previous"),
            ("→", "SWIPE R", "Next"),
        ]

        gesture_html = '<div style="display:flex; flex-wrap:wrap; gap:6px;">'
        for icon, name, action in gestures:
            gesture_html += f"""
            <div class="gesture-card">
                <span class="gesture-icon">{icon}</span>
                <div class="gesture-name">{name}</div>
                <div class="gesture-action">{action}</div>
            </div>"""
        gesture_html += '</div>'
        st.markdown(gesture_html, unsafe_allow_html=True)

    st.divider()

    # Gesture history
    st.markdown("### ⟨ GESTURE LOG ⟩")
    gesture_logs = db.get_logs_by_type(st.session_state.user_id, "gesture_used", 20)
    if gesture_logs:
        for log in gesture_logs:
            st.markdown(f"""
            <div class="log-entry log-success">
                🤚 <code>{log['action_details']}</code>
                <span class="log-timestamp">{log['timestamp']}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("◇ No gesture activity recorded. Initialize the controller to begin.")


# ═══════════════════════════════════════════════
#  VOICE COMMANDS
# ═══════════════════════════════════════════════
def voice_page():
    hud_header("Voice Commands", "Speech recognition neural link")

    available = vc.is_available()
    missing = vc.get_missing_packages()

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### ⟨ VOICE INTERFACE ⟩")

        if not available:
            st.markdown(f"""
            <div class="hud-card">
                <h3>◇ PACKAGES REQUIRED</h3>
                <p>Install voice dependencies to enable this module:</p>
                <p><code>pip install {' '.join(missing)}</code></p>
            </div>
            """, unsafe_allow_html=True)
            st.warning(f"◇ Missing packages: {', '.join(missing)}")
        else:
            st.markdown("""
            <div class="voice-indicator">
                <div class="voice-wave">
                    <span></span><span></span><span></span><span></span><span></span>
                </div>
                <span>VOICE NEURAL LINK — READY</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div class="hud-card" style="margin-top:16px;">
                <h3>◇ HOW TO USE</h3>
                <p>1. Click <strong>"ACTIVATE VOICE CONTROL"</strong> below</p>
                <p>2. Speak a command clearly (e.g., "open vault", "dashboard")</p>
                <p>3. The system processes your voice and executes the command</p>
                <p>4. You'll hear audio feedback confirming the action</p>
            </div>
            """, unsafe_allow_html=True)

            # Launch voice control standalone
            if st.button("◈ ACTIVATE VOICE CONTROL", type="primary", use_container_width=True):
                st.info("◇ Voice control is active. Speak a command...")
                # In a real deployment, this would start the VoiceEngine
                # For Streamlit Cloud, show the command reference
                st.session_state.voice_active = True

            # Manual command input (works on all platforms)
            st.markdown("### ⟨ MANUAL COMMAND INPUT ⟩")
            st.caption("◇ Type a command if microphone is not available")

            cmd_input = st.text_input("ENTER COMMAND", placeholder="e.g., dashboard, vault, logs, help...",
                                       label_visibility="collapsed")
            if cmd_input:
                engine = vc.VoiceEngine()
                cmd_key, cmd_info = engine._match_command(cmd_input)

                if cmd_info:
                    st.success(f"◇ COMMAND: {cmd_info['response']}")
                    if cmd_info["action"] == "navigate":
                        st.session_state.nav_page = cmd_info["target"]
                        time.sleep(0.5)
                        st.rerun()
                    elif cmd_info["action"] == "logout":
                        logger.log_logout(st.session_state.user_id)
                        for key in list(st.session_state.keys()):
                            del st.session_state[key]
                        st.rerun()
                    elif cmd_info["action"] == "help":
                        st.info(cmd_info["response"])
                else:
                    st.warning(f'◇ UNKNOWN COMMAND: "{cmd_input}" — Say "help" for available commands')

    with col2:
        st.markdown("### ⟨ COMMAND REFERENCE ⟩")

        engine = vc.VoiceEngine()
        groups = engine.get_all_commands()

        for group_name, cmds in groups.items():
            st.markdown(f"**◇ {group_name.upper()}**")
            for cmd in cmds:
                st.markdown(f"""
                <div class="gesture-card" style="display:block; margin:4px 0; text-align:left; padding:10px 14px;">
                    <span style="color:#00ff41; font-family: Orbitron, monospace; font-size:0.7rem;">"{cmd['command']}"</span>
                    <span style="color:#4a6670; font-family: Share Tech Mono, monospace; font-size:0.72rem; float:right;">→ {cmd['response']}</span>
                </div>
                """, unsafe_allow_html=True)

        # Voice history
        if st.session_state.get("voice_history"):
            st.markdown("### ⟨ VOICE LOG ⟩")
            for entry in st.session_state.voice_history[-10:]:
                st.markdown(f"""
                <div class="log-entry log-info">
                    🎙️ <code>{entry}</code>
                </div>
                """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════
#  VAULT
# ═══════════════════════════════════════════════
def vault_page():
    hud_header("Secure Vault", "Encrypted file storage system")

    # Vault status bar
    stats = vault.get_storage_stats(st.session_state.user_id)
    st.markdown(f"""
    <div class="vault-status">
        VAULT STATUS: UNLOCKED  ◇  FILES: {stats['total_files']}  ◇  STORAGE: {stats['size_formatted']}  ◇  OWNER: {st.session_state.username}
    </div>
    """, unsafe_allow_html=True)

    tab_upload, tab_browse, tab_search = st.tabs(["◇ UPLOAD", "◇ BROWSE", "◇ SEARCH"])

    with tab_upload:
        st.markdown("### ⟨ FILE UPLOAD ⟩")

        uploaded = st.file_uploader(
            "Select file for vault storage",
            type=None,
            accept_multiple_files=False,
            help="Max 100MB per file. All formats supported.",
        )

        category = st.selectbox("◇ CATEGORY", ["Auto-detect"] + vault.CATEGORIES)

        if uploaded and st.button("◈ ENCRYPT & STORE", type="primary", use_container_width=True):
            cat = None if category == "Auto-detect" else category
            ok, msg, info = vault.save_file(st.session_state.user_id, uploaded, cat)
            if ok:
                st.success(f"◇ FILE SECURED — {msg}")
                logger.log_file_upload(st.session_state.user_id, uploaded.name, info["category"])
            else:
                st.error(f"◇ UPLOAD FAILED — {msg}")

    with tab_browse:
        st.markdown("### ⟨ FILE BROWSER ⟩")

        filter_cat = st.selectbox("◇ FILTER", ["All"] + vault.CATEGORIES, key="browse_cat")
        files = vault.get_user_files(st.session_state.user_id, None if filter_cat == "All" else filter_cat)

        if not files:
            st.info("◇ Vault empty. Upload files to begin.")
        else:
            for f in files:
                icon = '📄' if f['category'] == 'Documents' else '🖼️' if f['category'] == 'Photos' else '🎬' if f['category'] == 'Videos' else '📎'
                size_str = vault.format_file_size(f['file_size'] or 0)

                with st.expander(f"{icon}  {f['original_filename']}  ◇  {size_str}  ◇  {f['category']}"):
                    col1, col2, col3 = st.columns([2, 1, 1])

                    with col1:
                        st.markdown(f"""
                        <div style="font-family: Share Tech Mono, monospace; font-size: 0.82rem; color: #c9d6df;">
                            ◇ UPLOADED: {f['uploaded_at']}<br>
                            ◇ TYPE: {f['file_type']}<br>
                            ◇ ACCESS COUNT: {f['access_count']}
                        </div>
                        """, unsafe_allow_html=True)

                    with col2:
                        data, name, mime = vault.get_file_content(f["file_id"])
                        if data:
                            st.download_button("📥 DOWNLOAD", data, name, mime, key=f"dl_{f['file_id']}")
                            logger.log_file_view(st.session_state.user_id, f["original_filename"])

                    with col3:
                        if st.button("🗑️ DELETE", key=f"del_{f['file_id']}"):
                            ok, msg = vault.delete_file(f["file_id"])
                            if ok:
                                logger.log_file_delete(st.session_state.user_id, f["original_filename"])
                                st.success(f"◇ {msg}")
                                st.rerun()
                            else:
                                st.error(msg)

                    # Image preview
                    if f["file_type"] in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
                        if data:
                            st.image(data, caption=f["original_filename"], width=300)

    with tab_search:
        st.markdown("### ⟨ VAULT SEARCH ⟩")
        query = st.text_input("◇ SEARCH QUERY", placeholder="e.g., report, photo, video...")

        if query:
            results = vault.search_user_files(st.session_state.user_id, query)
            if results:
                st.success(f"◇ {len(results)} file(s) found")
                for f in results:
                    st.markdown(f"""
                    <div class="log-entry log-info">
                        📎 <strong>{f['original_filename']}</strong> — {f['category']} — {vault.format_file_size(f['file_size'] or 0)}
                        <span class="log-timestamp">{f['uploaded_at']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("◇ No matching files in vault.")


# ═══════════════════════════════════════════════
#  ACTIVITY LOGS
# ═══════════════════════════════════════════════
def logs_page():
    hud_header("Activity Logs", "System monitoring & audit trail")

    col1, col2 = st.columns([1, 3])
    with col1:
        filter_type = st.selectbox("◇ FILTER", [
            "All", "login", "login_failed", "file_upload", "file_view",
            "file_delete", "gesture_used", "gesture_session", "settings_change", "logout",
        ])
    with col2:
        limit = st.slider("◇ ENTRIES", 10, 200, 50)

    if filter_type == "All":
        logs = db.get_user_logs(st.session_state.user_id, limit)
    else:
        logs = db.get_logs_by_type(st.session_state.user_id, filter_type, limit)

    if not logs:
        st.info("◇ No activity logs found.")
        return

    # Summary stats
    success_count = sum(1 for l in logs if l["success"])
    fail_count = len(logs) - success_count

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(cyber_stat_card("📊", len(logs), "TOTAL EVENTS"), unsafe_allow_html=True)
    with col2:
        st.markdown(cyber_stat_card("✅", success_count, "SUCCESSFUL"), unsafe_allow_html=True)
    with col3:
        st.markdown(cyber_stat_card("❌", fail_count, "FAILED"), unsafe_allow_html=True)

    st.divider()

    icons = {
        "login": "🔓", "login_failed": "🔒", "registration": "📝",
        "file_upload": "📤", "file_view": "👁️", "file_delete": "🗑️",
        "gesture_used": "🤚", "gesture_session": "🎮",
        "settings_change": "⚙️", "logout": "🚪",
    }

    for log in logs:
        icon = icons.get(log["action_type"], "📌")
        status_icon = "✓" if log["success"] else "✗"
        color_class = "log-success" if log["success"] else "log-failed"

        st.markdown(f"""
        <div class="log-entry {color_class}">
            {icon} {status_icon} <strong>{log['action_type'].upper()}</strong> — {log['action_details'] or ''}
            <span class="log-timestamp">{log['timestamp']}</span>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════
def settings_page():
    hud_header("Settings", "System configuration & security")

    tab_profile, tab_gesture, tab_security = st.tabs(
        ["◇ PROFILE", "◇ GESTURE CONFIG", "◇ SECURITY"]
    )

    user = db.get_user_by_id(st.session_state.user_id)

    with tab_profile:
        st.markdown("### ⟨ OPERATIVE PROFILE ⟩")

        st.markdown(f"""
        <div class="hud-card">
            <p>◇ <strong>OPERATIVE ID:</strong> {user['username']}</p>
            <p>◇ <strong>COMMS CHANNEL:</strong> {user['email'] or 'NOT SET'}</p>
            <p>◇ <strong>ENLISTED:</strong> {user['created_at']}</p>
            <p>◇ <strong>LAST AUTH:</strong> {user['last_login'] or 'N/A'}</p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown("### ⟨ BIOMETRIC RE-CALIBRATION ⟩")
        st.warning("◇ Re-register your face if recognition accuracy has degraded.")

        if st.button("◈ RE-REGISTER FACE"):
            st.session_state.re_register = True
            st.rerun()

        if st.session_state.get("re_register"):
            img = st.camera_input("Capture new biometric sample", key="reregister_cam")
            if img:
                image = Image.open(img).convert("RGB")
                frame = np.array(image)
                recognizer = get_face_recognizer()
                enc = recognizer.extract_encoding(frame)
                if enc is not None:
                    db.update_face_encoding(st.session_state.user_id, enc)
                    logger.log_settings_change(st.session_state.user_id, "face_data", "updated")
                    st.success("◇ BIOMETRIC DATA UPDATED")
                    st.session_state.re_register = False
                else:
                    st.error("◇ No face detected. Retry.")

    with tab_gesture:
        st.markdown("### ⟨ GESTURE NEURAL CONFIG ⟩")
        settings = db.get_gesture_settings(st.session_state.user_id)

        enabled = st.toggle("◇ GESTURE CONTROL ACTIVE", value=bool(settings["gesture_enabled"]))
        sensitivity = st.slider("◇ NEURAL SENSITIVITY", 1, 10, settings["sensitivity"],
                                help="1 = Conservative // 10 = Aggressive")

        st.markdown("""
        <div class="hud-card">
            <h3>◇ SENSITIVITY GUIDE</h3>
            <p><strong>1-3:</strong> Conservative — minimal false triggers, slower response</p>
            <p><strong>4-6:</strong> Balanced — optimal for most operatives</p>
            <p><strong>7-10:</strong> Aggressive — maximum responsiveness, may misfire</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("◈ SAVE CONFIG"):
            db.update_gesture_settings(st.session_state.user_id, enabled, sensitivity)
            logger.log_settings_change(st.session_state.user_id, "gesture_settings",
                                        f"enabled={enabled}, sensitivity={sensitivity}")
            st.success("◇ CONFIGURATION SAVED")

    with tab_security:
        st.markdown("### ⟨ CIPHER KEY UPDATE ⟩")

        with st.form("change_pw"):
            new_pw = st.text_input("NEW CIPHER KEY", type="password")
            confirm_pw = st.text_input("CONFIRM CIPHER KEY", type="password")
            submit = st.form_submit_button("◈ UPDATE KEY")

            if submit:
                if not new_pw:
                    st.error("◇ Cipher key cannot be empty.")
                elif new_pw != confirm_pw:
                    st.error("◇ Cipher keys do not match.")
                else:
                    db.update_user_password(st.session_state.user_id, new_pw)
                    logger.log_settings_change(st.session_state.user_id, "password", "changed")
                    st.success("◇ CIPHER KEY UPDATED")

        st.divider()
        st.markdown("### ⟨ SYSTEM PURGE ⟩")
        st.error("◇ WARNING: This action is irreversible. All data will be destroyed.")

        if st.button("⚠️ PURGE ACCOUNT"):
            st.session_state.confirm_delete = True

        if st.session_state.get("confirm_delete"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("◈ CONFIRM PURGE", type="primary"):
                    db.delete_user(st.session_state.user_id)
                    logger.log_logout(st.session_state.user_id)
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
            with col2:
                if st.button("← ABORT"):
                    st.session_state.confirm_delete = False
                    st.rerun()


# ═══════════════════════════════════════════════
#  MAIN APP — SIDEBAR + ROUTING
# ═══════════════════════════════════════════════
def main_app():
    with st.sidebar:
        # Logo
        st.markdown("""
        <div style="text-align:center; padding:10px 0;">
            <div style="font-family: Orbitron, monospace; font-size:1.4rem; color:#00ff41;
                        text-shadow: 0 0 20px #00ff4140; letter-spacing:4px;">
                ◈ SENTINEL
            </div>
            <div style="font-family: Share Tech Mono, monospace; font-size:0.55rem;
                        color:#4a6670; letter-spacing:3px; margin-top:4px;">
                [ CYBERPUNK EDITION v2.0 ]
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # User profile
        st.markdown(f"""
        <div class="sidebar-profile">
            <span class="avatar">👤</span>
            <div class="name">{st.session_state.username}</div>
            <div class="role">AUTHORIZED OPERATIVE</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Navigation with icons
        nav_items = [
            ("🏠", "Dashboard"),
            ("🤚", "Gesture Control"),
            ("🎙️", "Voice Commands"),
            ("🔒", "My Vault"),
            ("📋", "Activity Logs"),
            ("⚙️", "Settings"),
        ]

        for icon, page in nav_items:
            is_active = st.session_state.nav_page == page
            if st.button(
                f"{icon}  {page.upper()}",
                key=f"nav_{page}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.nav_page = page
                st.rerun()

        st.divider()

        # System status
        st.markdown("""
        <div style="font-family: Share Tech Mono, monospace; font-size:0.68rem;
                    color:#4a6670; text-align:center; letter-spacing:1px;">
            SYS STATUS: <span style="color:#00ff41;">OPERATIONAL</span><br>
            MODULES: 6 ONLINE<br>
            THREAT LEVEL: LOW
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        if st.button("🚪  DISCONNECT", use_container_width=True):
            logger.log_logout(st.session_state.user_id)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # Page router
    page = st.session_state.get("nav_page", "Dashboard")

    if page == "Dashboard":
        dashboard_page()
    elif page == "Gesture Control":
        gesture_page()
    elif page == "Voice Commands":
        voice_page()
    elif page == "My Vault":
        vault_page()
    elif page == "Activity Logs":
        logs_page()
    elif page == "Settings":
        settings_page()


# ═══════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════
def main():
    load_css()
    init_app()

    if st.session_state.logged_in:
        main_app()
    else:
        auth_page()


if __name__ == "__main__":
    main()
