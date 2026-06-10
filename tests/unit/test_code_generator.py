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
