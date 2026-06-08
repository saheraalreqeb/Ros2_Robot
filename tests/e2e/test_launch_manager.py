import os
import pytest
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QLineEdit, QDialog, QMessageBox, QScrollArea, QComboBox
from PySide6.QtCore import Qt
from gui.launch_manager import LaunchManagerPage

def get_launch_page(main_window):
    """Helper to extract LaunchManagerPage from main_window."""
    for i in range(main_window.content_stack.count()):
        widget = main_window.content_stack.widget(i)
        if isinstance(widget, LaunchManagerPage):
            return widget
    return None

def test_empty_workspace_state(main_window, qtbot, tmp_path):
    """1. test_empty_workspace_state: Launch UI with no launch files; verify empty state message."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    assert launch_page is not None

    # Switch to the launch page so it becomes visible
    main_window.content_stack.setCurrentWidget(launch_page)

    # Simulate UI refresh if needed
    if hasattr(launch_page, 'refresh_file_list'):
        launch_page.refresh_file_list()

    # Process pending deleteLater() events
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.processEvents()

    # Look for an empty state label
    empty_label = launch_page.findChild(QLabel, "emptyStateLabel")
    if empty_label is not None:
        assert not empty_label.isHidden()
        assert "no launch files" in empty_label.text().lower()
    else:
        pytest.fail("Feature not implemented: emptyStateLabel not found")

def test_list_existing_launch_files(main_window, qtbot, tmp_path):
    """2. test_list_existing_launch_files: Mock workspace with multiple .launch.py files; verify UI cards."""
    # Create mock launch files
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "my_pkg" / "launch"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "test1.launch.py").write_text("# test1")
    (pkg_dir / "test2.launch.py").write_text("# test2")

    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    if hasattr(launch_page, 'refresh_file_list'):
        launch_page.refresh_file_list()

    file_list = launch_page.findChild(QListWidget, "launchFileList")
    if file_list is not None:
        assert file_list.count() >= 2
        items = [file_list.item(i).text() for i in range(file_list.count())]
        assert any("test1.launch.py" in item for item in items)
        assert any("test2.launch.py" in item for item in items)
    else:
        pytest.fail("Feature not implemented: launchFileList not found")

def test_visual_builder_single_node(main_window, qtbot, tmp_path, mocker):
    """3. test_visual_builder_single_node: Add a single node, click save, verify open().write called."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    if not btn_new:
        pytest.fail("Feature not implemented: btnNewLaunch not found")
        
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    
    btn_add_node = launch_page.findChild(QPushButton, "btnAddNode")
    assert btn_add_node is not None, "btnAddNode not found"
    qtbot.mouseClick(btn_add_node, Qt.LeftButton)
    
    input_filename = launch_page.findChild(QLineEdit, "inputFilename")
    assert input_filename is not None, "inputFilename not found"
    input_filename.setText("my_single.launch.py")
    
    mock_open = mocker.patch("builtins.open", mocker.mock_open())
    
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    assert btn_save is not None, "btnSaveLaunch not found"
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    mock_open.assert_called_once()
    handle = mock_open()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "LaunchDescription" in written_content
    assert "Node" in written_content

def test_visual_builder_multiple_nodes_and_delays(main_window, qtbot, tmp_path, mocker):
    """4. test_visual_builder_multiple_nodes_and_delays: Add nodes/delays, verify TimerAction."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    if not btn_new:
        pytest.fail("Feature not implemented: btnNewLaunch not found")
        
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    
    btn_add_node = launch_page.findChild(QPushButton, "btnAddNode")
    btn_add_delay = launch_page.findChild(QPushButton, "btnAddDelay")
    
    assert btn_add_node is not None and btn_add_delay is not None
    
    qtbot.mouseClick(btn_add_node, Qt.LeftButton)
    qtbot.mouseClick(btn_add_delay, Qt.LeftButton)
    qtbot.mouseClick(btn_add_node, Qt.LeftButton)
    
    mock_open = mocker.patch("builtins.open", mocker.mock_open())
    
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    handle = mock_open()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "TimerAction" in written_content
    assert written_content.count("Node") >= 2

def test_visual_builder_save_validity(main_window, qtbot, tmp_path, mocker):
    """5. test_visual_builder_save_validity: Save valid launch config, verify file list is refreshed."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    mocker.patch.object(launch_page, 'refresh_file_list', create=True)
    mocker.patch("builtins.open", mocker.mock_open())
    
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    if not btn_new:
        pytest.fail("Feature not implemented")
        
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    
    input_filename = launch_page.findChild(QLineEdit, "inputFilename")
    input_filename.setText("valid.launch.py")
    
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    launch_page.refresh_file_list.assert_called()

