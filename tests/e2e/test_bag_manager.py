import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from unittest.mock import MagicMock
import os

def test_record_all_topics(main_window, qtbot, mock_subprocess_popen):
    bag_page = main_window.content_stack.widget(9)
    qtbot.mouseClick(bag_page.btn_record_all, Qt.LeftButton)
    
    mock_subprocess_popen.assert_called_once()
    args = mock_subprocess_popen.call_args[0][0]
    assert 'ros2' in args
    assert 'bag' in args
    assert 'record' in args
    assert '-a' in args

def test_record_selected_topics(main_window, qtbot, mock_subprocess_popen):
    bag_page = main_window.content_stack.widget(9)
    bag_page.list_topics.addItem("/topic1")
    bag_page.list_topics.addItem("/topic2")
    bag_page.list_topics.item(0).setSelected(True)
    bag_page.list_topics.item(1).setSelected(True)
    
    qtbot.mouseClick(bag_page.btn_record_selected, Qt.LeftButton)
    
    mock_subprocess_popen.assert_called_once()
    args = mock_subprocess_popen.call_args[0][0]
    assert 'ros2' in args
    assert 'bag' in args
    assert 'record' in args
    assert '/topic1' in args
    assert '/topic2' in args

def test_stop_recording(main_window, qtbot, mock_subprocess_popen):
    bag_page = main_window.content_stack.widget(9)
    
    qtbot.mouseClick(bag_page.btn_record_all, Qt.LeftButton)
    mock_process = mock_subprocess_popen.return_value
    
    qtbot.mouseClick(bag_page.btn_stop, Qt.LeftButton)
    mock_process.terminate.assert_called_once()

def test_play_existing_bag_file(main_window, qtbot, mock_subprocess_popen, mocker):
    bag_page = main_window.content_stack.widget(9)
    bag_page.input_bag_path.setText("/path/to/bag")
    
    mocker.patch('os.path.exists', return_value=True)
    
    qtbot.mouseClick(bag_page.btn_play, Qt.LeftButton)
    
    mock_subprocess_popen.assert_called_once()
    args = mock_subprocess_popen.call_args[0][0]
    assert 'ros2' in args
    assert 'bag' in args
    assert 'play' in args
    assert '/path/to/bag' in args

def test_view_bag_info(main_window, qtbot, mock_ros2_cli, mocker):
    bag_page = main_window.content_stack.widget(9)
    bag_page.input_bag_path.setText("/path/to/bag")
    
    mocker.patch('os.path.exists', return_value=True)
    mock_ros2_cli.return_value.returncode = 0
    mock_ros2_cli.return_value.stdout = "Bag Info Details"
    
    mock_info = mocker.patch("PySide6.QtWidgets.QMessageBox.information")
    
    qtbot.mouseClick(bag_page.btn_info, Qt.LeftButton)
    
    mock_ros2_cli.assert_called_once()
    assert mock_info.called
    assert "Bag Info Details" in mock_info.call_args[0][2]

def test_record_with_no_topics_selected(main_window, qtbot, mock_subprocess_popen, mocker):
    bag_page = main_window.content_stack.widget(9)
    
    mock_warning = mocker.patch("PySide6.QtWidgets.QMessageBox.warning")
    
    qtbot.mouseClick(bag_page.btn_record_selected, Qt.LeftButton)
    
    mock_subprocess_popen.assert_not_called()
    assert mock_warning.called

def test_play_non_existent_file(main_window, qtbot, mock_subprocess_popen, mocker):
    bag_page = main_window.content_stack.widget(9)
    bag_page.input_bag_path.setText("/invalid/path")
    
    mocker.patch('os.path.exists', return_value=False)
    mock_warning = mocker.patch("PySide6.QtWidgets.QMessageBox.warning")
    
    qtbot.mouseClick(bag_page.btn_play, Qt.LeftButton)
    
    mock_subprocess_popen.assert_not_called()
    assert mock_warning.called

def test_stop_button_disabled_when_idle(main_window, qtbot):
    bag_page = main_window.content_stack.widget(9)
    assert not bag_page.btn_stop.isEnabled()

def test_bag_info_error(main_window, qtbot, mock_ros2_cli, mocker):
    bag_page = main_window.content_stack.widget(9)
    bag_page.input_bag_path.setText("/path/to/bag")
    
    mocker.patch('os.path.exists', return_value=True)
    mock_ros2_cli.return_value.returncode = 1
    mock_ros2_cli.return_value.stderr = "Error reading bag"
    
    mock_critical = mocker.patch("PySide6.QtWidgets.QMessageBox.critical")
    
    qtbot.mouseClick(bag_page.btn_info, Qt.LeftButton)
    
    mock_ros2_cli.assert_called_once()
    assert mock_critical.called

def test_process_launch_exception(main_window, qtbot, mock_subprocess_popen, mocker):
    bag_page = main_window.content_stack.widget(9)
    
    mock_subprocess_popen.side_effect = FileNotFoundError("ROS2 not found")
    mock_critical = mocker.patch("PySide6.QtWidgets.QMessageBox.critical")
    
    qtbot.mouseClick(bag_page.btn_record_all, Qt.LeftButton)
    
    assert mock_critical.called
    assert "ROS2 not found" in mock_critical.call_args[0][2]
