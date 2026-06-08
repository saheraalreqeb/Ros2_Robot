import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QListWidget, QTextEdit, QLabel, QTabWidget, QPushButton, QWidget
from PySide6.QtCore import Qt

def test_navigation_to_inspector(qtbot, main_window):
    nav_btn = main_window.findChild(QPushButton, "nav_btn_inspector")
    if nav_btn is not None:
        qtbot.mouseClick(nav_btn, Qt.LeftButton)
    
    tabs = main_window.findChild(QTabWidget, "tabs_inspector")
    assert tabs is not None
    assert tabs.isVisible()

def test_refresh_topics_success(qtbot, main_window, mock_ros2_cli):
    mock_ros2_cli.return_value.stdout = "/chatter\n/rosout"
    
    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_topics")
    if btn_refresh is not None:
        qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    
    list_topics = main_window.findChild(QListWidget, "list_topics")
    assert list_topics is not None
    assert list_topics.count() == 2
    assert list_topics.item(0).text() == "/chatter"
    assert list_topics.item(1).text() == "/rosout"

def test_refresh_services_success(qtbot, main_window, mock_ros2_cli):
    mock_ros2_cli.return_value.stdout = "/spawn\n/kill"
    
    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_services")
    if btn_refresh is not None:
        qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    
    list_services = main_window.findChild(QListWidget, "list_services")
    assert list_services is not None
    assert list_services.count() == 2
    assert list_services.item(0).text() == "/spawn"
    assert list_services.item(1).text() == "/kill"

def test_topic_info_display(qtbot, main_window, mock_ros2_cli):
    list_topics = main_window.findChild(QListWidget, "list_topics")
    if list_topics is not None:
        list_topics.addItem("/chatter")
        list_topics.setCurrentRow(0)
    
    mock_ros2_cli.return_value.stdout = "Type: std_msgs/msg/String\nPublisher count: 1"
    
    btn_topic_info = main_window.findChild(QPushButton, "btn_topic_info")
    if btn_topic_info is not None:
        qtbot.mouseClick(btn_topic_info, Qt.LeftButton)
    
    txt_topic_details = main_window.findChild(QTextEdit, "txt_topic_details")
    assert txt_topic_details is not None
    assert "std_msgs/msg/String" in txt_topic_details.toPlainText()

def test_service_info_display(qtbot, main_window, mock_ros2_cli):
    list_services = main_window.findChild(QListWidget, "list_services")
    if list_services is not None:
        list_services.addItem("/spawn")
        list_services.setCurrentRow(0)
    
    mock_ros2_cli.return_value.stdout = "turtlesim/srv/Spawn"
    
    btn_service_info = main_window.findChild(QPushButton, "btn_service_info")
    if btn_service_info is not None:
        qtbot.mouseClick(btn_service_info, Qt.LeftButton)
    
    txt_service_details = main_window.findChild(QTextEdit, "txt_service_details")
    assert txt_service_details is not None
    assert "turtlesim/srv/Spawn" in txt_service_details.toPlainText()

def test_topic_echo_start_stop(qtbot, main_window, mock_subprocess_popen):
    mock_process = MagicMock()
    mock_subprocess_popen.return_value = mock_process
    
    list_topics = main_window.findChild(QListWidget, "list_topics")
    if list_topics is not None:
        list_topics.addItem("/chatter")
        list_topics.setCurrentRow(0)
    
    btn_topic_echo = main_window.findChild(QPushButton, "btn_topic_echo")
    
    # Start echo
    if btn_topic_echo is not None:
        qtbot.mouseClick(btn_topic_echo, Qt.LeftButton)
    
    assert mock_subprocess_popen.called
    args, kwargs = mock_subprocess_popen.call_args
    assert args[0] == ['ros2', 'topic', 'echo', '/chatter']
    
    # Stop echo
    if btn_topic_echo is not None:
        qtbot.mouseClick(btn_topic_echo, Qt.LeftButton)
    assert mock_process.terminate.called

def test_refresh_topics_empty(qtbot, main_window, mock_ros2_cli):
    mock_ros2_cli.return_value.stdout = ""
    
    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_topics")
    if btn_refresh is not None:
        qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    
    list_topics = main_window.findChild(QListWidget, "list_topics")
    assert list_topics is not None
    assert list_topics.count() == 0
    
    lbl_status = main_window.findChild(QLabel, "lbl_inspector_status")
    assert lbl_status is not None
    assert "no topics found" in lbl_status.text().lower()

def test_refresh_topics_cli_error(qtbot, main_window, mock_ros2_cli):
    mock_ros2_cli.return_value.returncode = 1
    mock_ros2_cli.return_value.stderr = "CLI error"
    
    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_topics")
    if btn_refresh is not None:
        qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    
    list_topics = main_window.findChild(QListWidget, "list_topics")
    if list_topics is not None:
        assert list_topics.count() == 0
    
    lbl_status = main_window.findChild(QLabel, "lbl_inspector_status")
    txt_details = main_window.findChild(QTextEdit, "txt_topic_details")
    
    error_visible = False
    if lbl_status is not None and "cli error" in lbl_status.text().lower():
        error_visible = True
    if txt_details is not None and "cli error" in txt_details.toPlainText().lower():
        error_visible = True
        
    assert error_visible

def test_topic_actions_disabled_on_no_selection(qtbot, main_window):
    nav_btn = main_window.findChild(QPushButton, "nav_btn_inspector")
    if nav_btn is not None:
        qtbot.mouseClick(nav_btn, Qt.LeftButton)
    
    list_topics = main_window.findChild(QListWidget, "list_topics")
    if list_topics is not None:
        list_topics.clear()
    
    btn_topic_info = main_window.findChild(QPushButton, "btn_topic_info")
    btn_topic_echo = main_window.findChild(QPushButton, "btn_topic_echo")
    
    if btn_topic_info is not None:
        assert not btn_topic_info.isEnabled()
    if btn_topic_echo is not None:
        assert not btn_topic_echo.isEnabled()
    
    assert btn_topic_info is not None and btn_topic_echo is not None

def test_service_actions_disabled_on_no_selection(qtbot, main_window):
    nav_btn = main_window.findChild(QPushButton, "nav_btn_inspector")
    if nav_btn is not None:
        qtbot.mouseClick(nav_btn, Qt.LeftButton)
    
    list_services = main_window.findChild(QListWidget, "list_services")
    if list_services is not None:
        list_services.clear()
    
    btn_service_info = main_window.findChild(QPushButton, "btn_service_info")
    
    if btn_service_info is not None:
        assert not btn_service_info.isEnabled()
        
    assert btn_service_info is not None

def test_refresh_services_cli_error(qtbot, main_window, mock_ros2_cli):
    mock_ros2_cli.return_value.returncode = 1
    mock_ros2_cli.return_value.stderr = "Daemon failed"
    
    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_services")
    if btn_refresh is not None:
        qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    
    lbl_status = main_window.findChild(QLabel, "lbl_inspector_status")
    txt_details = main_window.findChild(QTextEdit, "txt_service_details")
    
    error_visible = False
    if lbl_status is not None and "daemon failed" in lbl_status.text().lower():
        error_visible = True
    if txt_details is not None and "daemon failed" in txt_details.toPlainText().lower():
        error_visible = True
        
    assert error_visible
