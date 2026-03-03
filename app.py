"""
SENTINEL — AI-Powered Face Recognition & Gesture Control System
Main Streamlit Application

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
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ── Init ──────────────────────────────────────
def init_app():
    """One-time initialisation: DB, models, session state."""
    db.init_db()

    # Download models if needed
    if "models_ready" not in st.session_state:
        with st.spinner("Downloading AI models (first run only)..."):
            ensure_face_model()
            ensure_hand_model()
        st.session_state.models_ready = True

    # Session defaults
    defaults = {
        "logged_in": False,
        "user_id": None,
        "username": None,
        "reg_step": 0,
        "reg_frames": [],
        "reg_username": "",
        "reg_email": "",
        "reg_password": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Cached face recognizer ───────────────────
@st.cache_resource
def get_face_recognizer():
    return FaceRecognizer()


# ═══════════════════════════════════════════════
#  AUTH PAGES
# ═══════════════════════════════════════════════
def auth_page():
    """Login / Register page shown when not logged in."""
    col_spacer1, col_center, col_spacer2 = st.columns([1, 2, 1])

    with col_center:
        st.markdown("""
        <div style="text-align:center; padding: 30px 0 10px 0;">
            <h1 style="font-size:3rem; margin-bottom:0;">🛡️ SENTINEL</h1>
            <p style="color:#8888aa; font-size:1.1rem; margin-top:5px;">
                Secure Access & Touchless Control
            </p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔓 Login", "📝 Register"])

        with tab_login:
            login_page()

        with tab_register:
            register_page()


