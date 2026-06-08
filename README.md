# Ros2 Robot

*ROS is used for robots, but isn't it time to have its own robot?*  

**Ros2 Robot** is a modern, futuristic GUI designed to automate and manage your ROS 2 projects and workspaces—developed with the help of advanced coding agents. Built on PySide6, it allows you to create packages, run nodes, inspect topics, manage bags, build launch files, and more, all from one clean, premium interface.

---

## Screenshots

> Launch the app to see the dark-themed futuristic UI with icon-rich sidebar navigation and a built-in Settings tab for switching themes and toggling tabs.

---

## Requirements

| Requirement | Version |
|---|---|
| OS | Windows 10/11 with **WSL 2** (Ubuntu 22.04 recommended) |
| ROS 2 | Humble / Iron / Jazzy / Rolling |
| Python | 3.8 + |
| WSLg | Required for GUI rendering (included in WSL 2 by default) |

> **All commands below must be run inside your WSL terminal**, not Windows PowerShell/CMD.

### Tested Environments

We periodically test `Ros2 Robot` in various environments to ensure compatibility. The following setups have been explicitly verified:
- **Ubuntu 22.04 LTS (WSL 2 & Native)** with **ROS 2 Humble Hawksbill** (Python 3.10)
- **Ubuntu 24.04 LTS (WSL 2 & Native)** with **ROS 2 Jazzy Jalisco** (Python 3.12)

This list is updated every time we verify a new environment.

---

## Installation

Choose one of the two methods below to install **Ros2 Robot**. Method 1 is recommended for most users as it performs everything automatically in a single step.

### Method 1: One-Line Online Installer (Recommended)

Open your terminal and run the following command. This automatically downloads the installer, clones the repository to your home directory (`~/Ros2_Robot`), installs all dependencies, and configures the `ros2_robot` global command:

```bash
curl -sSL https://raw.githubusercontent.com/saheraalreqeb/Ros2_Robot/main/install.sh | bash
```

---

### Method 2: Manual Git Repository Installation

If you prefer to clone the repository to a custom location (e.g., for code modification or active development):

#### 1. Clone the repository and enter the directory
```bash
git clone https://github.com/saheraalreqeb/Ros2_Robot.git
cd Ros2_Robot
```

#### 2. Run the installation script
```bash
bash install.sh
```

---

### What the installer does automatically:
- Installs the system dependency for Qt (`libxcb-cursor0`)
- Installs all Python dependencies (`PySide6`, `psutil`, `PyYAML`, `qtawesome`)
- Creates a permanent `ros2_robot` command symlink in `~/.local/bin` (no `sudo` required for this step)
- Ensures `~/.local/bin` is added to your shell's `PATH`

> If a stale copy of `ros2_robot` exists in `/usr/local/bin` from a previous installation, the script will ask for your sudo password **once** to clean it up, then run purely under user permissions.

---

## Running the App

Open any WSL terminal and run:

```bash
ros2_robot
```

The GUI window will appear on your Windows desktop via **WSLg**.  
The terminal will show a blinking cursor while the app is running — this is normal.

To run in the background and get your terminal back:

```bash
ros2_robot &
```

---

## Features

| Tab | Description |
|---|---|
| **Workspace** | Open or initialise `colcon` workspaces. Build with `colcon build` directly from the UI. |
| **Packages** | Create ROS 2 packages (`ament_python` or `ament_cmake`) with one click. |
| **Nodes** | View all nodes in the workspace. Run or stop individual nodes with a button. |
| **Visualizer** | Live graph of publishers and subscribers across your running nodes. |
| **Launch Manager** | Visually build `.launch.py` files, then run them with live log output. |
| **Tools Hub** | Check and launch common ROS 2 tools (rqt, rviz2, gazebo, etc.). |
| **Topic Inspector** | Browse all active topics, view message types, and echo live data. |
| **Parameters** | Read and set node parameters. Dump/load YAML parameter files. |
| **Bag Manager** | Record and replay ROS 2 bag files with loop and rate controls. |
| **Settings** | Switch between **Dark** and **Light** themes. Show/hide sidebar tabs. |

---

## Troubleshooting

### App doesn't appear after typing `ros2_robot`

WSLg must be enabled. Check with:

```bash
echo $DISPLAY   # should print :0
ls /tmp/.X11-unix/X0   # should exist
```

If missing, make sure you are using **WSL 2** (not WSL 1):

```bash
# In PowerShell (Windows side):
wsl --set-default-version 2
wsl --update
```

### Qt platform plugin error (`xcb` or `wayland`)

Install the missing system library:

```bash
sudo apt-get install -y libxcb-cursor0
```

### `ros2_robot` command not found after re-opening WSL

Re-run the install script:

```bash
bash /mnt/c/Users/pc/Desktop/Ros2_Robot/install.sh
```

Or source your profile manually:

```bash
source ~/.bashrc
```

### GUI works with `python3 main.py` but not `ros2_robot`

Make sure the launcher is executable and the symlink is correct:

```bash
bash install.sh
```

---

## Development

The app is installed in **editable mode**, so any changes you make to the source files are reflected immediately — no reinstall needed.

```
Ros2_Robot/
├── main.py                  # Entry point
├── install.sh               # One-command installer
├── ros2_robot_bin           # Shell launcher (symlinked to ~/.local/bin/ros2_robot)
├── requirements.txt
├── core/
│   ├── ros2_cli.py          # ROS 2 CLI wrapper (WSL-aware)
│   ├── workspace.py         # Workspace discovery
│   └── code_generator.py   # Package/node boilerplate generator
└── gui/
    ├── main_window.py       # Main window + sidebar navigation
    ├── theme.py             # Dark/Light theme system (ThemeManager)
    ├── settings_page.py     # Settings tab
    ├── launch_manager.py    # Launch file builder & runner
    ├── tools_hub.py         # ROS 2 tools cards
    ├── topic_inspector.py   # Topic browser & echo
    ├── parameter_manager.py # Node parameter editor
    ├── bag_manager.py       # Bag record & playback
    └── visualizer.py        # Network graph
```

## Author & Contact

**Saher ALREQEB**
- **Email**: [s.a.alreqeb@gmail.com](mailto:s.a.alreqeb@gmail.com)
- **Website**: [saheralreqeb.work](https://www.saheralreqeb.work/)

---

## License

MIT

