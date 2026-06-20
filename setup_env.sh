#!/bin/bash
# ============================================================
#  Setup Script — Inventory Management System (AIAT Stemland)
#  Installs Python 3.11, system dependencies, and all Python
#  packages required to run the application.
# ============================================================

set -e

PYTHON=python3.11
VENV_DIR="$(dirname "$0")/venv"

echo "======================================"
echo " AIAT Stemland Inventory Setup"
echo "======================================"

# ── 1. System packages ───────────────────────────────────────
echo ""
echo "[1/5] Installing system dependencies..."
sudo apt-get update -y
sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3.11-tk \
    python3-pip \
    libzbar0 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgtk-3-dev \
    tk-dev \
    espeak \
    espeak-ng \
    ffmpeg \
    v4l-utils \
    git

echo "  System packages installed."

# ── 2. Create virtual environment ────────────────────────────
echo ""
echo "[2/5] Creating Python 3.11 virtual environment at: $VENV_DIR"
$PYTHON -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
echo "  Virtual environment created."

# ── 3. Upgrade pip ───────────────────────────────────────────
echo ""
echo "[3/5] Upgrading pip..."
pip install --upgrade pip setuptools wheel

# ── 4. Install Python dependencies ───────────────────────────
echo ""
echo "[4/5] Installing Python packages..."
pip install \
    opencv-python==4.13.0.92 \
    insightface==1.0.1 \
    onnxruntime==1.26.0 \
    onnx==1.21.0 \
    faiss-cpu==1.14.2 \
    numpy==2.4.5 \
    scipy==1.17.1 \
    Pillow==12.2.0 \
    pyzbar==0.1.9 \
    pyttsx3 \
    pyaudio

echo "  Python packages installed."

# ── 5. Download InsightFace buffalo_sc model ─────────────────
echo ""
echo "[5/5] Pre-downloading InsightFace buffalo_sc model..."
python - <<'PYEOF'
import insightface
from insightface.app import FaceAnalysis
print("  Downloading model (first run only)...")
app = FaceAnalysis(name='buffalo_sc', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=0, det_size=(320, 320))
print("  Model ready.")
PYEOF

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "======================================"
echo " Setup complete!"
echo "======================================"
echo ""
echo " To run the application:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo " Or use the launch script:"
echo "   ./run.sh"
echo ""

# Create a convenience launch script
cat > "$(dirname "$0")/run.sh" <<'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/venv/bin/activate"
cd "$DIR"
python main.py
EOF
chmod +x "$(dirname "$0")/run.sh"
echo " run.sh created for quick launch."
