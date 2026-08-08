import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget
from unittest.mock import MagicMock

from gui.dialogs import (
    InitWorkspaceDialog,
    CreatePackageDialog,
    CreateNodeDialog,
    NodeProfileDialog,
    center_dialog_on_parent
)
from gui.main_window import HelpDialog
from gui.launch_manager import LaunchBuilderDialog
from gui.theme import ThemeManager


@pytest.fixture
def parent_window(qtbot):
    win = QMainWindow()
    win.setGeometry(100, 100, 800, 600)
    qtbot.addWidget(win)
    win.show()
    return win


def test_center_dialog_on_parent_calculation(parent_window):
    dialog = InitWorkspaceDialog(parent_window)
    dialog.resize(400, 200)
    center_dialog_on_parent(dialog)
    
    geom = parent_window.geometry()
    expected_x = geom.x() + (geom.width() - 400) // 2
    expected_y = geom.y() + (geom.height() - 200) // 2
    
    assert dialog.x() == expected_x
    assert dialog.y() == expected_y


def create_mock_pm():
    pm = MagicMock()
    pm.load_profiles.return_value = [
        {"profile_name": "default", "app_args": "--flag", "ros_args": "-p param:=1", "working_directory": "/tmp"}
    ]
    return pm


@pytest.mark.parametrize("dialog_class, kwargs_factory", [
    (InitWorkspaceDialog, lambda: {}),
    (CreatePackageDialog, lambda: {}),
    (CreateNodeDialog, lambda: {}),
    (NodeProfileDialog, lambda: {"profile_manager": create_mock_pm(), "pkg_name": "test_pkg", "node_name": "test_node"}),
    (HelpDialog, lambda: {"page_data": {"title": "Test Title", "description": "Test Description"}}),
    (LaunchBuilderDialog, lambda: {"packages": [], "workspace_path": "/tmp"}),
])
def test_dialogs_styled_background_and_centering(qapp, qtbot, parent_window, dialog_class, kwargs_factory):
    ThemeManager.apply(qapp, "dark")
    kwargs = kwargs_factory()
    dialog = dialog_class(parent=parent_window, **kwargs)
    qtbot.addWidget(dialog)
    
    # Verify Qt.WA_StyledBackground is True
    assert dialog.testAttribute(Qt.WA_StyledBackground) is True
    
    # Trigger show event to verify centering over parent
    dialog.show()
    qtbot.waitExposed(dialog)
    
    geom = parent_window.geometry()
    expected_x = max(0, geom.x() + (geom.width() - dialog.width()) // 2)
    expected_y = max(0, geom.y() + (geom.height() - dialog.height()) // 2)
    
    assert abs(dialog.x() - expected_x) <= 2
    assert abs(dialog.y() - expected_y) <= 2


def test_dialogs_light_and_dark_theme_compliance(qapp, qtbot, parent_window):
    for theme_name in ["dark", "light"]:
        ThemeManager.apply(qapp, theme_name)
        
        d1 = InitWorkspaceDialog(parent_window)
        d2 = CreatePackageDialog(parent_window)
        d3 = CreateNodeDialog(parent_window)
        d4 = NodeProfileDialog(parent_window, create_mock_pm(), "pkg", "node")
        d5 = HelpDialog({"title": "Help"}, parent_window)
        d6 = LaunchBuilderDialog([], "/tmp", parent_window)
        
        for d in [d1, d2, d3, d4, d5, d6]:
            qtbot.addWidget(d)
            assert d.testAttribute(Qt.WA_StyledBackground) is True
