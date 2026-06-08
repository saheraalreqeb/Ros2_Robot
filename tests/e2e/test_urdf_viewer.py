import os
import pytest
from PySide6.QtWidgets import QLabel, QListWidget, QTreeWidget, QGraphicsView, QPushButton
from PySide6.QtCore import Qt, QCoreApplication
from gui.urdf_viewer import URDFViewerPage

def get_urdf_page(main_window):
    """Helper to extract URDFViewerPage from main_window."""
    for i in range(main_window.content_stack.count()):
        widget = main_window.content_stack.widget(i)
        if isinstance(widget, URDFViewerPage):
            return widget
    return None

def test_empty_workspace_state(main_window, qtbot, tmp_path):
    """1. test_empty_workspace_state: Launch UI with no URDF files; verify empty state message."""
    main_window.current_workspace_path = str(tmp_path)
    urdf_page = get_urdf_page(main_window)
    assert urdf_page is not None

    # Switch to the URDF page
    main_window.content_stack.setCurrentWidget(urdf_page)

    if hasattr(urdf_page, 'scan_workspace'):
        urdf_page.scan_workspace()

    QCoreApplication.processEvents()

    # Verify active file label shows no files found
    active_lbl = urdf_page.lbl_active_file
    assert "no urdf/xacro files found" in active_lbl.text().lower()

def test_list_existing_urdf_files(main_window, qtbot, tmp_path):
    """2. test_list_existing_urdf_files: Mock workspace with multiple URDF/Xacro files; verify file list."""
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "my_robot_pkg"
    pkg_dir.mkdir(parents=True)
    
    (pkg_dir / "robot.urdf").write_text("<robot name='test'></robot>")
    (pkg_dir / "robot_macro.xacro").write_text("<robot name='test_xacro'></robot>")

    main_window.current_workspace_path = str(tmp_path)
    urdf_page = get_urdf_page(main_window)
    assert urdf_page is not None

    # Switch to the URDF page
    main_window.content_stack.setCurrentWidget(urdf_page)

    if hasattr(urdf_page, 'scan_workspace'):
        urdf_page.scan_workspace()

    QCoreApplication.processEvents()

    file_list = urdf_page.findChild(QListWidget, "list_urdf_files")
    assert file_list is not None
    assert file_list.count() >= 2

    items = [file_list.item(i).text() for i in range(file_list.count())]
    assert any("robot.urdf" in item for item in items)
    assert any("robot_macro.xacro" in item for item in items)

def test_parse_and_inspect_urdf(main_window, qtbot, tmp_path):
    """3. test_parse_and_inspect_urdf: Inspect a valid URDF; check hierarchy tree and graphics scene."""
    urdf_content = """<?xml version="1.0"?>
<robot name="simple_car">
  <link name="base_link">
    <visual><geometry><box size="0.6 0.4 0.2"/></geometry></visual>
  </link>
  <link name="wheel_left">
    <visual><geometry><cylinder length="0.05" radius="0.1"/></geometry></visual>
  </link>
  <joint name="base_to_wheel_left" type="continuous">
    <parent link="base_link"/>
    <child link="wheel_left"/>
  </joint>
</robot>
"""
    src_dir = tmp_path / "src"
    pkg_dir = src_dir / "car_pkg"
    pkg_dir.mkdir(parents=True)
    urdf_file = pkg_dir / "car.urdf"
    urdf_file.write_text(urdf_content)

    main_window.current_workspace_path = str(tmp_path)
    urdf_page = get_urdf_page(main_window)
    assert urdf_page is not None

    # Switch to the URDF page
    main_window.content_stack.setCurrentWidget(urdf_page)

    if hasattr(urdf_page, 'scan_workspace'):
        urdf_page.scan_workspace()

    QCoreApplication.processEvents()

    # Check file list and select the file
    file_list = urdf_page.findChild(QListWidget, "list_urdf_files")
    assert file_list is not None
    assert file_list.count() == 1
    file_list.setCurrentRow(0)

    QCoreApplication.processEvents()

    # Verify XML view
    xml_view = urdf_page.txt_urdf_xml
    assert "simple_car" in xml_view.toPlainText()

    # Verify Hierarchy Tree items
    tree = urdf_page.findChild(QTreeWidget, "tree_urdf_hierarchy")
    assert tree is not None
    assert tree.topLevelItemCount() == 1
    
    root_item = tree.topLevelItem(0)
    assert "Robot Root: base_link" in root_item.text(0)
    
    assert root_item.childCount() == 1
    joint_item = root_item.child(0)
    assert "Joint: base_to_wheel_left" in joint_item.text(0)
    
    assert joint_item.childCount() == 1
    child_link_item = joint_item.child(0)
    assert "Link: wheel_left" in child_link_item.text(0)

    # Verify Kinematic Diagram scene items
    scene = urdf_page.scene_urdf
    # We expect Base link node, Wheel left node, joint line, and joint text label
    assert len(scene.items()) >= 4