def login_page():
    """Face recognition login + backup password login."""
    st.subheader("Login with Face Recognition")

    img_data = st.camera_input("Look at the camera and take a photo", key="login_cam")

    if img_data is not None:
        image = Image.open(img_data).convert("RGB")
        frame = np.array(image)

        with st.spinner("Verifying face..."):
            recognizer = get_face_recognizer()
            stored = db.get_all_face_encodings()

            if not stored:
                st.warning("No users registered yet. Please register first.")
                return

            matched, user_info, score = recognizer.verify_face(frame, stored)

        if matched:
            st.session_state.logged_in = True
            st.session_state.user_id = user_info["user_id"]
            st.session_state.username = user_info["username"]
            db.update_last_login(user_info["user_id"])
            logger.log_login_success(user_info["user_id"], "face")

            st.success(f"Welcome back, **{user_info['username']}**! (Match: {score*100:.1f}%)")
            time.sleep(1)
            st.rerun()
        else:
            score_pct = score * 100 if score > 0 else 0
            st.error(f"Face not recognized. Best match: {score_pct:.1f}% (need 80%+)")
            logger.log_login_failed(reason=f"Best score: {score_pct:.1f}%")

    st.divider()
    st.subheader("🔑 Backup: Password Login")

    with st.form("password_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit and username and password:
            user = db.get_user_by_username(username)
            if user and user["password_hash"] and db.verify_password(password, user["password_hash"]):
                st.session_state.logged_in = True
                st.session_state.user_id = user["user_id"]
                st.session_state.username = user["username"]
                db.update_last_login(user["user_id"])
                logger.log_login_success(user["user_id"], "password")
                st.success(f"Welcome, {username}!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Invalid username or password.")
                logger.log_login_failed(reason=f"Bad password for '{username}'")


def register_page():
    """Multi-step face registration."""
    step = st.session_state.reg_step

    if step == 0:
        st.subheader("Step 1: Enter Your Details")
        with st.form("reg_form"):
            username = st.text_input("Username *")
            email = st.text_input("Email")
            password = st.text_input("Backup Password (optional)", type="password")
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
        st.subheader(f"Step 2: Capture Face ({len(st.session_state.reg_frames) + 1}/5)")
        st.info("Take 5 photos with slightly different head angles for better accuracy.")

        prompts = [
            "📸 Look straight at the camera",
            "📸 Turn your head slightly LEFT",
            "📸 Turn your head slightly RIGHT",
            "📸 Tilt your head slightly UP",
            "📸 Look straight again",
        ]
        idx = len(st.session_state.reg_frames)
        if idx < 5:
            st.write(prompts[idx])

        img_data = st.camera_input("Capture face", key=f"reg_cam_{idx}")

        if img_data is not None:
            image = Image.open(img_data).convert("RGB")
            frame = np.array(image)

            # Verify face is detected
            recognizer = get_face_recognizer()
            enc = recognizer.extract_encoding(frame)

            if enc is not None:
                st.session_state.reg_frames.append(frame)
                st.success(f"Sample {len(st.session_state.reg_frames)}/5 captured ✅")

                if len(st.session_state.reg_frames) >= 5:
                    st.session_state.reg_step = 2
                    st.rerun()
                else:
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.warning("No face detected. Please try again.")

        # Navigation
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back"):
                st.session_state.reg_step = 0
                st.session_state.reg_frames = []
                st.rerun()
        with col2:
            if len(st.session_state.reg_frames) >= 3:
                if st.button("Skip remaining → Complete with current samples"):
                    st.session_state.reg_step = 2
                    st.rerun()

    elif step == 2:
        st.subheader("Step 3: Confirm Registration")
        st.write(f"**Username:** {st.session_state.reg_username}")
        st.write(f"**Email:** {st.session_state.reg_email or 'N/A'}")
        st.write(f"**Face samples:** {len(st.session_state.reg_frames)}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Confirm & Register"):
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
                        # Log it
                        user = db.get_user_by_username(st.session_state.reg_username)
                        if user:
                            logger.log_registration(user["user_id"], user["username"])

                        st.success(f"🎉 {db_msg} You can now login!")
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
    st.markdown(f"""
    <div style="text-align:center; padding:20px 0;">
        <h1>Welcome, {st.session_state.username} 👋</h1>
        <p style="color:#8888aa;">SENTINEL Dashboard</p>
    </div>
    """, unsafe_allow_html=True)

    # Stats cards
    stats = vault.get_storage_stats(st.session_state.user_id)
    logs = db.get_user_logs(st.session_state.user_id, limit=100)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📁 Total Files", stats["total_files"])
    with col2:
        st.metric("💾 Storage Used", stats["size_formatted"])
    with col3:
        login_count = sum(1 for l in logs if l["action_type"] == "login")
        st.metric("🔓 Total Logins", login_count)
    with col4:
        gesture_count = sum(1 for l in logs if l["action_type"] == "gesture_used")
        st.metric("🤚 Gestures Used", gesture_count)

    st.divider()

    # Quick actions
    st.subheader("Quick Actions")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="sentinel-card">
            <h3>🤚 Gesture Control</h3>
            <p>Control your computer with hand gestures</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Launch Gesture Control", key="dash_gesture"):
            st.session_state.nav_page = "Gesture Control"
            st.rerun()

    with col2:
        st.markdown("""
        <div class="sentinel-card">
            <h3>🔒 My Vault</h3>
            <p>Access your secure file vault</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Vault", key="dash_vault"):
            st.session_state.nav_page = "My Vault"
            st.rerun()

    with col3:
        st.markdown("""
        <div class="sentinel-card">
            <h3>📋 Activity Logs</h3>
            <p>View your activity history</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("View Logs", key="dash_logs"):
            st.session_state.nav_page = "Activity Logs"
            st.rerun()

    st.divider()

    # Recent activity
    st.subheader("Recent Activity")
    recent = logger.get_formatted_logs(st.session_state.user_id, limit=10)
    if recent:
        for log in recent:
            color_class = "log-success" if log["success"] else "log-failed"
            st.markdown(f"""
            <div class="log-entry {color_class}">
                {log['icon']} {log['status']}  <strong>{log['action']}</strong> — {log['details']}
                <span style="float:right; color:#666; font-size:0.8rem;">{log['timestamp']}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No activity yet.")


# ═══════════════════════════════════════════════
#  GESTURE CONTROL PAGE
# ═══════════════════════════════════════════════
def gesture_page():
    st.header("🤚 Gesture Control")
    st.write("Control your computer with hand gestures — presentations, media, system controls.")

    # Settings
    settings = db.get_gesture_settings(st.session_state.user_id)
    sensitivity = settings.get("sensitivity", 5)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Launch Controller")
        st.info("This opens a separate camera window. Press **'q'** in that window to stop.")

        new_sensitivity = st.slider("Gesture Sensitivity", 1, 10, sensitivity,
                                     help="Higher = more responsive but may cause false detections")

        if new_sensitivity != sensitivity:
            db.update_gesture_settings(st.session_state.user_id, True, new_sensitivity)
            sensitivity = new_sensitivity

        if st.button("🚀 Start Gesture Control", type="primary"):
            logger.log_gesture_session_start(st.session_state.user_id)

            # Launch gesture controller as subprocess
            script = os.path.join(PROJECT_ROOT, "modules", "gesture_control.py")
            python_exe = sys.executable
            subprocess.Popen([
                python_exe, script,
                str(sensitivity),
                str(st.session_state.user_id),
            ])
            st.success("Gesture Control launched! Look for the camera window.")
            st.balloons()

    with col2:
        st.subheader("Gesture Guide")
        gestures = {
            "✊ Fist": "Minimize All (Win+D)",
            "🖐️ Open Palm": "Play / Pause",
            "✌️ Peace (V)": "Screenshot",
            "👍 Thumbs Up": "Volume Up",
            "🤘 Rock On": "Volume Down",
            "3️⃣ Three Fingers": "Alt + Tab",
            "🤙 Pinky Only": "Mute / Unmute",
            "👉 Gun": "Enter Key",
            "👈 Swipe Left": "Previous (←)",
            "👉 Swipe Right": "Next (→)",
        }
        for gesture, action in gestures.items():
            st.markdown(f"**{gesture}** → {action}")

    st.divider()

    # Gesture history
    st.subheader("Recent Gesture Activity")
    gesture_logs = db.get_logs_by_type(st.session_state.user_id, "gesture_used", 20)
    if gesture_logs:
        for log in gesture_logs:
            st.markdown(f"🤚 `{log['action_details']}` — {log['timestamp']}")
    else:
        st.info("No gesture activity yet. Launch the controller to get started!")


# ═══════════════════════════════════════════════
#  VAULT PAGE
# ═══════════════════════════════════════════════
def vault_page():
    st.header("🔒 My Vault")

    tab_upload, tab_browse, tab_search = st.tabs(["📤 Upload", "📂 Browse Files", "🔍 Search"])

    # ── Upload tab ────────────────────────────
    with tab_upload:
        st.subheader("Upload a File")

        uploaded = st.file_uploader(
            "Choose a file",
            type=None,
            accept_multiple_files=False,
            help="Max 100MB. Supported: Documents, Photos, Videos, and more.",
        )

        category = st.selectbox("Category", ["Auto-detect"] + vault.CATEGORIES)

        if uploaded and st.button("📤 Upload File", type="primary"):
            cat = None if category == "Auto-detect" else category
            ok, msg, info = vault.save_file(st.session_state.user_id, uploaded, cat)

            if ok:
                st.success(msg)
                logger.log_file_upload(
                    st.session_state.user_id,
                    uploaded.name,
                    info["category"],
                )
            else:
                st.error(msg)

    # ── Browse tab ────────────────────────────
    with tab_browse:
        st.subheader("Browse Files")

        # Category filter
        filter_cat = st.selectbox("Filter by Category", ["All"] + vault.CATEGORIES, key="browse_cat")

        files = vault.get_user_files(
            st.session_state.user_id,
            None if filter_cat == "All" else filter_cat,
        )

        if not files:
            st.info("No files found. Upload some files first!")
        else:
            # Stats bar
            stats = vault.get_storage_stats(st.session_state.user_id)
            st.caption(f"Total: {stats['total_files']} files | {stats['size_formatted']} used")

            for f in files:
                with st.expander(
                    f"{'📄' if f['category']=='Documents' else '🖼️' if f['category']=='Photos' else '🎬' if f['category']=='Videos' else '📎'} "
                    f"{f['original_filename']}  |  {vault.format_file_size(f['file_size'] or 0)}  |  {f['category']}"
                ):
                    col1, col2, col3 = st.columns([2, 1, 1])

                    with col1:
                        st.write(f"**Uploaded:** {f['uploaded_at']}")
                        st.write(f"**Type:** {f['file_type']}")
                        st.write(f"**Accessed:** {f['access_count']} times")

                    with col2:
                        # Download
                        data, name, mime = vault.get_file_content(f["file_id"])
                        if data:
                            st.download_button(
                                "📥 Download", data, name, mime,
                                key=f"dl_{f['file_id']}",
                            )
                            logger.log_file_view(st.session_state.user_id, f["original_filename"])

                    with col3:
                        # Delete
                        if st.button("🗑️ Delete", key=f"del_{f['file_id']}"):
                            ok, msg = vault.delete_file(f["file_id"])
                            if ok:
                                logger.log_file_delete(st.session_state.user_id, f["original_filename"])
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                    # Preview for images
                    if f["file_type"] in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
                        if data:
                            st.image(data, caption=f["original_filename"], width=300)

    # ── Search tab ────────────────────────────
    with tab_search:
        st.subheader("Search Files")
        query = st.text_input("Enter filename to search", placeholder="e.g., resume, photo")

        if query:
            results = vault.search_user_files(st.session_state.user_id, query)
            if results:
                st.write(f"Found {len(results)} result(s):")
                for f in results:
                    st.markdown(
                        f"📎 **{f['original_filename']}** — {f['category']} — "
                        f"{vault.format_file_size(f['file_size'] or 0)} — {f['uploaded_at']}"
                    )
            else:
                st.warning("No files matching your search.")


# ═══════════════════════════════════════════════
#  ACTIVITY LOGS PAGE
# ═══════════════════════════════════════════════
def logs_page():
    st.header("📋 Activity Logs")

    # Filter options
    col1, col2 = st.columns([1, 2])
    with col1:
        filter_type = st.selectbox("Filter by Action", [
            "All", "login", "login_failed", "file_upload", "file_view",
            "file_delete", "gesture_used", "gesture_session", "settings_change", "logout",
        ])
    with col2:
        limit = st.slider("Number of entries", 10, 200, 50)

    # Get logs
    if filter_type == "All":
        logs = db.get_user_logs(st.session_state.user_id, limit)
    else:
        logs = db.get_logs_by_type(st.session_state.user_id, filter_type, limit)

    if not logs:
        st.info("No activity logs found.")
        return

    # Summary stats
    st.subheader(f"Showing {len(logs)} entries")

    # Timeline
    icons = {
        "login": "🔓", "login_failed": "🔒", "registration": "📝",
        "file_upload": "📤", "file_view": "👁️", "file_delete": "🗑️",
        "gesture_used": "🤚", "gesture_session": "🎮",
        "settings_change": "⚙️", "logout": "🚪",
    }

    for log in logs:
        icon = icons.get(log["action_type"], "📌")
        status_icon = "✅" if log["success"] else "❌"
        color = "#00c864" if log["success"] else "#ff3232"

        st.markdown(f"""
        <div style="border-left: 3px solid {color}; padding: 6px 12px; margin: 4px 0; font-size: 0.9rem;">
            {icon} {status_icon} <strong>{log['action_type']}</strong> — {log['action_details'] or ''}
            <span style="float:right; color:#666; font-size:0.8rem;">{log['timestamp']}</span>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════
#  SETTINGS PAGE
# ═══════════════════════════════════════════════
def settings_page():
    st.header("⚙️ Settings")

    tab_profile, tab_gesture, tab_security = st.tabs(
        ["👤 Profile", "🤚 Gesture Settings", "🔒 Security"]
    )

    user = db.get_user_by_id(st.session_state.user_id)

    # ── Profile ───────────────────────────────
    with tab_profile:
        st.subheader("Profile Information")
        st.write(f"**Username:** {user['username']}")
        st.write(f"**Email:** {user['email'] or 'Not set'}")
        st.write(f"**Member since:** {user['created_at']}")
        st.write(f"**Last login:** {user['last_login'] or 'N/A'}")

        st.divider()
        st.subheader("Update Face Data")
        st.warning("Re-register your face if recognition is not working well.")

        if st.button("📸 Re-register Face"):
            st.session_state.re_register = True
            st.rerun()

        if st.session_state.get("re_register"):
            img = st.camera_input("Take a new face photo (will add to existing data)", key="reregister_cam")
            if img:
                image = Image.open(img).convert("RGB")
                frame = np.array(image)
                recognizer = get_face_recognizer()
                enc = recognizer.extract_encoding(frame)
                if enc is not None:
                    db.update_face_encoding(st.session_state.user_id, enc)
                    logger.log_settings_change(st.session_state.user_id, "face_data", "updated")
                    st.success("Face data updated!")
                    st.session_state.re_register = False
                else:
                    st.error("No face detected. Try again.")

    # ── Gesture Settings ──────────────────────
    with tab_gesture:
        st.subheader("Gesture Control Settings")
        settings = db.get_gesture_settings(st.session_state.user_id)

        enabled = st.toggle("Enable Gesture Control", value=bool(settings["gesture_enabled"]))
        sensitivity = st.slider("Sensitivity", 1, 10, settings["sensitivity"],
                                help="1 = Very strict (fewer false positives)\n10 = Very sensitive (more responsive)")

        st.caption("""
        **Sensitivity guide:**
        - **1-3:** Conservative — fewer false detections, slower response
        - **4-6:** Balanced — good for most users
        - **7-10:** Aggressive — very responsive, may trigger unintended actions
        """)

        if st.button("💾 Save Gesture Settings"):
            db.update_gesture_settings(st.session_state.user_id, enabled, sensitivity)
            logger.log_settings_change(st.session_state.user_id, "gesture_settings",
                                        f"enabled={enabled}, sensitivity={sensitivity}")
            st.success("Settings saved!")

    # ── Security ──────────────────────────────
    with tab_security:
        st.subheader("Change Backup Password")

        with st.form("change_pw"):
            new_pw = st.text_input("New Password", type="password")
            confirm_pw = st.text_input("Confirm Password", type="password")
            submit = st.form_submit_button("Update Password")

            if submit:
                if not new_pw:
                    st.error("Password cannot be empty.")
                elif new_pw != confirm_pw:
                    st.error("Passwords do not match.")
                else:
                    db.update_user_password(st.session_state.user_id, new_pw)
                    logger.log_settings_change(st.session_state.user_id, "password", "changed")
                    st.success("Password updated!")

        st.divider()
        st.subheader("Account")

        st.warning("Deleting your account will remove all your data including vault files.")
        if st.button("⚠️ Delete Account", type="secondary"):
            st.session_state.confirm_delete = True

        if st.session_state.get("confirm_delete"):
            st.error("Are you sure? This action cannot be undone.")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes, delete my account"):
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
#  MAIN APP
# ═══════════════════════════════════════════════
def main_app():
    """Authenticated main application."""

    # Sidebar
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align:center; padding:10px 0;">
            <h2 style="margin:0;">🛡️ SENTINEL</h2>
            <p style="color:#8888aa; font-size:0.85rem; margin:0;">v1.0</p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.write(f"👤 **{st.session_state.username}**")
        st.divider()

        # Navigation
        if "nav_page" not in st.session_state:
            st.session_state.nav_page = "Dashboard"

        pages = ["Dashboard", "Gesture Control", "My Vault", "Activity Logs", "Settings"]
        icons = ["🏠", "🤚", "🔒", "📋", "⚙️"]

        for page, icon in zip(pages, icons):
            if st.sidebar.button(f"{icon} {page}", key=f"nav_{page}",
                                  use_container_width=True,
                                  type="primary" if st.session_state.nav_page == page else "secondary"):
                st.session_state.nav_page = page
                st.rerun()

        st.divider()

        if st.button("🚪 Logout", use_container_width=True):
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
