# Ros2 Robot

*ROS is used for robots, but isn't it time to have its own robot?*  

**Ros2 Robot** is a simple, modern GUI designed to manage your ROS 2 projects. Think of it as **GitHub Desktop, but for ROS 2**. 

It eliminates those repetitive, soul-crushing terminal commands so you can actually focus on coding and development. Built on PySide6, it lets you create packages, run nodes, inspect topics, manage bags, and build launch files, all from one clean interface.

---

## Screenshots

> Launch the app to see the dark-themed futuristic UI with icon-rich sidebar navigation and a built-in Settings tab for switching themes and toggling tabs.

---

## Requirements

| Requirement | Version |
|---|---|
| OS | **Native Linux** (Ubuntu 22.04/24.04) or Windows 10/11 with **WSL 2** |
| ROS 2 | Humble / Iron / Jazzy / Rolling |
| Python | 3.8 + |
| Display | Native X11/Wayland (Linux) or WSLg (Windows) |

> **All commands below must be run inside your Linux or WSL terminal**, not Windows PowerShell/CMD.

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

## Uninstallation

To completely remove **Ros2 Robot** from your system (including settings, the executable command, and the repository folder), simply run this one-line command:

```bash
curl -sSL https://raw.githubusercontent.com/saheraalreqeb/Ros2_Robot/main/uninstall.sh | bash
```

Alternatively, if you installed it manually via Git, you can just run `bash uninstall.sh` directly from inside the repository folder.

---

## Running the App

Open your Linux or WSL terminal and run:

```bash
ros2_robot
```

The GUI window will appear on your desktop (via X11/Wayland on native Linux, or WSLg on Windows).  
The terminal will show a blinking cursor while the app is running, this is normal.

To run in the background and get your terminal back:

```bash
ros2_robot &
```

---

## Running in Docker

By default, Docker containers are entirely "headless" and isolated from your host's monitor. If you want to run `ros2_robot` from inside a Docker container, you must launch the container with specific display sockets mapped to your host.

### For Windows/WSL2 Users (WSLg)
If you are running Docker inside WSL2, map the WSLg sockets into the container:

```bash
docker run -it \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v /mnt/wslg:/mnt/wslg \
    -e DISPLAY=$DISPLAY \
    -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
    -e XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
    -e PULSE_SERVER=$PULSE_SERVER \
    <your-image-name> /bin/bash
```

### For Windows Users (Docker Desktop)
If you are using Docker Desktop natively on Windows without WSLg:
1. Install an X11 server like **VcXsrv** on Windows and start it (ensure you check "Disable access control").
2. Run your container with the internal host display:
```bash
docker run -it -e DISPLAY=host.docker.internal:0.0 <your-image-name> /bin/bash
```

Once inside the container, run the `install.sh` script or launch `ros2_robot` directly.

---

## Features

| Tab | Description |
|---|---|
| **Workspace** | Open or initialize `colcon` workspaces. Build using an interactive colcon console with package selection, clean build toggle, and live output streaming. |
| **Packages** | Create ROS 2 packages (`ament_python` or `ament_cmake`) with one click. |
| **Nodes** | View all nodes in the workspace. Run or stop individual nodes with a button. |
| **Visualizer** | Live graph of publishers and subscribers across your running nodes. |
| **Launch Manager** | Visually build `.launch.py` files, then run them with live log output. |
| **Tools Hub** | Check and launch common ROS 2 tools (rqt, rviz2, gazebo, etc.). |
| **Topic Inspector** | Browse all active topics, view message types, and echo live data. |
| **Service Inspector** | Browse all active services and call them from the UI. |
| **Action Inspector** | Browse all active actions, view details, and send goals interactively with live progress feedback. |
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

If you receive a "no Qt platform plugin could be initialized" error (especially in slim Docker containers), install the missing system headless libraries:

```bash
sudo apt-get update
sudo apt-get install -y libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libgl1 libegl1 libglib2.0-0
```

> **Note for Docker users:** If the error persists after installing these libraries, it means your container cannot connect to the host's screen. Ensure you passed the `DISPLAY` flags when starting the container (see **Running in Docker** above).

### `ros2_robot` command not found after re-opening terminal

Re-run the install script:

```bash
bash ~/Ros2_Robot/install.sh
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

The app is installed in **editable mode**, so any changes you make to the source files are reflected immediately, no reinstall needed.

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
    ├── service_inspector.py # Service browser & caller
    ├── action_inspector.py  # Action browser & goal sender
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

