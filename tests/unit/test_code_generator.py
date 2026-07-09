import os
import pytest
from core.code_generator import CodeGenerator

def test_generate_python_node(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_python_node"
    
    generated_file = CodeGenerator.generate_python_node(str(package_dir), package_name, node_name)
    
    assert os.path.exists(generated_file)
    assert generated_file.endswith("my_python_node.py")
    
    with open(generated_file, "r") as f:
        content = f.read()
    assert "class My_python_nodeNode(Node):" in content
    assert "def main(args=None):" in content
    assert "super().__init__('my_python_node')" in content
    
    # Check that __init__.py was created
    assert os.path.exists(os.path.join(package_dir, package_name, "__init__.py"))

def test_generate_cpp_node(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_node"
    
    generated_file = CodeGenerator.generate_cpp_node(str(package_dir), package_name, node_name)
    
    assert os.path.exists(generated_file)
    assert generated_file.endswith("my_cpp_node.cpp")
    
    with open(generated_file, "r") as f:
        content = f.read()
    assert "class My_cpp_nodeNode : public rclcpp::Node" in content
    assert "RCLCPP_INFO(this->get_logger(), \"Hello World from my_cpp_node\");" in content

def test_modify_setup_py(tmp_path):
    setup_py = tmp_path / "setup.py"
    setup_py.write_text("""
    setup(
        name='test_pkg',
        entry_points={
            'console_scripts': [
            ],
        },
    )
    """)
    
    CodeGenerator.modify_setup_py(str(setup_py), "test_pkg", "my_node")
    
    with open(setup_py, "r") as f:
        content = f.read()
    assert "my_node = test_pkg.my_node:main" in content

    # Add second node
    CodeGenerator.modify_setup_py(str(setup_py), "test_pkg", "another_node")
    with open(setup_py, "r") as f:
        content = f.read()
    assert "my_node = test_pkg.my_node:main" in content
    assert "another_node = test_pkg.another_node:main" in content

    # Add duplicate node (should not change anything)
    original_content = content
    CodeGenerator.modify_setup_py(str(setup_py), "test_pkg", "my_node")
    with open(setup_py, "r") as f:
        content_after = f.read()
    assert content_after == original_content

def test_modify_setup_py_no_file():
    with pytest.raises(FileNotFoundError):
        CodeGenerator.modify_setup_py("invalid/setup.py", "pkg", "node")

def test_modify_setup_py_malformed(tmp_path):
    setup_py = tmp_path / "setup.py"
    setup_py.write_text("print('hello')")
    with pytest.raises(ValueError):
        CodeGenerator.modify_setup_py(str(setup_py), "pkg", "node")

def test_modify_cmakelists(tmp_path):
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text("""
    cmake_minimum_required(VERSION 3.8)
    project(test_pkg)
    ament_package()
    """)
    
    CodeGenerator.modify_cmakelists(str(cmakelists), "my_cpp_node")
    
    with open(cmakelists, "r") as f:
        content = f.read()
    assert "add_executable(my_cpp_node src/my_cpp_node.cpp)" in content
    assert "ament_target_dependencies(my_cpp_node rclcpp)" in content
    assert "install(TARGETS my_cpp_node" in content

    # Duplicate check
    original_content = content
    CodeGenerator.modify_cmakelists(str(cmakelists), "my_cpp_node")
    with open(cmakelists, "r") as f:
        content_after = f.read()
    assert content_after == original_content

def test_modify_cmakelists_no_file():
    with pytest.raises(FileNotFoundError):
        CodeGenerator.modify_cmakelists("invalid/CMakeLists.txt", "node")

def test_modify_cmakelists_malformed(tmp_path):
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text("cmake_minimum_required(VERSION 3.8)")
    with pytest.raises(ValueError):
        CodeGenerator.modify_cmakelists(str(cmakelists), "node")

# ── Lifecycle node tests ────────────────────────────────────────────

def test_generate_python_lifecycle_node_creates_file(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_lifecycle_node"

    generated_file = CodeGenerator.generate_python_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    assert os.path.exists(generated_file)
    assert generated_file.endswith("my_lifecycle_node.py")

    # __init__.py should also be created
    assert os.path.exists(os.path.join(package_dir, package_name, "__init__.py"))


def test_generate_python_lifecycle_node_imports(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_lifecycle_node"

    generated_file = CodeGenerator.generate_python_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    assert "from rclpy.lifecycle import LifecycleNode" in content
    assert "from rclpy.lifecycle import TransitionCallbackReturn" in content


def test_generate_python_lifecycle_node_class_structure(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_lifecycle_node"

    generated_file = CodeGenerator.generate_python_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    assert "class My_lifecycle_nodeNode(LifecycleNode):" in content
    assert "super().__init__('my_lifecycle_node')" in content
    assert "def main(args=None):" in content


def test_generate_python_lifecycle_node_callbacks_present(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_lifecycle_node"

    generated_file = CodeGenerator.generate_python_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    for callback in [
        "on_configure",
        "on_activate",
        "on_deactivate",
        "on_cleanup",
        "on_shutdown",
        "on_error"
    ]:
        assert f"def {callback}(self, state):" in content, f"Missing callback: {callback}"


def test_generate_python_lifecycle_node_callbacks_return_success(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_lifecycle_node"

    generated_file = CodeGenerator.generate_python_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    # All callbacks except on_error should have a non-error return
    assert content.count("return TransitionCallbackReturn.SUCCESS") == 6


def test_generate_python_node_unchanged(tmp_path):
    """Regression test: normal node generation output is unchanged."""
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_python_node"

    generated_file = CodeGenerator.generate_python_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    # Should NOT contain lifecycle imports or classes
    assert "LifecycleNode" not in content
    assert "TransitionCallbackReturn" not in content
    assert "on_configure" not in content
    assert "from rclpy.node import Node" in content
    assert "class My_python_nodeNode(Node):" in content

# ── C++ lifecycle node tests ─────────────────────────────────────────

def test_generate_cpp_lifecycle_node_creates_file(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_lc_node"

    generated_file = CodeGenerator.generate_cpp_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    assert os.path.exists(generated_file)
    assert generated_file.endswith("my_cpp_lc_node.cpp")


def test_generate_cpp_lifecycle_node_includes_headers(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_lc_node"

    generated_file = CodeGenerator.generate_cpp_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    assert '#include "rclcpp_lifecycle/lifecycle_node.hpp"' in content
    assert '#include "rclcpp_lifecycle/state.hpp"' in content
    assert "rclcpp_lifecycle::LifecycleNode" in content
    assert "CallbackReturn" in content


def test_generate_cpp_lifecycle_node_class_structure(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_lc_node"

    generated_file = CodeGenerator.generate_cpp_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    assert f"class My_cpp_lc_nodeNode : public rclcpp_lifecycle::LifecycleNode" in content
    assert f'My_cpp_lc_nodeNode() : rclcpp_lifecycle::LifecycleNode("my_cpp_lc_node")' in content
    assert "int main(int argc, char * argv[])" in content
    assert "auto node = std::make_shared<My_cpp_lc_nodeNode>();" in content
    assert "rclcpp::spin(node->get_node_base_interface());" in content
    assert "rclcpp::spin(std::make_shared" not in content


def test_generate_cpp_lifecycle_node_callbacks_present(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_lc_node"

    generated_file = CodeGenerator.generate_cpp_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    for callback in [
        "on_configure",
        "on_activate",
        "on_deactivate",
        "on_cleanup",
        "on_shutdown",
        "on_error"
    ]:
        assert f"{callback}(" in content, f"Missing callback: {callback}"


def test_generate_cpp_lifecycle_node_callbacks_return_success(tmp_path):
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_lc_node"

    generated_file = CodeGenerator.generate_cpp_lifecycle_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    assert content.count("CallbackReturn::SUCCESS") == 6


# ── CMakeLists.txt lifecycle integration tests ───────────────────────

def test_modify_cmakelists_lifecycle(tmp_path):
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text("""cmake_minimum_required(VERSION 3.8)
project(test_pkg)

find_package(rclcpp REQUIRED)

ament_package()
""")

    CodeGenerator.modify_cmakelists(str(cmakelists), "my_lc_node", lifecycle=True)

    with open(cmakelists, "r") as f:
        content = f.read()

    assert "add_executable(my_lc_node src/my_lc_node.cpp)" in content
    assert "ament_target_dependencies(my_lc_node rclcpp rclcpp_lifecycle)" in content
    assert "find_package(rclcpp_lifecycle REQUIRED)" in content
    assert "install(TARGETS my_lc_node" in content


def test_modify_cmakelists_lifecycle_idempotent(tmp_path):
    """Repeated calls with lifecycle=True must not duplicate anything."""
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text("""cmake_minimum_required(VERSION 3.8)
project(test_pkg)

find_package(rclcpp REQUIRED)

ament_package()
""")

    CodeGenerator.modify_cmakelists(str(cmakelists), "my_lc_node", lifecycle=True)

    with open(cmakelists, "r") as f:
        first_pass = f.read()

    CodeGenerator.modify_cmakelists(str(cmakelists), "my_lc_node", lifecycle=True)

    with open(cmakelists, "r") as f:
        second_pass = f.read()

    assert first_pass == second_pass
    # No duplication of find_package
    assert first_pass.count("find_package(rclcpp_lifecycle REQUIRED)") == 1


# ── package.xml lifecycle integration tests ──────────────────────────

def test_modify_package_xml_adds_dependency(tmp_path):
    package_xml = tmp_path / "package.xml"
    package_xml.write_text("""<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>test_pkg</name>
  <version>0.0.0</version>
  <description>Test package</description>
  <maintainer email="user@example.com">user</maintainer>
  <license>Apache-2.0</license>

  <depend>rclcpp</depend>
</package>
""")

    CodeGenerator.modify_package_xml(str(package_xml), "rclcpp_lifecycle")

    with open(package_xml, "r") as f:
        content = f.read()

    assert "<depend>rclcpp_lifecycle</depend>" in content


def test_modify_package_xml_no_duplicate(tmp_path):
    package_xml = tmp_path / "package.xml"
    package_xml.write_text("""<?xml version="1.0"?>
<package format="3">
  <name>test_pkg</name>
  <version>0.0.0</version>
  <description>Test</description>
  <maintainer email="u@e.com">u</maintainer>
  <license>Apache-2.0</license>
  <depend>rclcpp_lifecycle</depend>
</package>
""")

    CodeGenerator.modify_package_xml(str(package_xml), "rclcpp_lifecycle")

    with open(package_xml, "r") as f:
        content = f.read()

    assert content.count("<depend>rclcpp_lifecycle</depend>") == 1


def test_modify_package_xml_no_file():
    with pytest.raises(FileNotFoundError):
        CodeGenerator.modify_package_xml("invalid/package.xml", "rclcpp_lifecycle")


def test_generate_cpp_node_unchanged(tmp_path):
    """Regression: normal C++ node generation is untouched."""
    package_dir = tmp_path
    package_name = "test_pkg"
    node_name = "my_cpp_node"

    generated_file = CodeGenerator.generate_cpp_node(
        str(package_dir), package_name, node_name
    )

    with open(generated_file, "r") as f:
        content = f.read()

    assert "class My_cpp_nodeNode : public rclcpp::Node" in content
    assert "LifecycleNode" not in content
    assert "lifecycle" not in content.lower()


def test_modify_cmakelists_adds_find_package_rclcpp(tmp_path):
    cmakelists_path = tmp_path / "CMakeLists.txt"
    cmakelists_path.write_text("find_package(ament_cmake REQUIRED)\nament_package()\n")

    CodeGenerator.modify_cmakelists(str(cmakelists_path), "my_cpp_node")
    content = cmakelists_path.read_text()

    assert "find_package(rclcpp REQUIRED)" in content
    assert "add_executable(my_cpp_node src/my_cpp_node.cpp)" in content
    assert "ament_target_dependencies(my_cpp_node rclcpp)" in content


def test_ensure_rclcpp_depend_in_package_xml(tmp_path):
    package_xml = tmp_path / "package.xml"
    package_xml.write_text("<package>\n  <name>test_pkg</name>\n</package>")

    CodeGenerator.ensure_rclcpp_depend_in_package_xml(str(package_xml))
    content = package_xml.read_text()

    assert "<depend>rclcpp</depend>" in content

def test_validate_package_language_compat(tmp_path):
    from core.code_generator import CodeGenerator
    pkg_path = tmp_path / "my_pkg"
    pkg_path.mkdir()
    
    # Empty dir
    valid, msg = CodeGenerator.validate_package_language_compat(str(pkg_path), "python")
    assert not valid
    assert "Cannot add a Python node" in msg
    
    valid, msg = CodeGenerator.validate_package_language_compat(str(pkg_path), "cpp")
    assert not valid
    assert "Cannot add a C++ node" in msg
    
    # Python pkg
    (pkg_path / "setup.py").touch()
    valid, msg = CodeGenerator.validate_package_language_compat(str(pkg_path), "python")
    assert valid
    assert msg == ""
    
    # Cpp pkg
    (pkg_path / "CMakeLists.txt").touch()
    valid, msg = CodeGenerator.validate_package_language_compat(str(pkg_path), "cpp")
    assert valid
    assert msg == ""
