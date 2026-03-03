# 🛡️ SENTINEL — AI-Powered Face Recognition & Gesture Control System

> **"Secure Access & Touchless Control — The Future of Human-Computer Interaction"**

## 📌 Overview

SENTINEL is an AI-powered system that combines **face recognition authentication** with **hand gesture computer control** and a **personal file vault**. No touch, no keyboard — pure AI-based interaction.

---

## ✅ Features

### 1. Face Recognition Authentication
- One-time face registration (5 samples from different angles)
- Face-based login using cosine similarity matching (80%+ threshold)
- Backup password login option
- MediaPipe FaceLandmarker with 478 facial landmarks

### 2. Hand Gesture Computer Control
| Gesture | Action |
|---------|--------|
| ✊ Fist | Minimize all windows (Win+D) |
| 🖐️ Open Palm | Play / Pause (Space) |
| ✌️ Peace (V) | Screenshot |
| 👍 Thumbs Up | Volume Up |
| 🤘 Rock On | Volume Down |
| 3️⃣ Three Fingers | Alt + Tab |
| 🤙 Pinky Only | Mute / Unmute |
| 👉 Swipe Right | Next slide / Forward |
| 👈 Swipe Left | Previous slide / Back |

### 3. Personal File Vault
- Upload files (Documents, Photos, Videos)
- Browse, search, download, and delete
- Auto-categorization by file extension
- Face-protected access — only **you** can access your vault

### 4. Activity Logs
- Complete activity timeline with icons
- Filter by action type
- Tracks logins, file operations, gesture usage
- Security monitoring

### 5. Settings & Customization
- Gesture sensitivity (1–10 scale)
- Profile management
- Face re-registration
- Backup password management

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the App
```bash
cd sentinel_project
streamlit run app.py
```

### 3. First-Time Setup
1. Click **Register** tab
2. Enter your username and email
3. Take 5 face photos (different angles)
4. Confirm registration
5. Login with your face!

---

## 📁 Project Structure

```
sentinel_project/
├── app.py                      # Main Streamlit web application
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── modules/                    # Core functionality
│   ├── __init__.py
│   ├── database.py             # SQLite CRUD operations
│   ├── face_recognition.py     # Face detection & matching
│   ├── gesture_control.py      # Hand gesture detection & actions
│   ├── vault_manager.py        # File upload/download/delete
│   └── logger.py               # Activity logging
│
├── models/                     # AI models (auto-downloaded)
│   ├── face_landmarker.task    # MediaPipe face model
│   └── hand_landmarker.task    # MediaPipe hand model
│
├── database/                   # SQLite database (auto-created)
│   └── sentinel.db
│
├── vault_storage/              # User files (auto-created)
│   └── user_{id}/
│       ├── documents/
│       ├── photos/
│       └── videos/
│
├── config/
│   └── settings.json           # App configuration
│
└── assets/
    └── styles/
        └── custom.css          # UI theming
```

---

## 🗄️ Database Schema

### `users`
| Column | Type | Description |
|--------|------|-------------|
| user_id | INTEGER PK | Auto-incrementing ID |
| username | TEXT UNIQUE | Login username |
| email | TEXT | User email |
| password_hash | TEXT | SHA-256 backup password |
| face_encoding | BLOB | Pickled face landmarks |
| created_at | TIMESTAMP | Registration date |
| last_login | TIMESTAMP | Last login time |

### `vault_files`
| Column | Type | Description |
|--------|------|-------------|
| file_id | INTEGER PK | File ID |
| user_id | FK | Owner |
| filename | TEXT | Stored filename |
| original_filename | TEXT | User's filename |
| filepath | TEXT | Storage path |
| category | TEXT | Documents/Photos/Videos/Others |
| file_size | INTEGER | Size in bytes |

### `access_logs`
| Column | Type | Description |
|--------|------|-------------|
| log_id | INTEGER PK | Log ID |
| user_id | FK | User who acted |
| action_type | TEXT | login/file_upload/gesture_used/etc |
| action_details | TEXT | Description |
| timestamp | TIMESTAMP | When it happened |
| success | INTEGER | 1=success, 0=failed |

---

