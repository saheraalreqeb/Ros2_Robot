import os
import re
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET

class ROS2Workspace:
    """Parser and data model for a ROS2 workspace."""
    
    def __init__(self, path: str):
        """
        Initialize the workspace parser.
        
        Args:
            path (str): The root path of the ROS2 workspace.
        """
        self.path = os.path.abspath(path)
        if os.path.basename(self.path) == 'src':
            self.src_path = self.path
            self.path = os.path.dirname(self.path)
        else:
            self.src_path = os.path.join(self.path, 'src')
        
    def is_valid(self) -> bool:
        """
        Check if the workspace appears to be a valid ROS2 workspace.
        
        Returns:
            bool: True if 'src' directory exists, False otherwise.
        """
        return os.path.isdir(self.src_path)
        
    def get_packages(self) -> List[Dict[str, Any]]:
        """
        Scan the workspace src directory for ROS2 packages.
        
        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing package info.
        """
        packages = []
        if not self.is_valid():
            return packages
            
        # Walk through the src directory looking for package.xml
        for root, dirs, files in os.walk(self.src_path):
            if 'package.xml' in files:
                pkg_info = self._parse_package(root)
                if pkg_info:
                    packages.append(pkg_info)
                # Don't recurse further into a package's subdirectories
                dirs.clear()
                
        return packages
        
    def _parse_package(self, package_path: str) -> Optional[Dict[str, Any]]:
        """
        Parse package.xml and setup.py/CMakeLists.txt to gather package info.
        
        Args:
            package_path (str): Path to the package root.
            
        Returns:
            Optional[Dict[str, Any]]: Package information or None on parsing error.
        """
        package_xml_path = os.path.join(package_path, 'package.xml')
        try:
            tree = ET.parse(package_xml_path)
            root_elem = tree.getroot()
            
            name_elem = root_elem.find('name')
            name = name_elem.text if name_elem is not None and name_elem.text else os.path.basename(package_path)
            
            description_elem = root_elem.find('description')
            description = description_elem.text if description_elem is not None and description_elem.text else ""
            
            build_type = 'unknown'
            export_elem = root_elem.find('export')
            if export_elem is not None:
                build_type_elem = export_elem.find('build_type')
                if build_type_elem is not None and build_type_elem.text:
                    build_type = build_type_elem.text
            
            # Identify nodes based on build system
            nodes = []
            if build_type == 'ament_python':
                setup_py_path = os.path.join(package_path, 'setup.py')
                if os.path.exists(setup_py_path):
                    nodes = self._find_python_nodes(setup_py_path)
            elif build_type == 'ament_cmake':
                cmake_lists_path = os.path.join(package_path, 'CMakeLists.txt')
                if os.path.exists(cmake_lists_path):
                    nodes = self._find_cmake_nodes(cmake_lists_path)
                    
            return {
                'name': name.strip(),
                'path': package_path,
                'description': description.strip(),
                'build_type': build_type.strip(),
                'nodes': nodes
            }
        except ET.ParseError:
            # Handle malformed XML gracefully
            return None
        except Exception as e:
            return None
            
    def _find_python_nodes(self, setup_py_path: str) -> List[str]:
        """
        Parse setup.py entry_points to find python nodes.
        Fallback to scanning the package directory for .py files.
        """
        nodes = []
        package_path = os.path.dirname(setup_py_path)
        package_name = os.path.basename(package_path)
        
        try:
            with open(setup_py_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Naive regex to find console_scripts block
                pattern = r"['\"]?console_scripts['\"]?\s*:\s*\[(.*?)\]"
                match = re.search(pattern, content, re.DOTALL)
                
                if match:
                    scripts_block = match.group(1)
                    # Extract node names: 'my_node = my_pkg.my_node:main'
                    for line in scripts_block.split('\n'):
                        line = line.strip().strip("'").strip('"').strip(',')
                        if '=' in line:
                            node_name = line.split('=')[0].strip()
                            # remove inner quotes if any
                            node_name = node_name.strip("'").strip('"')
                            nodes.append(node_name)
        except Exception:
            pass
            
        # Fallback: if no nodes found via static parsing, scan the actual python package directory
        if not nodes:
            # The python module folder is usually the same as the package name
            module_dir = os.path.join(package_path, package_name)
            if os.path.isdir(module_dir):
                for py_file in os.listdir(module_dir):
                    if py_file.endswith('.py') and py_file != '__init__.py':
                        nodes.append(py_file[:-3])
                        
        return nodes
        
    def _find_cmake_nodes(self, cmake_lists_path: str) -> List[str]:
        """
        Parse CMakeLists.txt to find C++ nodes.
        
        Args:
            cmake_lists_path (str): Path to the CMakeLists.txt file.
            
        Returns:
            List[str]: List of executable node names.
        """
        nodes = []
        try:
            with open(cmake_lists_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Naive regex to find add_executable calls
                pattern = r"add_executable\s*\(\s*([^\s]+)"
                matches = re.finditer(pattern, content, re.IGNORECASE)
                
                for match in matches:
                    nodes.append(match.group(1).strip())
        except Exception:
            pass
        return nodes
