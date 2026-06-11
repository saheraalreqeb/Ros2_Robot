import subprocess
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class ROS2CLI:
    """Wrapper for ROS2 command line interface."""
    
    def __init__(self, use_wsl: bool = False):
        """
        Initialize the ROS2CLI wrapper.
        
        Args:
            use_wsl (bool): Whether to prefix commands with 'wsl' for execution on Windows. Default False because we run natively inside WSL.
        """
        self.use_wsl = use_wsl
        self.workspace_path = None

    def set_workspace(self, path: str):
        self.workspace_path = path

    def _run_command(self, cmd: List[str], cwd: Optional[str] = None) -> str:
        """
        Run a command and return its output as a string.
        
        Args:
            cmd (List[str]): The command and its arguments.
            cwd (Optional[str]): Working directory to execute the command in.
            
        Returns:
            str: Standard output of the command.
            
        Raises:
            RuntimeError: If the command execution fails.
        """
        import os
        import re

        def to_wsl_path(win_path: str) -> str:
            if not win_path:
                return win_path
            path = win_path.replace('\\', '/')
            match = re.match(r'^([a-zA-Z]):(.*)', path)
            if match:
                drive = match.group(1).lower()
                return f"/mnt/{drive}{match.group(2)}"
            return path

        if self.use_wsl:
            # Build a shell command that optionally sources setup.bash
            # before running the ROS2 command.  We cannot use os.path.exists
            # here because the path lives inside WSL, not on Windows.
            cmd_str = " ".join(cmd)
            if self.workspace_path:
                setup_bash_wsl = to_wsl_path(
                    os.path.join(self.workspace_path, 'install', 'setup.bash')
                )
                shell_cmd = (
                    f'[ -f "{setup_bash_wsl}" ] && source "{setup_bash_wsl}"; '
                    f'{cmd_str}'
                )
            else:
                shell_cmd = cmd_str
            final_cmd = ['wsl', 'bash', '-i', '-c', shell_cmd]
            run_cwd = None  # WSL cannot use a Windows CWD
        else:
            if self.workspace_path:
                setup_bash = os.path.join(self.workspace_path, 'install', 'setup.bash')
                if os.path.exists(setup_bash):
                    cmd_str = " ".join(cmd)
                    cmd = ['bash', '-c', f'source "{setup_bash}" && {cmd_str}']
            final_cmd = cmd
            run_cwd = cwd

        try:
            logger.debug(f"Running command: {' '.join(final_cmd)}")
            result = subprocess.run(
                final_cmd,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {e.cmd}")
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
            raise RuntimeError(f"ROS2 command failed: {e.stderr}") from e
        except FileNotFoundError as e:
            logger.error(f"Command not found: {final_cmd[0]}")
            raise RuntimeError(f"Command not found: {final_cmd[0]}. Ensure WSL/ROS2 is installed.") from e

    def pkg_create(
        self, 
        package_name: str, 
        build_type: str = 'ament_python', 
        dependencies: Optional[List[str]] = None, 
        cwd: Optional[str] = None
    ) -> str:
        """
        Create a new ROS2 package.
        
        Args:
            package_name (str): The name of the new package.
            build_type (str): Build system to use ('ament_python' or 'ament_cmake').
            dependencies (Optional[List[str]]): List of ROS2 package dependencies.
            cwd (Optional[str]): Directory to create the package in (typically workspace 'src').
            
        Returns:
            str: The output of the command.
        """
        cmd = ['ros2', 'pkg', 'create', package_name, '--build-type', build_type]
        if dependencies:
            cmd.extend(['--dependencies'] + dependencies)
        return self._run_command(cmd, cwd=cwd)

    def node_list(self) -> List[str]:
        """
        List running ROS2 nodes.
        
        Returns:
            List[str]: List of running node names.
        """
        cmd = ['ros2', 'node', 'list']
        try:
            output = self._run_command(cmd)
            return [line.strip() for line in output.split('\n') if line.strip()]
        except RuntimeError:
            # Command might fail if no ROS2 daemon is running or WSL fails
            return []

    def topic_list(self) -> List[str]:
        """
        List active ROS2 topics.
        
        Returns:
            List[str]: List of active topic names.
        """
        cmd = ['ros2', 'topic', 'list']
        try:
            output = self._run_command(cmd)
            return [line.strip() for line in output.split('\n') if line.strip()]
        except RuntimeError:
            return []

    def get_topology(self) -> dict:
        """
        Runs ros2 node list and parses ros2 node info <node> for Publishers and Subscribers.
        Returns a dictionary representing the topology graph.
        """
        nodes = self.node_list()
        topology = {
            'nodes': nodes,
            'topics': set(),
            'edges': []
        }
        
        if not nodes:
            return topology

        import concurrent.futures

        def get_node_info(node):
            cmd = ['ros2', 'node', 'info', node]
            try:
                output = self._run_command(cmd)
                return node, output
            except Exception:
                return node, ""

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(nodes), 16)) as executor:
            # Map the helper function over all nodes in parallel threads
            results = executor.map(get_node_info, nodes)

        for node, output in results:
            if not output:
                continue
                
            current_section = None
            for line in output.split('\n'):
                line = line.rstrip()
                if not line:
                    continue
                    
                if not line.startswith(' '):
                    # Node name or other top-level output
                    continue
                    
                if line.startswith('  ') and not line.startswith('    '):
                    # Section header
                    current_section = line.strip().rstrip(':')
                    continue
                    
                if line.startswith('    '):
                    # Item in the section
                    item = line.strip()
                    # Example item: "/topic: std_msgs/msg/String"
                    if ':' in item:
                        topic_name = item.split(':')[0].strip()
                    else:
                        topic_name = item
                        
                    if current_section == 'Publishers':
                        topology['topics'].add(topic_name)
                        topology['edges'].append({
                            'src': node,
                            'dst': topic_name,
                            'label': 'publish'
                        })
                    elif current_section == 'Subscribers':
                        topology['topics'].add(topic_name)
                        topology['edges'].append({
                            'src': topic_name,
                            'dst': node,
                            'label': 'subscribe'
                        })
                        
        topology['topics'] = list(topology['topics'])
        return topology

    def service_list(self) -> List[str]:
        """
        List active ROS2 services.
        
        Returns:
            List[str]: List of active service names.
        """
        cmd = ['ros2', 'service', 'list']
        try:
            output = self._run_command(cmd)
            return [line.strip() for line in output.split('\n') if line.strip()]
        except RuntimeError:
            return []

    def action_list(self) -> List[str]:
        """
        List active ROS2 actions.
        
        Returns:
            List[str]: List of active action names.
        """
        cmd = ['ros2', 'action', 'list']
        try:
            output = self._run_command(cmd)
            return [line.strip() for line in output.split('\n') if line.strip()]
        except RuntimeError:
            return []

    def action_info(self, name: str) -> str:
        """
        Get info for a ROS2 action.
        
        Args:
            name (str): Action name.
            
        Returns:
            str: Raw action info output.
        """
        cmd = ['ros2', 'action', 'info', name]
        try:
            return self._run_command(cmd)
        except RuntimeError as exc:
            return str(exc)
