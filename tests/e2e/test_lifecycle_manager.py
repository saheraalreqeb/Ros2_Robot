"""E2E tests for the Lifecycle Manager page."""
import subprocess
from unittest.mock import MagicMock
from PySide6.QtWidgets import QListWidget, QTextEdit, QLabel, QPushButton
from PySide6.QtCore import Qt


def test_navigation_to_lifecycle_page(qtbot, main_window):
    """Verify clicking the lifecycle nav button switches to the correct page."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None, "Lifecycle Manager nav button not found"
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    # Verify the page is present by finding the title label
    title = main_window.findChild(QLabel, "lifecycle_title_label")
    assert title is not None, "Lifecycle Manager title not found"


def test_refresh_lifecycle_nodes_success(qtbot, main_window, mock_ros2_cli):
    """Test that refresh populates the node list with mocked CLI output."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    # Mock lifecycle nodes output
    mock_ros2_cli.return_value.stdout = "/lifecycle_node_1\n/lifecycle_node_2"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)

    # Wait for worker thread to complete
    qtbot.wait(500)

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    assert node_list.count() == 2
    assert node_list.item(0).text() == "/lifecycle_node_1"
    assert node_list.item(1).text() == "/lifecycle_node_2"


def test_refresh_lifecycle_nodes_empty(qtbot, main_window, mock_ros2_cli):
    """Test empty lifecycle node list."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = ""
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    assert node_list.count() == 0


def test_transition_buttons_exist(qtbot, main_window):
    """Verify all 5 transition buttons exist on the page."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    transitions = ["configure", "activate", "deactivate", "cleanup", "shutdown"]
    for t in transitions:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None, f"Button btn_transition_{t} not found"


def test_output_console_exists(qtbot, main_window):
    """Verify output console widget exists."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    console = main_window.findChild(QTextEdit, "text_output_console")
    assert console is not None, "Output console not found"


def test_selected_node_labels_exist(qtbot, main_window):
    """Verify node selection labels exist on the page."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    lbl_node = main_window.findChild(QLabel, "lbl_selected_node")
    assert lbl_node is not None, "Selected node label not found"

    lbl_state = main_window.findChild(QLabel, "lbl_current_state")
    assert lbl_state is not None, "Current state label not found"


def test_transition_buttons_disabled_without_selection(qtbot, main_window):
    """Verify transition buttons are disabled when no node is selected."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    transitions = ["configure", "activate", "deactivate", "cleanup", "shutdown"]
    for t in transitions:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert not btn.isEnabled(), f"btn_transition_{t} should be disabled"


def test_refresh_lifecycle_cli_error(qtbot, main_window, mock_ros2_cli):
    """Test refresh when CLI returns an error."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.returncode = 1
    mock_ros2_cli.return_value.stderr = "Lifecycle CLI error"

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    # Node list should remain empty after CLI error
    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    assert node_list.count() == 0


def test_node_selection_loads_state(qtbot, main_window, mock_ros2_cli):
    """Verify selecting a node triggers state and transitions fetch."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    assert node_list.count() == 1

    # Set up mock for state and transitions when node is selected
    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        result = MagicMock(stdout="", stderr="", returncode=0)
        if "lifecycle get" in cmd_str:
            result.stdout = "active"
        elif "lifecycle list" in cmd_str:
            result.stdout = "configure\nactivate\ndeactivate"
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None  # clear return_value so side_effect takes over

    # Select the node
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    lbl_state = main_window.findChild(QLabel, "lbl_current_state")
    assert lbl_state is not None


def test_execute_transition(qtbot, main_window, mock_ros2_cli):
    """Verify clicking a transition button triggers the CLI call."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    # First, populate the list
    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    # Set up side_effect for state, transitions, and set commands
    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        result = MagicMock(stdout="", stderr="", returncode=0)
        if "lifecycle get" in cmd_str:
            result.stdout = "inactive"
        elif "lifecycle list" in cmd_str:
            result.stdout = "configure\nshutdown"
        elif "lifecycle set" in cmd_str:
            result.stdout = "Transitioning successfully"
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    # Select the node
    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    # Click configure button
    btn_configure = main_window.findChild(QPushButton, "btn_transition_configure")
    assert btn_configure is not None
    qtbot.mouseClick(btn_configure, Qt.LeftButton)
    qtbot.wait(500)

    # Verify that lifecycle set was called
    set_calls = [
        call for call in mock_ros2_cli.call_args_list
        if "lifecycle set" in " ".join(call[0][0])
    ]
    assert len(set_calls) >= 1, "Expected lifecycle set transition CLI call"


