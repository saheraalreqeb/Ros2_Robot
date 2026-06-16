"""
core/ide_launcher.py
====================
Provides cross-platform (Native Linux and WSL) IDE detection and launching capabilities.
"""

import os
import shutil
import subprocess
from typing import List, Dict

# Known IDE executables and their human-readable names
KNOWN_IDES = {
    "code": "VSCode",
    "cursor": "Cursor",
    "pycharm-community": "PyCharm CE",
    "pycharm-professional": "PyCharm Pro",
    "clion": "CLion",
    "gedit": "GEdit",
}

def get_available_ides() -> List[Dict[str, str]]:
    """
    Returns a list of dictionaries with 'cmd' and 'name' for each installed IDE.
    e.g., [{"cmd": "code", "name": "VSCode"}, ...]
    """
    available = []
    
    # Check if we are running in a WSL context.
    # The application itself might be running on Windows, wrapping WSL.
    # If the app runs natively on Windows but manages a WSL workspace, 
    # we can just use `shutil.which` because commands like `code` are usually in the Windows PATH
    # and automatically work across the WSL boundary via `code .`.
    
    for cmd, name in KNOWN_IDES.items():
        if shutil.which(cmd):
            available.append({"cmd": cmd, "name": name})
            continue
            
        # Fallback for Windows/WSL: check if `wsl which <cmd>` works
        try:
            # We don't want a blocking timeout, just a quick check
            res = subprocess.run(["wsl", "which", cmd], capture_output=True, text=True, timeout=1)
            if res.returncode == 0 and res.stdout.strip():
                available.append({"cmd": cmd, "name": name})
        except Exception:
            pass
            
    return available

def launch_in_ide(ide_cmd: str, target_path: str) -> bool:
    """
    Launch the specified IDE and open the target_path.
    Returns True if successfully launched.
    """
    if not ide_cmd or not target_path:
        return False
        
    try:
        # If running on Windows natively, `shutil.which` will find the Windows .cmd/.exe.
        # VSCode's Windows binary can accept WSL paths (e.g. \\wsl$\Ubuntu\...)
        # OR if we pass the wsl path to it from WSL `wsl bash -c "code <path>"` it handles it.
        
        # If the path looks like a Linux path (e.g., /home/...) and we are on Windows, 
        # we can route the command through WSL to be safe.
        is_windows = os.name == 'nt'
        is_linux_path = target_path.startswith('/')
        
        if is_windows and is_linux_path:
            # Execute inside WSL
            subprocess.Popen(["wsl", "bash", "-c", f"{ide_cmd} '{target_path}'"])
        else:
            # Native Linux execution (or Windows native path)
            subprocess.Popen([ide_cmd, target_path])
            
        return True
    except Exception as e:
        print(f"Failed to launch IDE: {e}")
        return False
