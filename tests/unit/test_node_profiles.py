import os
import json
import pytest
from core.node_profiles import NodeProfileManager

def test_node_profile_manager_lifecycle(tmp_path):
    workspace_path = str(tmp_path)
    manager = NodeProfileManager(workspace_path)
    
    profiles_dir = os.path.join(workspace_path, ".ros2_robot")
    profiles_file = os.path.join(profiles_dir, "node_profiles.json")
    
    assert os.path.exists(profiles_dir)
    assert os.path.exists(profiles_file)
    
    # Save a profile
    data = {
        "app_args": "--my-arg",
        "ros_args": "-p my_param:=1",
        "working_directory": "/tmp"
    }
    manager.save_profile("my_pkg", "my_node", "test_prof", data)
    
    # Load it
    profs = manager.load_profiles("my_pkg", "my_node")
    assert len(profs) == 1
    assert profs[0]["profile_name"] == "test_prof"
    assert profs[0]["app_args"] == "--my-arg"
    
    # Load specific
    prof = manager.load_profile("my_pkg", "my_node", "test_prof")
    assert prof["ros_args"] == "-p my_param:=1"
    
    # Load non-existent
    assert manager.load_profile("my_pkg", "my_node", "none") is None
    
    # Delete it
    manager.delete_profile("my_pkg", "my_node", "test_prof")
    profs = manager.load_profiles("my_pkg", "my_node")
    assert len(profs) == 0
