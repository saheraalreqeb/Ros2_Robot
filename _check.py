#!/usr/bin/env python3
import sys, os
os.environ.setdefault("DISPLAY", ":0")
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
sys.path.insert(0, "/mnt/c/Users/pc/Desktop/Ros2_Robot")
os.chdir("/mnt/c/Users/pc/Desktop/Ros2_Robot")

from gui.launch_manager import LaunchManagerPage
print("launch_manager OK")
from gui.parameter_manager import ParameterManagerPage
print("parameter_manager OK")
from gui.tools_hub import ToolsHubPage
print("tools_hub OK")
from gui.topic_inspector import TopicInspectorPage
print("topic_inspector OK")
from gui.visualizer import VisualizerPage
print("visualizer OK")
from gui.main_window import MainWindow
print("main_window OK")
print("ALL IMPORTS CLEAN")
