#!/bin/bash
# uninstall.sh, Removes Ros2 Robot from your system

echo "  Ros2 Robot, Uninstaller"
echo "  ════════════════════════════════"

# 1. Remove the local repository folder
INSTALL_DIR="$HOME/Ros2_Robot"
if [ -d "$INSTALL_DIR" ]; then
    echo "➡ Removing repository directory: $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
    echo "  ✓ Removed"
else
    echo "  ✓ Repository directory not found in $INSTALL_DIR"
fi

# 2. Remove the global command symlinks
LOCAL_BIN_LINK="$HOME/.local/bin/ros2_robot"
if [ -L "$LOCAL_BIN_LINK" ] || [ -f "$LOCAL_BIN_LINK" ]; then
    echo "➡ Removing local command symlink: $LOCAL_BIN_LINK"
    rm -f "$LOCAL_BIN_LINK"
    echo "  ✓ Removed"
fi

if [ -f /usr/local/bin/ros2_robot ]; then
    echo "➡ Removing legacy system command symlink (requires sudo): /usr/local/bin/ros2_robot"
    if command -v sudo &> /dev/null; then
        sudo rm -f /usr/local/bin/ros2_robot
        echo "  ✓ Removed"
    else
        echo "  ⚠ Cannot remove /usr/local/bin/ros2_robot (sudo not available)"
    fi
fi

# 3. Remove the settings file
SETTINGS_FILE="$HOME/.ros2_robot_settings.json"
if [ -f "$SETTINGS_FILE" ]; then
    echo "➡ Removing settings file: $SETTINGS_FILE"
    rm -f "$SETTINGS_FILE"
    echo "  ✓ Removed"
else
    echo "  ✓ Settings file not found"
fi

# 4. Remove the desktop shortcut
DESKTOP_FILE="$HOME/.local/share/applications/ros2_robot.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    echo "➡ Removing desktop shortcut: $DESKTOP_FILE"
    rm -f "$DESKTOP_FILE"
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    fi
    echo "  ✓ Removed"
else
    echo "  ✓ Desktop shortcut not found"
fi

echo ""
echo "  ════════════════════════════════"
echo "  Uninstallation complete!"
echo "  Ros2 Robot has been entirely removed from your system."
echo "  ════════════════════════════════"
echo ""
