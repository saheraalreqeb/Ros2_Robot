#!/bin/bash
# install.sh, One-command installer for Ros2 Robot
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
        if command -v apt-get &> /dev/null; then
            $SUDO apt-get update -q && $SUDO apt-get install -y -q git
        elif command -v dnf &> /dev/null; then
            $SUDO dnf install -y git
        elif command -v pacman &> /dev/null; then
            $SUDO pacman -Sy --noconfirm git
        else
            echo "❌  Unsupported package manager. Please install git manually."
            exit 1
        fi
    fi
    rm -rf "$INSTALL_DIR"
    git clone https://github.com/saheraalreqeb/Ros2_Robot.git "$INSTALL_DIR"
    REPO_DIR="$INSTALL_DIR"
fi

BIN_SRC="$REPO_DIR/ros2_robot_bin"
LOCAL_BIN="$HOME/.local/bin"
LINK="$LOCAL_BIN/ros2_robot"

echo ""
echo "  Ros2 Robot, Installer"
echo "  ════════════════════════════════"
echo "  Repo: $REPO_DIR"
echo ""

# ── 0. Remove stale /usr/local/bin copy if present ────────────────────────
if [ -f /usr/local/bin/ros2_robot ] && [ ! -L /usr/local/bin/ros2_robot ]; then
    echo "⚠  Stale copy found in /usr/local/bin, removing (needs sudo once)..."
    $SUDO rm -f /usr/local/bin/ros2_robot
    echo "✓  Removed"
fi

# ── 1. System dependencies ─────────────────────────────────────────────────
echo "[ 1/5 ] Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    $SUDO apt-get update -q 2>/dev/null || true
    $SUDO apt-get install -y -q libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libgl1 libegl1 libglib2.0-0 2>/dev/null
elif command -v dnf &> /dev/null; then
    $SUDO dnf install -y -q xcb-util-cursor xcb-util-xinerama libxkbcommon-x11 libglvnd-glx libglvnd-egl glib2 2>/dev/null || true
elif command -v pacman &> /dev/null; then
    $SUDO pacman -Sy --noconfirm --quiet xcb-util-cursor xcb-util-xinerama libxkbcommon-x11 libglvnd glib2 2>/dev/null || true
else
    echo "⚠  Unsupported package manager. Please install Qt X11 dependencies manually."
fi
echo "        ✓  Qt platform dependencies"

# ── 2. Python dependencies ─────────────────────────────────────────────────
echo "[ 2/5 ] Installing Python dependencies..."
if ! command -v pip3 &> /dev/null || ! python3 -c "import ensurepip" &>/dev/null; then
    echo "Required Python packages (pip/venv) are missing or incomplete. Installing..."
    if command -v apt-get &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")
        VENV_PKGS="python3-venv"
        if [ -n "$PYTHON_VERSION" ]; then
            VENV_PKGS="python3-venv python${PYTHON_VERSION}-venv"
        fi
        $SUDO apt-get update -q 2>/dev/null || true
        $SUDO apt-get install -y -q python3-pip $VENV_PKGS 2>/dev/null
    elif command -v dnf &> /dev/null; then
        $SUDO dnf install -y python3-pip 2>/dev/null || true
    elif command -v pacman &> /dev/null; then
        $SUDO pacman -Sy --noconfirm python-pip 2>/dev/null || true
    fi
fi

VENV_DIR="$REPO_DIR/.venv"
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python" ] || [ ! -f "$VENV_DIR/bin/pip" ]; then
    echo "Creating transparent Python virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

echo "Installing requirements into isolated environment..."
"$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
echo "        ✓  PySide6, psutil, PyYAML, qtawesome (isolated)"

# ── 3. Create ~/.local/bin symlink ─────────────────────────────────────────
echo "[ 3/5 ] Creating ros2_robot command..."
mkdir -p "$LOCAL_BIN"
rm -f "$LINK"
ln -sf "$BIN_SRC" "$LINK"
chmod +x "$BIN_SRC"
echo "        ✓  $LINK -> $BIN_SRC"

# ── 4. Ensure PATH includes ~/.local/bin ───────────────────────────────────
echo "[ 4/5 ] Checking PATH..."
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

# ── 5. Create Desktop Shortcut ───────────────────────────────────────────────
echo "[ 5/5 ] Creating Desktop Shortcut..."
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
DESKTOP_FILE="$APPS_DIR/ros2_robot.desktop"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=Ros2 Robot
Comment=Modern GUI for ROS 2 Workspaces
Exec=$HOME/.local/bin/ros2_robot
Icon=applications-engineering
Terminal=false
Categories=Development;Engineering;
EOF

chmod +x "$DESKTOP_FILE"
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi
echo "        ✓  Created ~/.local/share/applications/ros2_robot.desktop"

echo ""
echo "  ════════════════════════════════"
echo "  Installation complete!"
echo ""
echo "  Run:  ros2_robot"
echo "  (Open a new terminal if PATH was just updated)"
echo "  ════════════════════════════════"
echo ""
