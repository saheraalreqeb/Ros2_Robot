import pytest
from unittest.mock import MagicMock
from gui.main_window import MainWindow

@pytest.fixture
def mock_ros2_cli(mocker):
    """Mocks the subprocess.run call used by ROS2CLI to prevent real process execution."""
    mock_run = mocker.patch('core.ros2_cli.subprocess.run')
    mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
    return mock_run

@pytest.fixture
def main_window(qtbot, mock_ros2_cli):
    """Provides an instance of the MainWindow with mocked ROS2 CLI."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window

@pytest.fixture
def mock_subprocess_popen(mocker):
    """Mocks subprocess.Popen to prevent real background processes."""
    return mocker.patch('subprocess.Popen')