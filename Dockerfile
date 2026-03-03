# ── SENTINEL Docker Image ─────────────────────
# Deploys the Streamlit web dashboard.
# Gesture control (PyAutoGUI) is disabled inside Docker
# because there's no physical display — use the local
# install method on machines where you need gesture control.

FROM python:3.10-slim

# System deps for OpenCV & MediaPipe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Download MediaPipe models at build time
RUN python -c "\
from modules.face_recognition import ensure_face_model, ensure_hand_model; \
ensure_face_model(); ensure_hand_model()"

# Streamlit config
RUN mkdir -p ~/.streamlit && \
    echo '[server]\nheadless = true\nport = 8501\naddress = \"0.0.0.0\"\nenableCORS = false\nenableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false' > ~/.streamlit/config.toml

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py"]