def test_transitions_text_widget_exists(qtbot, main_window):
    """Verify the transitions text widget exists on the page."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    txt_transitions = main_window.findChild(QTextEdit, "text_transitions")
    assert txt_transitions is not None, "Transitions text widget not found"


def test_timeout_state_does_not_show_loading(qtbot, main_window, mock_ros2_cli):
    """When lifecycle_get_state times out, Current State shows 'Unavailable', not 'Loading...'."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    # Populate the list with one node
    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    # Set up side_effect: nodes list succeeds, state get times out
    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        if "lifecycle get" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        elif "lifecycle list" in cmd_str:
            result = MagicMock(stdout="configure\nactivate", stderr="", returncode=0)
            return result
        result = MagicMock(stdout="", stderr="", returncode=0)
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    # Select the node
    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    # Verify state is "Unavailable", not "Loading..." or "..."
    lbl_state = main_window.findChild(QLabel, "lbl_current_state")
    assert lbl_state is not None
    state_text = lbl_state.text()
    assert state_text == "Unavailable", f"Expected 'Unavailable', got '{state_text}'"
    assert state_text != "Loading...", f"State should not be 'Loading...'"
    assert state_text != "...", f"State should not be '...'"


def test_timeout_transitions_does_not_show_loading(qtbot, main_window, mock_ros2_cli):
    """When lifecycle_list_transitions times out, transitions shows 'Unavailable'."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        if "lifecycle get" in cmd_str:
            result = MagicMock(stdout="active", stderr="", returncode=0)
            return result
        elif "lifecycle list" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        result = MagicMock(stdout="", stderr="", returncode=0)
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    txt_transitions = main_window.findChild(QTextEdit, "text_transitions")
    assert txt_transitions is not None
    trans_text = txt_transitions.toPlainText()
    assert trans_text == "Unavailable", f"Expected 'Unavailable', got '{trans_text}'"
    assert trans_text != "Loading...", f"Transitions should not be 'Loading...'"


def test_timeout_buttons_disabled(qtbot, main_window, mock_ros2_cli):
    """After a timeout, transition buttons remain disabled."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        if "lifecycle get" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        elif "lifecycle list" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        result = MagicMock(stdout="", stderr="", returncode=0)
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    # All transition buttons should be disabled
    for t in ["configure", "activate", "deactivate", "cleanup", "shutdown"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert not btn.isEnabled(), f"btn_transition_{t} should be disabled after timeout"


def test_timeout_shows_error_in_console(qtbot, main_window, mock_ros2_cli):
    """After a timeout, the output console contains a visible timeout message."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        if "lifecycle get" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        elif "lifecycle list" in cmd_str:
            result = MagicMock(stdout="", stderr="", returncode=0)
            return result
        result = MagicMock(stdout="", stderr="", returncode=0)
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    console = main_window.findChild(QTextEdit, "text_output_console")
    assert console is not None
    console_text = console.toPlainText()
    assert "timed out" in console_text.lower() or "timeout" in console_text.lower() or "unavailable" in console_text.lower(), \
        f"Expected timeout message in console, got: {console_text}"


def test_smart_buttons_only_available_enabled(qtbot, main_window, mock_ros2_cli):
    """Only deactivate and shutdown are available → only those 2 buttons enabled."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        result = MagicMock(stdout="", stderr="", returncode=0)
        if "lifecycle get" in cmd_str:
            result.stdout = "active"
        elif "lifecycle list" in cmd_str:
            result.stdout = "- deactivate [4]\n- shutdown [7]"
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    # Only deactivate and shutdown should be enabled
    for t in ["deactivate", "shutdown"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert btn.isEnabled(), f"btn_transition_{t} should be enabled"

    for t in ["configure", "activate", "cleanup"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert not btn.isEnabled(), f"btn_transition_{t} should be disabled"


def test_smart_buttons_only_configure_enabled(qtbot, main_window, mock_ros2_cli):
    """Only configure is available → only Configure enabled."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        result = MagicMock(stdout="", stderr="", returncode=0)
        if "lifecycle get" in cmd_str:
            result.stdout = "unconfigured"
        elif "lifecycle list" in cmd_str:
            result.stdout = "- configure [1]"
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    btn_configure = main_window.findChild(QPushButton, "btn_transition_configure")
    assert btn_configure is not None
    assert btn_configure.isEnabled(), "btn_transition_configure should be enabled"

    for t in ["activate", "deactivate", "cleanup", "shutdown"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert not btn.isEnabled(), f"btn_transition_{t} should be disabled"


def test_smart_buttons_unavailable_disables_all(qtbot, main_window, mock_ros2_cli):
    """When transitions are unavailable (timeout/error), all buttons disabled."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        if "lifecycle get" in cmd_str:
            result = MagicMock(stdout="active", stderr="", returncode=0)
            return result
        elif "lifecycle list" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        result = MagicMock(stdout="", stderr="", returncode=0)
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    for t in ["configure", "activate", "deactivate", "cleanup", "shutdown"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert not btn.isEnabled(), f"btn_transition_{t} should be disabled when transitions unavailable"


def test_smart_buttons_stale_result_ignored(qtbot, main_window, mock_ros2_cli):
    """Stale transition results for a different node do NOT enable buttons."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/node_a\n/node_b"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    # Side effect: node_a has configure; node_b has shutdown
    # We select node_a, then rapidly select node_b before node_a's transitions arrive
    call_count = [0]

    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        result = MagicMock(stdout="", stderr="", returncode=0)
        if "lifecycle get" in cmd_str:
            result.stdout = "active"
        elif "lifecycle list" in cmd_str:
            call_count[0] += 1
            if "/node_a" in cmd_str:
                result.stdout = "- configure [1]"
            elif "/node_b" in cmd_str:
                result.stdout = "- shutdown [7]"
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None

    # Select node_a (will fetch configure transitions)
    node_list.setCurrentRow(0)  # node_a
    qtbot.wait(100)

    # Rapidly switch to node_b before node_a's results arrive.
    # The concurrency guard in _fetch_node_transitions disconnects the stale worker.
    node_list.setCurrentRow(1)  # node_b
    qtbot.wait(500)

    # Only shutdown (node_b's transition) should be enabled.
    # configure from node_a must NOT be enabled.
    btn_configure = main_window.findChild(QPushButton, "btn_transition_configure")
    assert btn_configure is not None
    assert not btn_configure.isEnabled(), (
        "btn_transition_configure should be disabled — stale node_a result ignored"
    )

    btn_shutdown = main_window.findChild(QPushButton, "btn_transition_shutdown")
    assert btn_shutdown is not None
    assert btn_shutdown.isEnabled(), "btn_transition_shutdown should be enabled for node_b"


def test_smart_buttons_enabled_when_state_fails_but_transitions_ok(qtbot, main_window, mock_ros2_cli):
    """State query times out, but transitions succeed → buttons enabled from transitions."""
    nav_btn = main_window.findChild(QPushButton, "btn_lifecycle")
    assert nav_btn is not None
    qtbot.mouseClick(nav_btn, Qt.LeftButton)

    mock_ros2_cli.return_value.stdout = "/test_lifecycle_node"
    mock_ros2_cli.return_value.returncode = 0

    btn_refresh = main_window.findChild(QPushButton, "btn_refresh_lifecycle")
    assert btn_refresh is not None
    qtbot.mouseClick(btn_refresh, Qt.LeftButton)
    qtbot.wait(500)

    # State query fails (timeout), but transitions succeed with deactivate + shutdown
    def side_effect(*args, **kwargs):
        cmd_args = args[0] if args else []
        cmd_str = " ".join(cmd_args)
        if "lifecycle get" in cmd_str:
            raise subprocess.TimeoutExpired(cmd=cmd_args, timeout=5)
        elif "lifecycle list" in cmd_str:
            result = MagicMock(stdout="- deactivate [4]\n- shutdown [7]", stderr="", returncode=0)
            return result
        result = MagicMock(stdout="", stderr="", returncode=0)
        return result

    mock_ros2_cli.side_effect = side_effect
    mock_ros2_cli.return_value = None

    node_list = main_window.findChild(QListWidget, "list_lifecycle_nodes")
    assert node_list is not None
    node_list.setCurrentRow(0)
    qtbot.wait(500)

    # State should show "Unavailable" (get_state timed out)
    lbl_state = main_window.findChild(QLabel, "lbl_current_state")
    assert lbl_state is not None
    assert lbl_state.text() == "Unavailable", f"Expected 'Unavailable', got '{lbl_state.text()}'"

    # Buttons should still be enabled based on transitions (deactivate, shutdown)
    for t in ["deactivate", "shutdown"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert btn.isEnabled(), f"btn_transition_{t} should be enabled (transition available)"

    for t in ["configure", "activate", "cleanup"]:
        btn = main_window.findChild(QPushButton, f"btn_transition_{t}")
        assert btn is not None
        assert not btn.isEnabled(), f"btn_transition_{t} should be disabled (transition not available)"
