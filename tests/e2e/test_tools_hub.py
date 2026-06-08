import pytest
import shutil
import subprocess
from unittest.mock import MagicMock
from PySide6.QtWidgets import QPushButton, QLabel, QMessageBox
from PySide6.QtCore import Qt

def find_button_by_text(parent, text):
    for btn in parent.findChildren(QPushButton):
        if text in btn.text():
            return btn
    return None

def find_label_containing_text(parent, text):
    for lbl in parent.findChildren(QLabel):
        if text in lbl.text():
            return lbl
    return None

# Tier 1: Feature Coverage (Happy Paths)

def test_tools_hub_navigation(main_window, qtbot):
    btn_tools = main_window.btn_tools
    qtbot.mouseClick(btn_tools, Qt.MouseButton.LeftButton)
    assert main_window.content_stack.currentIndex() == 6

def test_tools_hub_lists_required_tools(main_window, qtbot):
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    assert find_label_containing_text(page, "RViz") is not None, "RViz should be listed"
    assert find_label_containing_text(page, "Gazebo") is not None, "Gazebo should be listed"
    assert find_label_containing_text(page, "rqt") is not None, "rqt should be listed"

def test_tools_hub_launch_installed_tool(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value="/usr/bin/rviz2")
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch RViz")
    assert btn is not None, "Launch RViz button not found"
    
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    mock_subprocess_popen.assert_called_once()
    args = mock_subprocess_popen.call_args[0][0]
    assert "rviz2" in args or (isinstance(args, str) and "rviz2" in args) or (isinstance(args, list) and any("rviz2" in arg for arg in args))

def test_tools_hub_warn_uninstalled_tool(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value=None)
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch Gazebo")
    assert btn is not None, "Launch Gazebo button not found"
    
    mock_warning = mocker.patch.object(QMessageBox, 'warning')
    
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    mock_subprocess_popen.assert_not_called()
    mock_warning.assert_called_once()

def test_tools_hub_launch_multiple_tools(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value="/usr/bin/tool")
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn_rviz = find_button_by_text(page, "Launch RViz")
    btn_rqt = find_button_by_text(page, "Launch rqt")
    
    assert btn_rviz is not None
    assert btn_rqt is not None
    
    qtbot.mouseClick(btn_rviz, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(btn_rqt, Qt.MouseButton.LeftButton)
    
    assert mock_subprocess_popen.call_count == 2

# Tier 2: Boundary/Corner Cases

def test_tools_hub_subprocess_error(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value="/usr/bin/tool")
    mock_subprocess_popen.side_effect = OSError("Failed to start process")
    
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch RViz")
    assert btn is not None
    
    mock_critical = mocker.patch.object(QMessageBox, 'critical')
    
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    mock_critical.assert_called_once()

def test_tools_hub_tool_uninstalled_while_running(main_window, qtbot, mocker, mock_subprocess_popen):
    mock_which = mocker.patch("shutil.which", return_value="/usr/bin/tool")
    
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch RViz")
    assert btn is not None
    
    # Dynamically change to False before clicking launch
    mock_which.return_value = None
    
    mock_warning = mocker.patch.object(QMessageBox, 'warning')
    
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    mock_subprocess_popen.assert_not_called()
    mock_warning.assert_called_once()

def test_tools_hub_rapid_clicks(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value="/usr/bin/tool")
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch RViz")
    assert btn is not None
    
    for _ in range(3):
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    assert mock_subprocess_popen.call_count >= 1

def test_tools_hub_no_tools_installed(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value=None)
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch RViz")
    assert btn is not None
    
    mock_warning = mocker.patch.object(QMessageBox, 'warning')
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    mock_subprocess_popen.assert_not_called()
    mock_warning.assert_called_once()

def test_tools_hub_close_app_kills_tools(main_window, qtbot, mocker, mock_subprocess_popen):
    mocker.patch("shutil.which", return_value="/usr/bin/tool")
    main_window.btn_tools.click()
    page = main_window.content_stack.widget(6)
    
    btn = find_button_by_text(page, "Launch RViz")
    assert btn is not None
    
    mock_process = MagicMock()
    mock_subprocess_popen.return_value = mock_process
    
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    
    main_window.close()
    
    assert mock_process.terminate.called or mock_process.kill.called
