import os
import pytest
from PySide6.QtWidgets import QPushButton, QFrame, QLabel
from PySide6.QtCore import Qt, QCoreApplication
from unittest.mock import MagicMock

def test_nodes_page_kill_all(main_window, qtbot, tmp_path, mocker):
    # Mock workspace package and node structure
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "my_test_pkg"
    pkg_dir.mkdir(parents=True)
    
    mocker.patch("core.workspace.ROS2Workspace.get_packages", return_value=[
        {
            "name": "my_test_pkg",
            "path": str(pkg_dir),
            "nodes": ["talker_node"],
            "build_type": "ament_python"
        }
    ])

    main_window.current_workspace_path = str(tmp_path)
    
    # Navigate to nodes tab (index 2) and refresh list
    main_window.content_stack.setCurrentIndex(2)
    main_window._refresh_nodes_list()
    QCoreApplication.processEvents()

    # Verify node card is added
    assert len(main_window.active_node_cards) == 1
    card = main_window.active_node_cards[0]
    assert card.node_name == "talker_node"

    # Find the run button inside the card
    btn_run = card.findChild(QPushButton)
    assert btn_run is not None
    assert "Run" in btn_run.text()

    # Mock subprocess.Popen
    import io
    mock_popen = mocker.patch("subprocess.Popen")
    mock_proc = MagicMock()
    mock_proc.stdout = io.StringIO("")
    mock_popen.return_value = mock_proc

    # Mock psutil process iteration to simulate node NOT running initially
    mock_psutil_proc = MagicMock()
    mock_psutil_proc.info = {"cmdline": ["ros2 run my_test_pkg talker_node"]}
    mocker.patch("psutil.process_iter", return_value=[])

    # Click run
    qtbot.mouseClick(btn_run, Qt.LeftButton)
    QCoreApplication.processEvents()

    # Verify process started and tracked in running_processes
    assert "my_test_pkg:talker_node" in main_window.running_processes

    # Now mock psutil process iteration to return our running process
    mocker.patch("psutil.process_iter", return_value=[mock_psutil_proc])

    # Verify Kill All button is present
    btn_kill_all = main_window.findChild(QPushButton, "btnKillAllNodes")
    assert btn_kill_all is not None

    # Click Kill All Nodes
    qtbot.mouseClick(btn_kill_all, Qt.LeftButton)
    QCoreApplication.processEvents()

    # Verify it was terminated
    assert mock_psutil_proc.terminate.called
    assert "my_test_pkg:talker_node" not in main_window.running_processes
