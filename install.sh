#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════╗
# ║  SENTINEL — One-Click Installer (Linux / macOS)          ║
# ╚══════════════════════════════════════════════════════════╝

set -e

echo ""
echo "  ========================================"
echo "   SENTINEL - AI Face & Gesture System"
echo "   One-Click Installer (Linux / macOS)"
echo "  ========================================"
echo ""

# ── Check Python ────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo "        Install it with:"
    echo "          Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "          macOS:         brew install python"
    exit 1
fi

PYVER=$(python3 --version 2>&1)
echo "[OK] Found $PYVER"

# ── Create virtual environment ──────────────
if [ ! -d ".venv" ]; then
    echo ""
    echo "[1/4] Creating virtual environment..."
    python3 -m venv .venv
    echo "      Done."
else
    echo "[1/4] Virtual environment already exists - skipping."
fi

# ── Activate and install deps ───────────────
echo ""
echo "[2/4] Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
echo "      Done."

# ── Download AI models ──────────────────────
echo ""
echo "[3/4] Downloading AI models..."
python -c "from modules.face_recognition import ensure_face_model, ensure_hand_model; ensure_face_model(); ensure_hand_model()" || \
    echo "[WARNING] Model download failed. They will download on first run."
echo "      Done."

# ── Create launcher script ──────────────────
echo ""
echo "[4/4] Creating launcher..."
cat > run_sentinel.sh << 'LAUNCHER'
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
streamlit run app.py
LAUNCHER
chmod +x run_sentinel.sh
echo "      Done."

echo ""
echo "  ========================================"
echo "   Installation Complete!"
echo ""
echo "   To start SENTINEL:"
echo "     ./run_sentinel.sh"
echo "     Or: source .venv/bin/activate && streamlit run app.py"
echo ""
echo "   Open in browser: http://localhost:8501"
echo "  ========================================"
echo ""
