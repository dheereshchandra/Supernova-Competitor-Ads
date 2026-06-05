#!/usr/bin/env bash
# One-time setup: install Homebrew Python 3.13 + all pipeline deps.
# Run with: bash 01_install_python_and_deps.sh
set -e

echo "===> Checking for Homebrew..."
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -d /opt/homebrew/bin ]; then
        export PATH="/opt/homebrew/bin:$PATH"
    elif [ -d /usr/local/Homebrew/bin ]; then
        export PATH="/usr/local/bin:$PATH"
    fi
fi
echo "brew: $(brew --version | head -1)"

echo "===> Installing Python 3.13..."
brew install python@3.13 || brew upgrade python@3.13 || true
echo "python3.13: $(python3.13 --version)"

echo "===> Installing pipeline dependencies into Python 3.13..."
python3.13 -m pip install --upgrade --break-system-packages --user \
    yt-dlp requests openpyxl boto3 python-docx Pillow google-generativeai

echo "===> Verifying installs..."
python3.13 -c "import yt_dlp, requests, openpyxl, boto3, docx, PIL, google.generativeai; print('all deps importable')"

PY_BIN_DIR="$HOME/Library/Python/3.13/bin"
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$PY_BIN_DIR"; then
    echo "===> Adding $PY_BIN_DIR to PATH in ~/.zshrc..."
    echo "export PATH=\"$PY_BIN_DIR:\$PATH\"" >> ~/.zshrc
    export PATH="$PY_BIN_DIR:$PATH"
fi

echo ""
echo "===> Setup complete. Now run: bash 02_resume_step2.sh"
