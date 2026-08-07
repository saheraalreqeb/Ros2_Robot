import os
import re

class CodeGenerator:
    @staticmethod
    def generate_python_node(package_dir: str, package_name: str, node_name: str) -> str:
        """
        Generates a boilerplate 'Hello World' Python node inside a target package's directory.
        Returns the path to the generated file.
        """
        content = f"""import rclpy
from rclpy.node import Node

class {node_name.capitalize()}Node(Node):
    def __init__(self):
        super().__init__('{node_name}')
        self.get_logger().info('Hello World from {node_name}')

def main(args=None):
    rclpy.init(args=args)
    node = {node_name.capitalize()}Node()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
"""
        node_file_name = f"{node_name}.py"
        target_dir = os.path.join(package_dir, package_name)
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, node_file_name)
        
        with open(target_file, 'w') as f:
            f.write(content)
            
        # Also ensure __init__.py exists
        init_file = os.path.join(target_dir, '__init__.py')
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                pass
                
        return target_file

    @staticmethod
    def generate_python_lifecycle_node(package_dir: str, package_name: str, node_name: str) -> str:
        """
        Generates a Python lifecycle node using rclpy.lifecycle.LifecycleNode.
        Returns the path to the generated file.
        """
        class_name = f"{node_name.capitalize()}Node"
        content = f"""import rclpy
from rclpy.lifecycle import LifecycleNode
from rclpy.lifecycle import TransitionCallbackReturn

class {class_name}(LifecycleNode):
    def __init__(self):
        super().__init__('{node_name}')
        self.get_logger().info("Lifecycle node created: state = unconfigured")

    def on_configure(self, state):
        self.get_logger().info("on_configure() called")
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state):
        self.get_logger().info("on_activate() called")
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state):
        self.get_logger().info("on_deactivate() called")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state):
        self.get_logger().info("on_cleanup() called")
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state):
        self.get_logger().info("on_shutdown() called")
        return TransitionCallbackReturn.SUCCESS

    def on_error(self, state):
        self.get_logger().error("on_error() called")
        return TransitionCallbackReturn.SUCCESS

def main(args=None):
    rclpy.init(args=args)
    node = {class_name}()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
"""
        node_file_name = f"{node_name}.py"
        target_dir = os.path.join(package_dir, package_name)
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, node_file_name)

        with open(target_file, 'w') as f:
            f.write(content)

        init_file = os.path.join(target_dir, '__init__.py')
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                pass

        return target_file

    @staticmethod
    def generate_cpp_node(package_dir: str, package_name: str, node_name: str) -> str:
        """
        Generates a boilerplate C++ node.
        Returns the path to the generated file.
        """
        content = f"""#include "rclcpp/rclcpp.hpp"

class {node_name.capitalize()}Node : public rclcpp::Node
{{
public:
  {node_name.capitalize()}Node() : Node("{node_name}")
  {{
    RCLCPP_INFO(this->get_logger(), "Hello World from {node_name}");
  }}
}};

int main(int argc, char * argv[])
{{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<{node_name.capitalize()}Node>());
  rclcpp::shutdown();
  return 0;
}}
"""
        node_file_name = f"{node_name}.cpp"
        target_dir = os.path.join(package_dir, 'src')
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, node_file_name)
        
        with open(target_file, 'w') as f:
            f.write(content)
            
        return target_file

    @staticmethod
    def generate_cpp_lifecycle_node(package_dir: str, package_name: str, node_name: str) -> str:
        """
        C++ lifecycle node generation is not yet supported.
        Raises NotImplementedError with a clear message.
        """
        raise NotImplementedError(
            "Lifecycle node generation is currently supported for Python only."
        )

    @staticmethod
    def modify_setup_py(setup_py_path: str, package_name: str, node_name: str, module_name: str = None):
        """
        Modifies an existing setup.py to safely insert the new entry_point for a python node.
        Raises an error if the insertion point cannot be found.
        """
        if module_name is None:
            module_name = node_name

        if not os.path.exists(setup_py_path):
            raise FileNotFoundError(f"setup.py not found at {setup_py_path}")

        with open(setup_py_path, 'r') as f:
            content = f.read()

        # Regex to find 'console_scripts': [ ... ]
        pattern = r"(['\"]console_scripts['\"]\s*:\s*\[)(.*?)(\])"
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            raise ValueError(f"Could not find 'console_scripts' array in {setup_py_path}")

        prefix = match.group(1)
        existing_scripts = match.group(2)
        suffix = match.group(3)

        entry_point_str = f"{node_name} = {package_name}.{module_name}:main"

        if entry_point_str in existing_scripts:
            return  # Entry point already exists

        stripped_scripts = existing_scripts.strip()
        if stripped_scripts:
            if not stripped_scripts.endswith(','):
                existing_scripts = existing_scripts.rstrip() + ',\n            '
            else:
                existing_scripts = existing_scripts.rstrip() + '\n            '
        else:
            existing_scripts = '\n            '

        new_script_line = f"'{entry_point_str}',\n        "
        new_scripts = existing_scripts + new_script_line

        new_content = content[:match.start(2)] + new_scripts + content[match.end(2):]

        with open(setup_py_path, 'w') as f:
            f.write(new_content)

    @staticmethod
    def modify_cmakelists(cmakelists_path: str, node_name: str):
        """
        Modifies an existing CMakeLists.txt to add executable, ament_target_dependencies,
        and install directives for a new C++ node.
        Raises an error if the insertion point cannot be found.
        """
        if not os.path.exists(cmakelists_path):
            raise FileNotFoundError(f"CMakeLists.txt not found at {cmakelists_path}")

        with open(cmakelists_path, 'r') as f:
            content = f.read()

        # Check if node is already added to avoid duplicates
        if f"add_executable({node_name}" in content:
            return

        if 'ament_package()' not in content:
            raise ValueError(f"Could not find 'ament_package()' in {cmakelists_path} to insert node definitions.")

        injection = f"""
add_executable({node_name} src/{node_name}.cpp)
ament_target_dependencies({node_name} rclcpp)

install(TARGETS {node_name}
  DESTINATION lib/${{PROJECT_NAME}}
)
"""
        new_content = content.replace('ament_package()', f'{injection}\nament_package()')

        with open(cmakelists_path, 'w') as f:
            f.write(new_content)
