"""
SENTINEL — AI-Powered Face Recognition & Gesture Control System
Modern Professional Edition

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
        with st.spinner("Initializing AI models..."):
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

def page_header(title, subtitle=""):
    """Render a clean page header with status bar."""
    ts = datetime.now().strftime("%H:%M:%S")
    st.markdown(f"""
    <div class="status-bar">
        <span>SENTINEL v2.0</span>
        <span>{title}</span>
        <span class="status-online">● Online</span>
        <span>{ts}</span>
    </div>
    """, unsafe_allow_html=True)

    sub_html = f'<p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 4px; font-weight: 400;">{subtitle}</p>' if subtitle else ""
    st.markdown(f"""
    <div style="margin-bottom: 24px;">
        <h1 style="margin-bottom: 0;">{title}</h1>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def stat_card(icon, value, label):
    """Render a modern stat card."""
    return f"""
    <div class="cyber-stat">
        <div class="cyber-stat-icon">{icon}</div>
        <div class="cyber-stat-number">{value}</div>
        <div class="cyber-stat-label">{label}</div>
    </div>
    """


def info_card(icon, title, description):
    """Render a modern info card."""
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
        st.markdown("""
        <div class="sentinel-logo">
            <h1>SENTINEL</h1>
            <div class="tagline">SECURE ACCESS · TOUCHLESS CONTROL</div>
            <div class="version">v2.0 — Professional Edition</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            login_page()

        with tab_register:
            register_page()
        st.markdown('</div>', unsafe_allow_html=True)


def login_page():
    st.markdown("#### Face Recognition")

    img_data = st.camera_input("Position your face within the frame", key="login_cam")

    if img_data is not None:
        image = Image.open(img_data).convert("RGB")
        frame = np.array(image)

        with st.spinner("Verifying identity..."):
            recognizer = get_face_recognizer()
            stored = db.get_all_face_encodings()

            if not stored:
                st.warning("No registered users found. Please create an account first.")
                return

            matched, user_info, score = recognizer.verify_face(frame, stored)

        if matched:
            st.session_state.logged_in = True
            st.session_state.user_id = user_info["user_id"]
            st.session_state.username = user_info["username"]
            db.update_last_login(user_info["user_id"])
            logger.log_login_success(user_info["user_id"], "face")

            st.success(f"Identity verified — Welcome back, **{user_info['username']}** ({score*100:.1f}% match)")
            time.sleep(1)
            st.rerun()
        else:
            score_pct = score * 100 if score > 0 else 0
            st.error(f"Verification failed — Best match: {score_pct:.1f}% (minimum: 80%)")
            logger.log_login_failed(reason=f"Best score: {score_pct:.1f}%")

    st.divider()
    st.markdown("#### Password Login")

    with st.form("password_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign In")

        if submit and username and password:
            user = db.get_user_by_username(username)
            if user and user["password_hash"] and db.verify_password(password, user["password_hash"]):
                st.session_state.logged_in = True
                st.session_state.user_id = user["user_id"]
                st.session_state.username = user["username"]
                db.update_last_login(user["user_id"])
                logger.log_login_success(user["user_id"], "password")
                st.success(f"Welcome back, {username}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Invalid username or password")
                logger.log_login_failed(reason=f"Bad password for '{username}'")


def register_page():
    step = st.session_state.reg_step

    if step == 0:
        st.markdown("#### Step 1 — Account Details")
        with st.form("reg_form"):
            username = st.text_input("Username *")
            email = st.text_input("Email address")
            password = st.text_input("Password (optional)", type="password")
            submit = st.form_submit_button("Continue →")

            if submit:
                if not username.strip():
                    st.error("Username is required.")
                elif db.get_user_by_username(username.strip()):
                    st.error("Username already taken.")
                else:
                    st.session_state.reg_username = username.strip()
                    st.session_state.reg_email = email.strip()
                    st.session_state.reg_password = password
                    st.session_state.reg_frames = []
                    st.session_state.reg_step = 1
                    st.rerun()

    elif step == 1:
        captured = len(st.session_state.reg_frames)
        st.markdown(f"#### Step 2 — Face Registration ({captured + 1}/5)")

        prompts = [
            "Look directly at the camera",
            "Turn your head slightly to the left",
            "Turn your head slightly to the right",
            "Tilt your head up slightly",
            "Look at the camera — final capture",
        ]
        idx = min(captured, 4)
        st.info(prompts[idx])

        st.progress(captured / 5, text=f"Samples captured: {captured}/5")

        img_data = st.camera_input("Capture face sample", key=f"reg_cam_{idx}")

        if img_data is not None:
            image = Image.open(img_data).convert("RGB")
            frame = np.array(image)
            recognizer = get_face_recognizer()
            enc = recognizer.extract_encoding(frame)

            if enc is not None:
                st.session_state.reg_frames.append(frame)
                st.success(f"Sample {len(st.session_state.reg_frames)}/5 captured ✓")
                if len(st.session_state.reg_frames) >= 5:
                    st.session_state.reg_step = 2
                    st.rerun()
                else:
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.warning("No face detected. Please try again.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back"):
                st.session_state.reg_step = 0
                st.session_state.reg_frames = []
                st.rerun()
        with col2:
            if captured >= 3:
                if st.button("Skip → Finish"):
                    st.session_state.reg_step = 2
                    st.rerun()

    elif step == 2:
        st.markdown("#### Step 3 — Confirm Registration")

        st.markdown(f"""
        <div class="hud-card">
            <p><strong>Username:</strong> {st.session_state.reg_username}</p>
            <p><strong>Email:</strong> {st.session_state.reg_email or 'Not provided'}</p>
            <p><strong>Face Samples:</strong> {len(st.session_state.reg_frames)}</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Create Account", type="primary"):
                with st.spinner("Processing face data..."):
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
                        st.success(f"Account created successfully — {db_msg}")
                        st.session_state.reg_step = 0
                        st.session_state.reg_frames = []
                    else:
                        st.error(db_msg)
                else:
                    st.error(msg)

        with col2:
            if st.button("← Back to Capture"):
                st.session_state.reg_step = 1
                st.rerun()


# ═══════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════
def dashboard_page():
    page_header(f"Welcome, {st.session_state.username}", "Your personal command center")

    stats = vault.get_storage_stats(st.session_state.user_id)
    logs = db.get_user_logs(st.session_state.user_id, limit=500)
    login_count = sum(1 for l in logs if l["action_type"] == "login")
    gesture_count = sum(1 for l in logs if l["action_type"] == "gesture_used")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(stat_card("📁", stats["total_files"], "Vault Files"), unsafe_allow_html=True)
    with col2:
        st.markdown(stat_card("💾", stats["size_formatted"], "Storage Used"), unsafe_allow_html=True)
    with col3:
        st.markdown(stat_card("🔓", login_count, "Sign-ins"), unsafe_allow_html=True)
    with col4:
        st.markdown(stat_card("🤚", gesture_count, "Gestures"), unsafe_allow_html=True)

    st.divider()

    st.markdown("## Quick Actions")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(info_card("🤚", "Gesture Control", "Control your system with hand gestures"), unsafe_allow_html=True)
        if st.button("Launch", key="dash_gesture", use_container_width=True):
            st.session_state.nav_page = "Gesture Control"
            st.rerun()

    with col2:
        st.markdown(info_card("🔒", "Secure Vault", "Store and manage your files securely"), unsafe_allow_html=True)
        if st.button("Open", key="dash_vault", use_container_width=True):
            st.session_state.nav_page = "My Vault"
            st.rerun()

    with col3:
        st.markdown(info_card("🎙️", "Voice Control", "Navigate using voice commands"), unsafe_allow_html=True)
        if st.button("Activate", key="dash_voice", use_container_width=True):
            st.session_state.nav_page = "Voice Commands"
            st.rerun()

    with col4:
        st.markdown(info_card("📋", "Activity Logs", "Monitor all system activity"), unsafe_allow_html=True)
        if st.button("View", key="dash_logs", use_container_width=True):
            st.session_state.nav_page = "Activity Logs"
            st.rerun()

    st.divider()

    st.markdown("## Recent Activity")
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
        st.info("No activity recorded yet.")


# ═══════════════════════════════════════════════
#  GESTURE CONTROL
# ═══════════════════════════════════════════════
def gesture_page():
    page_header("Gesture Control", "Hand tracking interface")

    settings = db.get_gesture_settings(st.session_state.user_id)
    sensitivity = settings.get("sensitivity", 5)

    col1, col2 = st.columns([3, 2])

    # Detect if running on a cloud server (no camera available)
    is_cloud = os.environ.get("STREAMLIT_SERVER_HEADLESS") == "true" or not os.path.exists("/dev/video0") and sys.platform == "linux"

    with col1:
        st.markdown("### Launch Controller")

        if is_cloud:
            st.markdown("""
            <div class="hud-card">
                <h3>⚠️ Cloud Environment Detected</h3>
                <p>Gesture control requires a <strong>local webcam</strong> and cannot run on cloud servers like Streamlit Cloud.</p>
                <p>To use this feature, run SENTINEL locally:</p>
                <p><code>pip install -r requirements.txt</code></p>
                <p><code>streamlit run app.py</code></p>
            </div>
            """, unsafe_allow_html=True)
            st.warning("Gesture control is only available when running locally with a webcam.")
        else:
            st.markdown("""
            <div class="hud-card">
                <h3>How It Works</h3>
                <p>Opens a camera window — your hand controls the mouse cursor.</p>
                <p>Actions fire <strong>once per gesture</strong> (no repeated triggers).</p>
                <p>Close your <strong>fist</strong> anytime to pause tracking.</p>
                <p>Press <strong>Q</strong> in the camera window to quit.</p>
            </div>
            """, unsafe_allow_html=True)

        new_sensitivity = st.slider("Sensitivity", 1, 10, sensitivity,
                                     help="Higher = faster cursor, more responsive clicks")

        if new_sensitivity != sensitivity:
            db.update_gesture_settings(st.session_state.user_id, True, new_sensitivity)
            sensitivity = new_sensitivity

        if not is_cloud:
            if st.button("Start Gesture Control", type="primary", use_container_width=True):
                logger.log_gesture_session_start(st.session_state.user_id)
                script = os.path.join(PROJECT_ROOT, "modules", "gesture_control.py")
                subprocess.Popen([sys.executable, script, str(sensitivity), str(st.session_state.user_id)])
                st.success("Gesture control initialized — Camera window is active")
                st.balloons()

    with col2:
        st.markdown("### Gesture Reference")

        gestures = [
            ("☝️", "INDEX FINGER", "Move mouse cursor"),
            ("🤏", "PINCH", "Left click (thumb + index)"),
            ("✌️", "V SIGN", "Scroll up / down"),
            ("✊", "FIST", "Pause — stop tracking"),
            ("🖐️", "OPEN PALM", "Right click"),
            ("3️⃣", "THREE FINGERS", "Double click"),
            ("👍", "THUMBS UP", "Volume Up"),
            ("🤘", "ROCK ON", "Volume Down"),
        ]

        gesture_html = '<div style="display:flex; flex-wrap:wrap; gap:8px;">'
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

    st.markdown("### Gesture History")
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
        st.info("No gesture activity recorded yet. Start the controller to begin.")


# ═══════════════════════════════════════════════
#  VOICE COMMANDS
# ═══════════════════════════════════════════════
def voice_page():
    page_header("Voice Commands", "Speech recognition interface")

    available = vc.is_available()
    missing = vc.get_missing_packages()

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### Voice Interface")

        if not available:
            st.markdown(f"""
            <div class="hud-card">
                <h3>Packages Required</h3>
                <p>Install voice dependencies to enable this module:</p>
                <p><code>pip install {' '.join(missing)}</code></p>
            </div>
            """, unsafe_allow_html=True)
            st.warning(f"Missing packages: {', '.join(missing)}")
        else:
            st.markdown("""
            <div class="voice-indicator">
                <div class="voice-wave">
                    <span></span><span></span><span></span><span></span><span></span>
                </div>
                <span>Voice recognition — Ready</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div class="hud-card" style="margin-top:16px;">
                <h3>How to Use</h3>
                <p>1. Click <strong>"Activate Voice Control"</strong> below</p>
                <p>2. Speak a command clearly (e.g., "open vault", "dashboard")</p>
                <p>3. The system processes your voice and executes the command</p>
                <p>4. You'll hear audio feedback confirming the action</p>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Activate Voice Control", type="primary", use_container_width=True):
                st.info("Voice control is active. Speak a command...")
                st.session_state.voice_active = True

            st.markdown("### Text Command Input")
            st.caption("Type a command if microphone is not available")

            cmd_input = st.text_input("Enter command", placeholder="e.g., dashboard, vault, logs, help...",
                                       label_visibility="collapsed")
            if cmd_input:
                engine = vc.VoiceEngine()
                cmd_key, cmd_info = engine._match_command(cmd_input)

                if cmd_info:
                    st.success(f"Command recognized: {cmd_info['response']}")
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
                    st.warning(f'Unknown command: "{cmd_input}" — Say "help" for available commands')

    with col2:
        st.markdown("### Command Reference")

        engine = vc.VoiceEngine()
        groups = engine.get_all_commands()

        for group_name, cmds in groups.items():
            st.markdown(f"**{group_name.title()}**")
            for cmd in cmds:
                st.markdown(f"""
                <div class="gesture-card" style="display:block; margin:4px 0; text-align:left; padding:10px 16px;">
                    <span style="color:var(--primary-light); font-weight:600; font-size:0.82rem;">"{cmd['command']}"</span>
                    <span style="color:var(--text-muted); font-size:0.78rem; float:right;">→ {cmd['response']}</span>
                </div>
                """, unsafe_allow_html=True)

        if st.session_state.get("voice_history"):
            st.markdown("### Voice Log")
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
    page_header("Secure Vault", "Encrypted file storage")

    stats = vault.get_storage_stats(st.session_state.user_id)
    st.markdown(f"""
    <div class="vault-status">
        Status: Unlocked &nbsp;·&nbsp; Files: {stats['total_files']} &nbsp;·&nbsp; Storage: {stats['size_formatted']} &nbsp;·&nbsp; Owner: {st.session_state.username}
    </div>
    """, unsafe_allow_html=True)

    tab_upload, tab_browse, tab_search = st.tabs(["Upload", "Browse", "Search"])

    with tab_upload:
        st.markdown("### Upload File")

        uploaded = st.file_uploader(
            "Select a file to upload",
            type=None,
            accept_multiple_files=False,
            help="Max 100MB per file. All formats supported.",
        )

        category = st.selectbox("Category", ["Auto-detect"] + vault.CATEGORIES)

        if uploaded and st.button("Upload & Store", type="primary", use_container_width=True):
            cat = None if category == "Auto-detect" else category
            ok, msg, info = vault.save_file(st.session_state.user_id, uploaded, cat)
            if ok:
                st.success(f"File uploaded — {msg}")
                logger.log_file_upload(st.session_state.user_id, uploaded.name, info["category"])
            else:
                st.error(f"Upload failed — {msg}")

    with tab_browse:
        st.markdown("### Browse Files")

        filter_cat = st.selectbox("Filter by category", ["All"] + vault.CATEGORIES, key="browse_cat")
        files = vault.get_user_files(st.session_state.user_id, None if filter_cat == "All" else filter_cat)

        if not files:
            st.info("Your vault is empty. Upload files to get started.")
        else:
            for f in files:
                icon = '📄' if f['category'] == 'Documents' else '🖼️' if f['category'] == 'Photos' else '🎬' if f['category'] == 'Videos' else '📎'
                size_str = vault.format_file_size(f['file_size'] or 0)

                with st.expander(f"{icon}  {f['original_filename']}  ·  {size_str}  ·  {f['category']}"):
                    col1, col2, col3 = st.columns([2, 1, 1])

                    with col1:
                        st.markdown(f"""
                        <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.8;">
                            <strong>Uploaded:</strong> {f['uploaded_at']}<br>
                            <strong>Type:</strong> {f['file_type']}<br>
                            <strong>Views:</strong> {f['access_count']}
                        </div>
                        """, unsafe_allow_html=True)

                    with col2:
                        data, name, mime = vault.get_file_content(f["file_id"])
                        if data:
                            st.download_button("📥 Download", data, name, mime, key=f"dl_{f['file_id']}")
                            logger.log_file_view(st.session_state.user_id, f["original_filename"])

                    with col3:
                        if st.button("🗑️ Delete", key=f"del_{f['file_id']}"):
                            ok, msg = vault.delete_file(f["file_id"])
                            if ok:
                                logger.log_file_delete(st.session_state.user_id, f["original_filename"])
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                    if f["file_type"] in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
                        if data:
                            st.image(data, caption=f["original_filename"], width=300)

    with tab_search:
        st.markdown("### Search Vault")
        query = st.text_input("Search files", placeholder="e.g., report, photo, video...")

        if query:
            results = vault.search_user_files(st.session_state.user_id, query)
            if results:
                st.success(f"{len(results)} file(s) found")
                for f in results:
                    st.markdown(f"""
                    <div class="log-entry log-info">
                        📎 <strong>{f['original_filename']}</strong> — {f['category']} — {vault.format_file_size(f['file_size'] or 0)}
                        <span class="log-timestamp">{f['uploaded_at']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("No matching files found.")


# ═══════════════════════════════════════════════
#  ACTIVITY LOGS
# ═══════════════════════════════════════════════
def logs_page():
    page_header("Activity Logs", "System monitoring & audit trail")

    col1, col2 = st.columns([1, 3])
    with col1:
        filter_type = st.selectbox("Filter", [
            "All", "login", "login_failed", "file_upload", "file_view",
            "file_delete", "gesture_used", "gesture_session", "settings_change", "logout",
        ])
    with col2:
        limit = st.slider("Max entries", 10, 200, 50)

    if filter_type == "All":
        logs = db.get_user_logs(st.session_state.user_id, limit)
    else:
        logs = db.get_logs_by_type(st.session_state.user_id, filter_type, limit)

    if not logs:
        st.info("No activity logs found.")
        return

    success_count = sum(1 for l in logs if l["success"])
    fail_count = len(logs) - success_count

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(stat_card("📊", len(logs), "Total Events"), unsafe_allow_html=True)
    with col2:
        st.markdown(stat_card("✅", success_count, "Successful"), unsafe_allow_html=True)
    with col3:
        st.markdown(stat_card("❌", fail_count, "Failed"), unsafe_allow_html=True)

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
            {icon} {status_icon} <strong>{log['action_type'].replace('_', ' ').title()}</strong> — {log['action_details'] or ''}
            <span class="log-timestamp">{log['timestamp']}</span>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════
def settings_page():
    page_header("Settings", "Account & system configuration")

    tab_profile, tab_gesture, tab_security = st.tabs(
        ["Profile", "Gesture Config", "Security"]
    )

    user = db.get_user_by_id(st.session_state.user_id)

    with tab_profile:
        st.markdown("### Profile Information")

        st.markdown(f"""
        <div class="hud-card">
            <p><strong>Username:</strong> {user['username']}</p>
            <p><strong>Email:</strong> {user['email'] or 'Not set'}</p>
            <p><strong>Account created:</strong> {user['created_at']}</p>
            <p><strong>Last login:</strong> {user['last_login'] or 'N/A'}</p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown("### Update Face Data")
        st.warning("Re-register your face if recognition accuracy has decreased.")

        if st.button("Re-register Face"):
            st.session_state.re_register = True
            st.rerun()

        if st.session_state.get("re_register"):
            img = st.camera_input("Capture new face sample", key="reregister_cam")
            if img:
                image = Image.open(img).convert("RGB")
                frame = np.array(image)
                recognizer = get_face_recognizer()
                enc = recognizer.extract_encoding(frame)
                if enc is not None:
                    db.update_face_encoding(st.session_state.user_id, enc)
                    logger.log_settings_change(st.session_state.user_id, "face_data", "updated")
                    st.success("Face data updated successfully")
                    st.session_state.re_register = False
                else:
                    st.error("No face detected. Please try again.")

    with tab_gesture:
        st.markdown("### Gesture Configuration")
        settings = db.get_gesture_settings(st.session_state.user_id)

        enabled = st.toggle("Enable gesture control", value=bool(settings["gesture_enabled"]))
        sensitivity = st.slider("Sensitivity level", 1, 10, settings["sensitivity"],
                                help="1 = Conservative · 10 = Aggressive")

        st.markdown("""
        <div class="hud-card">
            <h3>Sensitivity Guide</h3>
            <p><strong>1–3:</strong> Conservative — fewer false triggers, slower response</p>
            <p><strong>4–6:</strong> Balanced — optimal for most users</p>
            <p><strong>7–10:</strong> Aggressive — fastest response, may misfire</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Save Configuration"):
            db.update_gesture_settings(st.session_state.user_id, enabled, sensitivity)
            logger.log_settings_change(st.session_state.user_id, "gesture_settings",
                                        f"enabled={enabled}, sensitivity={sensitivity}")
            st.success("Configuration saved")

    with tab_security:
        st.markdown("### Change Password")

        with st.form("change_pw"):
            new_pw = st.text_input("New password", type="password")
            confirm_pw = st.text_input("Confirm password", type="password")
            submit = st.form_submit_button("Update Password")

            if submit:
                if not new_pw:
                    st.error("Password cannot be empty.")
                elif new_pw != confirm_pw:
                    st.error("Passwords do not match.")
                else:
                    db.update_user_password(st.session_state.user_id, new_pw)
                    logger.log_settings_change(st.session_state.user_id, "password", "changed")
                    st.success("Password updated successfully")

        st.divider()
        st.markdown("### Delete Account")
        st.error("Warning: This action is permanent and cannot be undone.")

        if st.button("Delete My Account"):
            st.session_state.confirm_delete = True

        if st.session_state.get("confirm_delete"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Confirm Deletion", type="primary"):
                    db.delete_user(st.session_state.user_id)
                    logger.log_logout(st.session_state.user_id)
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
            with col2:
                if st.button("Cancel"):
                    st.session_state.confirm_delete = False
                    st.rerun()


# ═══════════════════════════════════════════════
#  MAIN APP — SIDEBAR + ROUTING
# ═══════════════════════════════════════════════
def main_app():
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding:12px 0;">
            <div style="font-size:1.5rem; font-weight:800; letter-spacing:-0.5px;
                        background: linear-gradient(135deg, #f8fafc, #818cf8);
                        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                        background-clip: text;">
                SENTINEL
            </div>
            <div style="font-size:0.7rem; color:var(--text-muted); letter-spacing:1.5px;
                        font-weight:500; margin-top:4px;">
                Professional Edition v2.0
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        st.markdown(f"""
        <div class="sidebar-profile">
            <span class="avatar">👤</span>
            <div class="name">{st.session_state.username}</div>
            <div class="role">Authorized User</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

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
                f"{icon}  {page}",
                key=f"nav_{page}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.nav_page = page
                st.rerun()

        st.divider()

        st.markdown("""
        <div class="sys-status">
            <span class="status-label">Status:</span>
            <span class="status-value">Operational</span><br>
            <span class="status-label">Modules:</span> 6 Active<br>
            <span class="status-label">Security:</span>
            <span class="status-value">Normal</span>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        if st.button("🚪  Sign Out", use_container_width=True):
            logger.log_logout(st.session_state.user_id)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

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
