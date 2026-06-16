# ROS2 Robot Roadmap & Future Tasks

## V1.1 / Future Optimizations

### 1. Centralized ROS2 State Cache (`RosStateManager`)
Currently, different UI components (Node Monitor, Topic Inspector, etc.) independently spawn `subprocess` calls like `ros2 node list` and `ros2 topic list`.
- **Goal:** Create a centralized `RosStateManager` singleton or background service.
- **Implementation:** 
  - Poll the ROS2 daemon on a fixed loop (e.g., every 2 seconds).
  - Cache the results (nodes, topics, services, parameters).
  - Use Qt Signals to broadcast the updated state to any active UI tabs.
- **Benefit:** Drastically reduces CPU overhead and overlapping subprocess calls, ensuring the UI remains highly responsive even on lightweight single-board computers (Raspberry Pi, etc.).

### 2. Tools Hub Caching
- **Goal:** Cache dependency/installation checks (`shutil.which` and `dpkg`).
- **Implementation:** Check if dependencies (e.g., `PlotJuggler`, `rqt_graph`) are installed only once on startup, rather than polling dynamically every time the tab is refreshed. Update the cache specifically only when the user clicks "Install" from within the app.
- **Benefit:** Eliminates unnecessary file-system and `dpkg` checks.

### 3. URDF / Mesh Memory Caching (Optional/Long-Term)
- **Goal:** Improve URDF viewer load times for heavy mesh files.
- **Implementation:** Maintain an LRU (Least Recently Used) cache for parsed `.stl` and `.dae` files in memory.
- **Benefit:** If the user repeatedly toggles the same robot, the viewer won't have to re-read the binary geometry data from the disk every time.
