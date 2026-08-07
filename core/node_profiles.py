import os
import json

class NodeProfileManager:
    """Stores per-node run configurations as JSON in the workspace."""
    
    def __init__(self, workspace_path: str):
        self.profiles_dir = os.path.join(workspace_path, ".ros2_robot")
        self.profiles_file = os.path.join(self.profiles_dir, "node_profiles.json")
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir, exist_ok=True)
        if not os.path.exists(self.profiles_file):
            with open(self.profiles_file, "w") as f:
                json.dump({}, f)

    def _read_profiles(self) -> dict:
        self._ensure_file_exists()
        try:
            with open(self.profiles_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _write_profiles(self, data: dict):
        self._ensure_file_exists()
        with open(self.profiles_file, "w") as f:
            json.dump(data, f, indent=4)

    def save_profile(self, pkg: str, node: str, profile_name: str, data: dict):
        profiles = self._read_profiles()
        key = f"{pkg}/{node}"
        if key not in profiles:
            profiles[key] = {}
        data["profile_name"] = profile_name
        profiles[key][profile_name] = data
        self._write_profiles(profiles)

    def load_profiles(self, pkg: str, node: str) -> list[dict]:
        profiles = self._read_profiles()
        key = f"{pkg}/{node}"
        if key in profiles:
            return list(profiles[key].values())
        return []

    def load_profile(self, pkg: str, node: str, profile_name: str) -> dict:
        profiles = self._read_profiles()
        key = f"{pkg}/{node}"
        if key in profiles and profile_name in profiles[key]:
            return profiles[key][profile_name]
        return None

    def delete_profile(self, pkg: str, node: str, profile_name: str):
        profiles = self._read_profiles()
        key = f"{pkg}/{node}"
        if key in profiles and profile_name in profiles[key]:
            del profiles[key][profile_name]
            if not profiles[key]:
                del profiles[key]
            self._write_profiles(profiles)