## 🔧 Technical Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Streamlit |
| Face Detection | MediaPipe FaceLandmarker |
| Hand Tracking | MediaPipe HandLandmarker |
| System Control | PyAutoGUI |
| Database | SQLite3 |
| Image Processing | OpenCV, Pillow, NumPy |
| Language | Python 3.10+ |

---

## 🧠 How Face Recognition Works

1. **Registration:** Capture 5 images → Extract 478 face landmarks per image → Normalize (center + scale) → Average → Store as encoding
2. **Login:** Capture 1 image → Extract landmarks → Compare with stored encodings using **cosine similarity**
3. **Match:** Similarity ≥ 80% → Access granted ✅

```
cos(θ) = (A · B) / (‖A‖ × ‖B‖)
```

---

---

## 🌐 Deployment Guide — Use on Other Devices

### Important Note
SENTINEL's **gesture control** uses PyAutoGUI, which controls the **local machine**. So the app must run locally on each device where gesture control is needed. The Streamlit web dashboard (face login, vault, logs) can be accessed remotely via browser.

---

### Method 1: Direct Install (Recommended — Any PC)

The easiest way. Copy the project folder to the target device and run the installer.

**Windows:**
```bash
# 1. Copy sentinel_project/ folder to the other PC (USB, zip, GitHub, etc.)
# 2. Double-click setup.bat
# 3. Double-click run_sentinel.bat
# 4. Open http://localhost:8501 in browser
```

**Linux / macOS:**
```bash
# 1. Copy sentinel_project/ folder to the other machine
cd sentinel_project
chmod +x install.sh
./install.sh
./run_sentinel.sh
# 4. Open http://localhost:8501 in browser
```

**Requirements:** Python 3.10+ and a webcam.

---

### Method 2: GitHub (Best for sharing & collaboration)

```bash
# On your machine — push to GitHub:
cd sentinel_project
git init
git add .
git commit -m "Initial commit — SENTINEL v1.0"
git remote add origin https://github.com/YOUR_USERNAME/sentinel.git
git push -u origin main

# On another device — clone and install:
git clone https://github.com/YOUR_USERNAME/sentinel.git
cd sentinel

# Windows:
setup.bat

# Linux/macOS:
chmod +x install.sh && ./install.sh
```

---

### Method 3: Docker (No Python install needed)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
# Build and run:
cd sentinel_project
docker compose up --build -d

# Access at http://localhost:8501
# Stop:
docker compose down
```

> **Note:** Gesture control (PyAutoGUI) is disabled in Docker because there's no display. Use Method 1 or 2 for full functionality including gesture control.

---

### Method 4: LAN Access (Other devices on same Wi-Fi)

If SENTINEL is already running on one PC, other devices on the same network can access the web dashboard:

```
1. Run SENTINEL on the host PC
2. Find host IP:  ipconfig  (Windows)  or  hostname -I  (Linux)
3. On other device, open browser:  http://<HOST_IP>:8501
```

Example: If host IP is `192.168.1.5`, open `http://192.168.1.5:8501`

> **Limitations:** Camera input uses the **browser's** webcam (works remotely). Gesture control only works on the host PC.

---

### Method 5: Cloud VM (AWS / GCP / Azure)

For internet-wide access (without gesture control):

```bash
# 1. Create a VM (Ubuntu 22.04, 2GB+ RAM)
# 2. SSH into the VM
ssh user@your-vm-ip

# 3. Install Python & clone
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
git clone https://github.com/YOUR_USERNAME/sentinel.git
cd sentinel
chmod +x install.sh && ./install.sh

# 4. Run with nohup (stays running after you disconnect)
nohup .venv/bin/streamlit run app.py --server.port 8501 &

# 5. Open firewall port 8501 in your cloud console
# 6. Access at http://your-vm-ip:8501
```

---

### Deployment Quick Reference

| Method | Gesture Control | Remote Access | Difficulty | Best For |
|--------|:-:|:-:|:-:|---|
| Direct Install | ✅ | ❌ | Easy | Personal use on another PC |
| GitHub | ✅ | ❌ | Easy | Sharing with classmates |
| Docker | ❌ | ✅ (LAN) | Medium | Clean isolated setup |
| LAN Access | Host only | ✅ | Easy | Demo on same network |
| Cloud VM | ❌ | ✅ (Internet) | Hard | Public access / demo |

---

## 📝 License

This project is for educational purposes (Final Year Project).
