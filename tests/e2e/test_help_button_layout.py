import pytest
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtWidgets import QPushButton
from gui.main_window import MainWindow

def test_help_buttons_existence_and_positioning(main_window, qtbot):
    # Ensure pages are instantiated
    for page_id in range(14):  # Pages 0 to 13 (all except Settings 14)
        main_window._instantiate_page(page_id)
        
    # Check that help buttons are created and behave correctly
    for page_id in range(14):
        page = main_window.content_stack.widget(page_id)
        assert page is not None, f"Page {page_id} not loaded"
        
        # Help button should be a direct child of the page
        help_btn = page.findChild(QPushButton, f"help_btn_{page_id}")
        assert help_btn is not None, f"Help button not found for page {page_id}"
        assert help_btn.parent() == page, f"Help button for page {page_id} is not a direct child of the page"
        
        # Resize the main window to a specific size
        main_window.resize(800, 600)
        qtbot.waitExposed(main_window)
        
        # Verify button position relative to the page's actual width after main window resize
        actual_w = page.width()
        expected_x = actual_w - 24 - 16
        expected_y = 12
        assert help_btn.x() == expected_x, f"Page {page_id} (w={actual_w}): help button x ({help_btn.x()}) is not {expected_x}"
        assert help_btn.y() == expected_y, f"Page {page_id}: help button y ({help_btn.y()}) is not {expected_y}"
        
        # Resize to a different size and check position update
        main_window.resize(1024, 768)
        qtbot.waitExposed(main_window)
        
        actual_w_new = page.width()
        expected_x_new = actual_w_new - 24 - 16
        assert help_btn.x() == expected_x_new, f"Page {page_id} (w={actual_w_new}): help button x ({help_btn.x()}) after resize is not {expected_x_new}"
        assert help_btn.y() == expected_y, f"Page {page_id}: help button y ({help_btn.y()}) after resize is not {expected_y}"

def test_no_help_button_on_settings_page(main_window):
    main_window._instantiate_page(14)
    settings_page = main_window.content_stack.widget(14)
    help_btn = settings_page.findChild(QPushButton, "help_btn_14")
    assert help_btn is None, "Settings page (14) should not have a help button"
