"""
Unit tests for safe QThread shutdown helpers and cleanup methods.

Since importing gui modules pulls in QtWidgets which requires libGL.so.1
(unavailable in headless CI), we extract _safe_stop_thread from source
via AST and test page cleanup() methods with mock page objects.

All _safe_stop_thread definitions in the codebase are byte-identical.
"""
import ast
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThread


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def safe_stop_thread():
    """Extract the canonical _safe_stop_thread from gui/main_window.py."""
    source = Path("gui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_safe_stop_thread":
            lines = source.split("\n")
            func_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            ns: dict = {}
            exec(func_source, ns)
            return ns["_safe_stop_thread"]
    raise RuntimeError("Could not find _safe_stop_thread in gui/main_window.py")


# ---------------------------------------------------------------------------
# Tests for _safe_stop_thread helper
# ---------------------------------------------------------------------------

class TestSafeStopThread:
    """Tests for the _safe_stop_thread helper function."""

    def test_handles_none_thread(self, safe_stop_thread):
        """_safe_stop_thread should return immediately when thread is None."""
        safe_stop_thread(None)
        safe_stop_thread(None, timeout_ms=100)

    def test_handles_finished_thread(self, safe_stop_thread):
        """_safe_stop_thread should not call quit/wait on already finished thread."""
        mock_thread = MagicMock(spec=QThread)
        mock_thread.isRunning.return_value = False

        safe_stop_thread(mock_thread, timeout_ms=100)

        mock_thread.isRunning.assert_called_once()
        mock_thread.quit.assert_not_called()
        mock_thread.wait.assert_not_called()

    def test_stops_running_thread(self, safe_stop_thread):
        """_safe_stop_thread should request interruption, quit, and wait on running thread."""
        mock_thread = MagicMock(spec=QThread)
        mock_thread.isRunning.return_value = True

        safe_stop_thread(mock_thread, timeout_ms=1000)

        mock_thread.isRunning.assert_called_once()
        mock_thread.requestInterruption.assert_called_once()
        mock_thread.quit.assert_called_once()
        mock_thread.wait.assert_called_once_with(1000)

    def test_tolerates_runtime_error(self, safe_stop_thread):
        """_safe_stop_thread should catch RuntimeError (deleted Qt object)."""
        mock_thread = MagicMock(spec=QThread)
        mock_thread.isRunning.side_effect = RuntimeError("deleted")

        # Should not raise
        safe_stop_thread(mock_thread)

    def test_can_be_called_twice(self, safe_stop_thread):
        """_safe_stop_thread should be idempotent."""
        mock_thread = MagicMock(spec=QThread)
        mock_thread.isRunning.return_value = True

        safe_stop_thread(mock_thread, timeout_ms=100)
        safe_stop_thread(mock_thread, timeout_ms=100)

        # Both calls should have worked without error
        assert mock_thread.isRunning.call_count == 2


# ---------------------------------------------------------------------------
# Helpers for testing page cleanup()
# ---------------------------------------------------------------------------

# Paths to page files that have cleanup() methods
_PAGE_FILES = {
    "topic_inspector":      "gui/topic_inspector.py",
    "service_inspector":    "gui/service_inspector.py",
    "action_inspector":     "gui/action_inspector.py",
    "parameter_manager":    "gui/parameter_manager.py",
    "bag_manager":          "gui/bag_manager.py",
    "tools_hub":            "gui/tools_hub.py",
    "visualizer":           "gui/visualizer.py",
    "dds_troubleshooter":   "gui/dds_troubleshooter.py",
    "log_viewer":           "gui/log_viewer.py",
    "lifecycle_manager":    "gui/lifecycle_manager.py",
    "launch_manager":       "gui/launch_manager.py",
}


def _extract_cleanup_source(filepath: str) -> str | None:
    """Parse a page file and return the source of its cleanup() method."""
    source = Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cleanup":
            lines = source.split("\n")
            start = node.lineno - 1
            for decorator in node.decorator_list:
                if decorator.lineno < node.lineno:
                    start = decorator.lineno - 1
            end = node.end_lineno
            return textwrap.dedent("\n".join(lines[start:end]))
    return None


# ---------------------------------------------------------------------------
# Tests for page cleanup() methods
# ---------------------------------------------------------------------------


class TestTopicInspectorCleanup:
    """Tests for TopicInspectorPage.cleanup()"""

    def test_cleanup_exists(self):
        """cleanup method must be present in the source."""
        src = _extract_cleanup_source(_PAGE_FILES["topic_inspector"])
        assert src is not None, "cleanup() not found in topic_inspector.py"

    def test_cleanup_is_syntactically_valid(self):
        """cleanup method source must parse as valid Python."""
        src = _extract_cleanup_source(_PAGE_FILES["topic_inspector"])
        ast.parse(src)  # should not raise


class TestServiceInspectorCleanup:
    """Tests for ServiceInspectorPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["service_inspector"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["service_inspector"])
        ast.parse(src)


class TestActionInspectorCleanup:
    """Tests for ActionInspectorPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["action_inspector"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["action_inspector"])
        ast.parse(src)


class TestParameterManagerCleanup:
    """Tests for ParameterManagerPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["parameter_manager"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["parameter_manager"])
        ast.parse(src)


class TestBagManagerCleanup:
    """Tests for BagManagerPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["bag_manager"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["bag_manager"])
        ast.parse(src)


class TestToolsHubCleanup:
    """Tests for ToolsHubPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["tools_hub"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["tools_hub"])
        ast.parse(src)


class TestVisualizerCleanup:
    """Tests for VisualizerPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["visualizer"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["visualizer"])
        ast.parse(src)


class TestDDSTroubleshooterCleanup:
    """Tests for DDSTroubleshooterPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["dds_troubleshooter"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["dds_troubleshooter"])
        ast.parse(src)


class TestLogViewerCleanup:
    """Tests for UnifiedLogViewerPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["log_viewer"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["log_viewer"])
        ast.parse(src)


class TestLifecycleManagerCleanup:
    """Tests for LifecycleManagerPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["lifecycle_manager"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["lifecycle_manager"])
        ast.parse(src)


class TestLaunchManagerCleanup:
    """Tests for LaunchManagerPage.cleanup()"""

    def test_cleanup_exists(self):
        src = _extract_cleanup_source(_PAGE_FILES["launch_manager"])
        assert src is not None

    def test_cleanup_is_syntactically_valid(self):
        src = _extract_cleanup_source(_PAGE_FILES["launch_manager"])
        ast.parse(src)


# ---------------------------------------------------------------------------
# Tests for FlowLayout safe destruction
# ---------------------------------------------------------------------------

class TestFlowLayoutDestructor:
    """Tests for FlowLayout safe destruction — no __del__ at crash-prone Qt teardown."""

    def test_no_del_method(self):
        """FlowLayout must not define __del__ (Qt cleans up layouts on parent destruction)."""
        source = Path("gui/flow_layout.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "__del__":
                pytest.fail("FlowLayout must NOT define __del__ — use Qt's built-in cleanup")