def test_validation_empty_fields(main_window, qtbot, tmp_path, mocker):
    """6. test_validation_empty_fields: Attempt save without mandatory fields, verify warning dialog."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    mock_warning = mocker.patch.object(QMessageBox, 'warning')
    
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    if not btn_new:
        pytest.fail("Feature not implemented")
        
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    
    input_filename = launch_page.findChild(QLineEdit, "inputFilename")
    input_filename.setText("") # Empty filename
    
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    mock_warning.assert_called_once()

def test_corrupted_launch_file_handling(main_window, qtbot, tmp_path):
    """7. test_corrupted_launch_file_handling: Mock unreadable file, verify UI doesn't crash."""
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "my_pkg" / "launch"
    pkg_dir.mkdir(parents=True)
    corrupted_file = pkg_dir / "corrupted.launch.py"
    
    # Write invalid Python syntax
    corrupted_file.write_text("def invalid_syntax(;;)")
    
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    try:
        if hasattr(launch_page, 'refresh_file_list'):
            launch_page.refresh_file_list()
    except Exception as e:
        pytest.fail(f"Application crashed on corrupted file: {e}")

def test_mock_permission_denied_save(main_window, qtbot, tmp_path, mocker):
    """8. test_mock_permission_denied_save: Mock PermissionError on save, verify error dialog."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    mock_open = mocker.patch("builtins.open", side_effect=PermissionError("Mocked Permission Denied"))
    mock_critical = mocker.patch.object(QMessageBox, 'critical')
    
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    if not btn_new:
        pytest.fail("Feature not implemented")
        
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    mock_critical.assert_called_once()
    assert "Permission" in mock_critical.call_args[0][2]

def test_duplicate_launch_file_name(main_window, qtbot, tmp_path, mocker):
    """9. test_duplicate_launch_file_name: Save with existing name, verify overwrite prompt or reject."""
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "my_pkg" / "launch"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "existing.launch.py").write_text("# exists")
    
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    mock_question = mocker.patch.object(QMessageBox, 'question', return_value=QMessageBox.No)
    mock_warning = mocker.patch.object(QMessageBox, 'warning')
    
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    if not btn_new:
        pytest.fail("Feature not implemented")
        
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    
    input_filename = launch_page.findChild(QLineEdit, "inputFilename")
    input_filename.setText("existing.launch.py")
    
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    # Either asks for overwrite or warns about duplicate
    assert mock_question.called or mock_warning.called

def test_boundary_large_number_of_files(main_window, qtbot, tmp_path):
    """10. test_boundary_large_number_of_files: Mock 100+ files, verify UI layout."""
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "my_pkg" / "launch"
    pkg_dir.mkdir(parents=True)
    
    for i in range(150):
        (pkg_dir / f"test_{i}.launch.py").write_text(f"# test {i}")
        
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    if hasattr(launch_page, 'refresh_file_list'):
        launch_page.refresh_file_list()
        
    file_list = launch_page.findChild(QListWidget, "launchFileList")
    if file_list is not None:
        assert file_list.count() == 150
        
    # Check if a scroll area exists in the page
    scroll_area = launch_page.findChild(QScrollArea)
    if scroll_area is None and file_list is None:
         pytest.fail("Feature not implemented: Missing ScrollArea or ListWidget for large file list")

def test_visual_builder_scripts_and_includes(main_window, qtbot, tmp_path, mocker):
    """11. test_visual_builder_scripts_and_includes: Add script and nested launch blocks, verify generation."""
    main_window.current_workspace_path = str(tmp_path)
    launch_page = get_launch_page(main_window)
    
    # Open builder dialog
    btn_new = launch_page.findChild(QPushButton, "btnNewLaunch")
    assert btn_new is not None
    qtbot.mouseClick(btn_new, Qt.LeftButton)
    
    # Enter script command
    input_cmd = launch_page.findChild(QLineEdit, "inputScriptCommand")
    assert input_cmd is not None
    input_cmd.setText("echo 'ROS 2 is active!'")
    
    btn_add_script = launch_page.findChild(QPushButton, "btnAddScript")
    assert btn_add_script is not None
    qtbot.mouseClick(btn_add_script, Qt.LeftButton)
    
    # Enter launch file to include
    input_file = launch_page.findChild(QComboBox, "cmbIncludeFile")
    assert input_file is not None
    input_file.setEditText("robot.launch.py")
    
    btn_add_include = launch_page.findChild(QPushButton, "btnAddInclude")
    assert btn_add_include is not None
    qtbot.mouseClick(btn_add_include, Qt.LeftButton)
    
    # Set filename
    input_filename = launch_page.findChild(QLineEdit, "inputFilename")
    assert input_filename is not None
    input_filename.setText("script_include.launch.py")
    
    mock_open = mocker.patch("builtins.open", mocker.mock_open())
    
    btn_save = launch_page.findChild(QPushButton, "btnSaveLaunch")
    assert btn_save is not None
    qtbot.mouseClick(btn_save, Qt.LeftButton)
    
    mock_open.assert_called_once()
    handle = mock_open()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "ExecuteProcess" in written_content
    assert "IncludeLaunchDescription" in written_content
    assert "FindPackageShare" in written_content
    assert "PythonLaunchDescriptionSource" in written_content
    assert "echo \\'ROS 2 is active!\\'" in written_content

