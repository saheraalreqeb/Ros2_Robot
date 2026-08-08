import os
import pytest
from core.workspace import ROS2Workspace

def test_workspace_init_paths(tmp_path):
    # Test path normalization and src folder handling
    ws1 = ROS2Workspace(str(tmp_path))
    assert ws1.path == os.path.abspath(tmp_path)
    assert ws1.src_path == os.path.join(os.path.abspath(tmp_path), 'src')

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    ws2 = ROS2Workspace(str(src_dir))
    assert ws2.path == os.path.abspath(tmp_path)
    assert ws2.src_path == os.path.abspath(src_dir)

def test_workspace_is_valid(tmp_path):
    ws = ROS2Workspace(str(tmp_path))
    assert not ws.is_valid()

    (tmp_path / "src").mkdir()
    assert ws.is_valid()

def test_workspace_get_packages_empty(tmp_path):
    ws = ROS2Workspace(str(tmp_path))
    assert ws.get_packages() == []

def test_workspace_parse_package_xml(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    pkg_dir = src_dir / "my_py_pkg"
    pkg_dir.mkdir()

    # Create mock package.xml for ament_python
    pkg_xml_content = """<?xml version="1.0"?>
    <package format="3">
      <name>my_py_pkg</name>
      <version>0.0.0</version>
      <description>Mock Python package</description>
      <maintainer email="test@test.com">test</maintainer>
      <license>Apache-2.0</license>
      <export>
        <build_type>ament_python</build_type>
      </export>
    </package>
    """
    (pkg_dir / "package.xml").write_text(pkg_xml_content)
    (pkg_dir / "setup.py").write_text("""
    from setuptools import find_packages, setup
    setup(
        name='my_py_pkg',
        entry_points={
            'console_scripts': [
                'my_node = my_py_pkg.my_node:main',
                'another_node = my_py_pkg.another_node:main'
            ],
        },
    )
    """)

    ws = ROS2Workspace(str(tmp_path))
    pkgs = ws.get_packages()
    assert len(pkgs) == 1
    assert pkgs[0]['name'] == 'my_py_pkg'
    assert pkgs[0]['build_type'] == 'ament_python'
    assert 'my_node' in pkgs[0]['nodes']
    assert 'another_node' in pkgs[0]['nodes']

def test_workspace_parse_cmake_package(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    pkg_dir = src_dir / "my_cpp_pkg"
    pkg_dir.mkdir()

    # Create mock package.xml for ament_cmake
    pkg_xml_content = """<?xml version="1.0"?>
    <package format="3">
      <name>my_cpp_pkg</name>
      <description>Mock C++ package</description>
      <license>MIT</license>
      <export>
        <build_type>ament_cmake</build_type>
      </export>
    </package>
    """
    (pkg_dir / "package.xml").write_text(pkg_xml_content)
    (pkg_dir / "CMakeLists.txt").write_text("""
    cmake_minimum_required(VERSION 3.8)
    project(my_cpp_pkg)
    add_executable(cpp_node src/cpp_node.cpp)
    add_executable(another_cpp src/another_cpp.cpp)
    ament_package()
    """)

    ws = ROS2Workspace(str(tmp_path))
    pkgs = ws.get_packages()
    assert len(pkgs) == 1
    assert pkgs[0]['name'] == 'my_cpp_pkg'
    assert pkgs[0]['build_type'] == 'ament_cmake'
    assert 'cpp_node' in pkgs[0]['nodes']
    assert 'another_cpp' in pkgs[0]['nodes']

def test_workspace_parse_package_fallback(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    pkg_dir = src_dir / "fallback_pkg"
    pkg_dir.mkdir()

    pkg_xml_content = """<?xml version="1.0"?>
    <package format="3">
      <name>fallback_pkg</name>
      <export>
        <build_type>ament_python</build_type>
      </export>
    </package>
    """
    (pkg_dir / "package.xml").write_text(pkg_xml_content)
    (pkg_dir / "setup.py").write_text("setup()")
    
    # Create module directory to trigger fallback
    module_dir = pkg_dir / "fallback_pkg"
    module_dir.mkdir()
    (module_dir / "__init__.py").touch()
    (module_dir / "scan_node.py").touch()
    (module_dir / "helper.py").touch()

    ws = ROS2Workspace(str(tmp_path))
    pkgs = ws.get_packages()
    assert len(pkgs) == 1
    # scan_node should be detected, __init__ skipped
    assert 'scan_node' in pkgs[0]['nodes']
    assert 'helper' in pkgs[0]['nodes']
    assert '__init__' not in pkgs[0]['nodes']


def test_init_workspace_dialog_get_data(qtbot):
    from gui.dialogs import InitWorkspaceDialog
    import os
    dlg = InitWorkspaceDialog()
    qtbot.addWidget(dlg)
    dlg.name_edit.setText("my_test_ws")
    home = os.path.expanduser("~")
    assert dlg.path_edit.text() == home
    data = dlg.get_data()
    assert data["name"] == "my_test_ws"
    assert data["location"] == home

