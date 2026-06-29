import pytest
from unittest.mock import MagicMock
from core.ros2_cli import ROS2CLI

def test_ros2_cli_init():
    cli = ROS2CLI(use_wsl=True)
    assert cli.use_wsl
    assert cli.workspace_path is None

    cli.set_workspace("/path/to/workspace")
    assert cli.workspace_path == "/path/to/workspace"

def test_ros2_cli_run_command_native(mocker):
    mock_run = mocker.patch("core.ros2_cli.subprocess.run")
    mock_run.return_value = MagicMock(stdout="Output of command", stderr="", returncode=0)

    cli = ROS2CLI(use_wsl=False)
    result = cli._run_command(["ros2", "node", "list"])

    assert result == "Output of command"
    mock_run.assert_called_once_with(
        ["ros2", "node", "list"],
        cwd=None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=None
    )

def test_ros2_cli_run_command_native_with_workspace(mocker):
    mock_run = mocker.patch("core.ros2_cli.subprocess.run")
    mock_run.return_value = MagicMock(stdout="Success", stderr="", returncode=0)
    mocker.patch("os.path.exists", return_value=True)

    cli = ROS2CLI(use_wsl=False)
    cli.set_workspace("/my/workspace")
    result = cli._run_command(["ros2", "node", "list"])

    assert result == "Success"
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "bash"
    assert args[1] == "-c"
    assert "source" in args[2]
    assert "setup.bash" in args[2]

def test_ros2_cli_run_command_wsl(mocker):
    mock_run = mocker.patch("core.ros2_cli.subprocess.run")
    mock_run.return_value = MagicMock(stdout="WSL output", stderr="", returncode=0)

    cli = ROS2CLI(use_wsl=True)
    result = cli._run_command(["ros2", "node", "list"])

    assert result == "WSL output"
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "wsl"
    assert args[1] == "bash"
    assert args[2] == "-i"
    assert args[3] == "-c"
    assert args[4] == "ros2 node list"

def test_ros2_cli_run_command_wsl_with_workspace(mocker):
    mock_run = mocker.patch("core.ros2_cli.subprocess.run")
    mock_run.return_value = MagicMock(stdout="WSL Workspace Output", stderr="", returncode=0)

    cli = ROS2CLI(use_wsl=True)
    cli.set_workspace(r"C:\Users\user\ws")
    result = cli._run_command(["ros2", "node", "list"])

    assert result == "WSL Workspace Output"
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "wsl"
    assert args[4].startswith('[ -f "/mnt/c/Users/user/ws/install/setup.bash" ]')

def test_ros2_cli_pkg_create(mocker):
    cli = ROS2CLI(use_wsl=False)
    mock_run = mocker.patch.object(cli, "_run_command", return_value="Created package")
    
    res = cli.pkg_create("new_pkg", build_type="ament_python", dependencies=["rclpy", "std_msgs"])
    assert res == "Created package"
    mock_run.assert_called_once_with(
        ["ros2", "pkg", "create", "new_pkg", "--build-type", "ament_python", "--dependencies", "rclpy", "std_msgs"],
        cwd=None
    )

