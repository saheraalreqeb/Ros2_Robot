#!/bin/bash
# install.sh — One-command installer for Ros2 Robot
#
# Usage (inside WSL):
#   bash install.sh
#
# What this does:
#   1. Installs the missing Qt system library (libxcb-cursor0)
#   2. Installs Python dependencies
#   3. Creates a permanent `ros2_robot` command in ~/.local/bin (no sudo needed)
#   4. Ensures ~/.local/bin is on your PATH

set -e

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if ! command -v sudo &> /dev/null; then
        echo "❌ sudo is required but not installed. Please install sudo or run as root."
        exit 1
    fi
    SUDO="sudo"
fi

# Detect if we are running from a local checkout or via curl/wget
if [ -f "requirements.txt" ] && [ -f "main.py" ]; then
    REPO_DIR="$(pwd)"
elif [ -f "$(dirname "${BASH_SOURCE[0]}")/requirements.txt" ] 2>/dev/null; then
    REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    # We are running via curl/wget online. We need to clone the repo first.
    INSTALL_DIR="$HOME/Ros2_Robot"
    echo "➡  Running online installer..."
    echo "➡  Cloning Ros2_Robot repository to $INSTALL_DIR..."
    if ! command -v git &> /dev/null; then
        echo "❌  git is not installed. Installing git (requires sudo)..."
        $SUDO apt-get update -q && $SUDO apt-get install -y -q git
    fi
    rm -rf "$INSTALL_DIR"
    git clone https://github.com/saheraalreqeb/Ros2_Robot.git "$INSTALL_DIR"
    REPO_DIR="$INSTALL_DIR"
fi

BIN_SRC="$REPO_DIR/ros2_robot_bin"
LOCAL_BIN="$HOME/.local/bin"
LINK="$LOCAL_BIN/ros2_robot"

echo ""
echo "  Ros2 Robot — Installer"
echo "  ════════════════════════════════"
echo "  Repo: $REPO_DIR"
echo ""

# ── 0. Remove stale /usr/local/bin copy if present ────────────────────────
if [ -f /usr/local/bin/ros2_robot ] && [ ! -L /usr/local/bin/ros2_robot ]; then
    echo "⚠  Stale copy found in /usr/local/bin — removing (needs sudo once)..."
    $SUDO rm -f /usr/local/bin/ros2_robot
    echo "✓  Removed"
fi

# ── 1. System dependencies ─────────────────────────────────────────────────
echo "[ 1/4 ] Installing system dependencies..."
$SUDO apt-get update -q 2>/dev/null || true
$SUDO apt-get install -y -q libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libgl1 libglib2.0-0 libxcb-xfixes0 2>/dev/null
echo "        ✓  Qt platform dependencies"

# ── 2. Python dependencies ─────────────────────────────────────────────────
echo "[ 2/4 ] Installing Python dependencies..."
if ! command -v pip3 &> /dev/null; then
    echo "pip3 wasn't installed >>> installing pip3..."
    $SUDO apt-get update -q 2>/dev/null || true
    $SUDO apt-get install -y -q python3-pip 2>/dev/null
    echo ">> install done, you need to open a new terminal and rerun the installation."
    exit 1
fi

if ! pip3 install -q -r "$REPO_DIR/requirements.txt" 2>/dev/null; then
    # Fallback for PEP 668 externally-managed environments (e.g., Ubuntu 24.04 / Jazzy)
    pip3 install -q --break-system-packages -r "$REPO_DIR/requirements.txt"
fi
echo "        ✓  PySide6, psutil, PyYAML, qtawesome"

# ── 3. Create ~/.local/bin symlink ─────────────────────────────────────────
echo "[ 3/4 ] Creating ros2_robot command..."
mkdir -p "$LOCAL_BIN"
rm -f "$LINK"
ln -sf "$BIN_SRC" "$LINK"
chmod +x "$BIN_SRC"
echo "        ✓  $LINK -> $BIN_SRC"

# ── 4. Ensure PATH includes ~/.local/bin ───────────────────────────────────
echo "[ 4/4 ] Checking PATH..."
BASHRC="$HOME/.bashrc"
if ! grep -qF '.local/bin' "$BASHRC" 2>/dev/null; then
    {
        echo ""
        echo "# Added by ros2_robot install.sh"
        echo 'export PATH="$HOME/.local/bin:$PATH"'
    } >> "$BASHRC"
    echo "        ✓  Added ~/.local/bin to PATH in ~/.bashrc"
else
    echo "        ✓  ~/.local/bin already in PATH"
fi

echo ""
echo "  ════════════════════════════════"
echo "  Installation complete!"
echo ""
echo "  Run:  ros2_robot"
echo "  (Open a new terminal if PATH was just updated)"
echo "  ════════════════════════════════"
echo ""
