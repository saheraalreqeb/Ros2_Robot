import pytest

def pytest_collection_modifyitems(config, items):
    for item in items:
        # If the test is inside the e2e folder, add the 'gui' marker automatically
        if "tests/e2e" in str(item.fspath).replace('\\', '/'):
            item.add_marker(pytest.mark.gui)