def test_ros2_cli_node_list(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", return_value="/node1\n/node2\n")
    
    nodes = cli.node_list()
    assert nodes == ["/node1", "/node2"]

def test_ros2_cli_node_list_failure(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", side_effect=RuntimeError("ros2 daemon not running"))
    
    nodes = cli.node_list()
    assert nodes == []

def test_ros2_cli_topic_list(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", return_value="/topic1\n/topic2\n")
    
    topics = cli.topic_list()
    assert topics == ["/topic1", "/topic2"]

def test_ros2_cli_get_topology(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "node_list", return_value=["/talker", "/listener"])
    
    def mock_run_cmd(cmd, cwd=None):
        if "/talker" in cmd:
            return """
/talker
  Publishers:
    /chatter: std_msgs/msg/String
  Subscribers:
"""
        elif "/listener" in cmd:
            return """
/listener
  Publishers:
  Subscribers:
    /chatter: std_msgs/msg/String
"""
        return ""
    
    mocker.patch.object(cli, "_run_command", side_effect=mock_run_cmd)
    
    topology = cli.get_topology()
    assert topology["nodes"] == ["/talker", "/listener"]
    assert "/chatter" in topology["topics"]
    
    # Check edges
    edges = topology["edges"]
    assert len(edges) == 2
    
    # Edge from /talker to /chatter (publish)
    edge1 = next(e for e in edges if e["src"] == "/talker")
    assert edge1["dst"] == "/chatter"
    assert edge1["label"] == "publish"
    
    # Edge from /chatter to /listener (subscribe)
    edge2 = next(e for e in edges if e["src"] == "/chatter")
    assert edge2["dst"] == "/listener"
    assert edge2["label"] == "subscribe"


def test_ros2_cli_lifecycle_nodes(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", return_value="/node1\n/node2\n")
    nodes = cli.lifecycle_nodes()
    assert nodes == ["/node1", "/node2"]


def test_ros2_cli_lifecycle_nodes_failure(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", side_effect=RuntimeError("daemon not running"))
    nodes = cli.lifecycle_nodes()
    assert nodes == []


def test_ros2_cli_lifecycle_get_state(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", return_value="active")
    state = cli.lifecycle_get_state("/my_node")
    assert state == "active"


def test_ros2_cli_lifecycle_get_state_failure(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", side_effect=RuntimeError("node not found"))
    with pytest.raises(RuntimeError, match="node not found"):
        cli.lifecycle_get_state("/nonexistent")


def test_ros2_cli_lifecycle_list_transitions(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", return_value="configure\nactivate\nshutdown\n")
    transitions = cli.lifecycle_list_transitions("/my_node")
    assert transitions == ["configure", "activate", "shutdown"]


def test_ros2_cli_lifecycle_list_transitions_failure(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", side_effect=RuntimeError("node not found"))
    transitions = cli.lifecycle_list_transitions("/nonexistent")
    assert transitions == []


def test_ros2_cli_lifecycle_set_transition(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", return_value="Transition successful")
    result = cli.lifecycle_set_transition("/my_node", "activate")
    assert result == "Transition successful"


def test_ros2_cli_lifecycle_set_transition_failure(mocker):
    cli = ROS2CLI(use_wsl=False)
    mocker.patch.object(cli, "_run_command", side_effect=RuntimeError("transition not available"))
    with pytest.raises(RuntimeError, match="transition not available"):
        cli.lifecycle_set_transition("/my_node", "invalid_transition")


def test_ros2_cli_lifecycle_get_state_timeout(mocker):
    """Test that lifecycle_get_state raises RuntimeError on timeout."""
    import subprocess
    cli = ROS2CLI(use_wsl=False)
    # Simulate TimeoutExpired — subprocess.run raises it
    mocker.patch("core.ros2_cli.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd=["ros2", "lifecycle", "get", "/node"], timeout=5))
    with pytest.raises(RuntimeError, match="timed out"):
        cli.lifecycle_get_state("/node")


def test_ros2_cli_lifecycle_list_transitions_timeout(mocker):
    """Test that lifecycle_list_transitions returns empty list on timeout."""
    import subprocess
    cli = ROS2CLI(use_wsl=False)
    mocker.patch("core.ros2_cli.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd=["ros2", "lifecycle", "list", "/node"], timeout=5))
    # lifecycle_list_transitions catches RuntimeError and returns []
    transitions = cli.lifecycle_list_transitions("/node")
    assert transitions == []


def test_ros2_cli_lifecycle_nodes_timeout(mocker):
    """Test that lifecycle_nodes returns empty list on timeout."""
    import subprocess
    cli = ROS2CLI(use_wsl=False)
    mocker.patch("core.ros2_cli.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd=["ros2", "lifecycle", "nodes"], timeout=5))
    nodes = cli.lifecycle_nodes()
    assert nodes == []


def test_ros2_cli_lifecycle_set_transition_timeout(mocker):
    """Test that lifecycle_set_transition raises RuntimeError on timeout."""
    import subprocess
    cli = ROS2CLI(use_wsl=False)
    mocker.patch("core.ros2_cli.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd=["ros2", "lifecycle", "set", "/node", "activate"], timeout=10))
    with pytest.raises(RuntimeError, match="timed out"):
        cli.lifecycle_set_transition("/node", "activate")
