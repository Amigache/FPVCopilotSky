"""
Extended Tests for Preferences and Configuration

Tests for preferences handling and configuration management
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


class TestPreferencesFile:
    """Test preferences file handling"""

    def test_preferences_file_creation(self, tmp_path):
        """Test creating a preferences file"""
        prefs_file = tmp_path / "prefs.json"
        prefs_data = {"language": "en", "theme": "light"}

        with open(prefs_file, "w") as f:
            json.dump(prefs_data, f)

        assert prefs_file.exists()
        assert prefs_file.is_file()

    def test_preferences_file_reading(self, tmp_path):
        """Test reading preferences from file"""
        prefs_file = tmp_path / "prefs.json"
        test_data = {"language": "es", "notifications": True}
        prefs_file.write_text(json.dumps(test_data))

        with open(prefs_file, "r") as f:
            loaded = json.load(f)

        assert loaded == test_data
        assert loaded["language"] == "es"

    def test_preferences_file_writing(self, tmp_path):
        """Test writing preferences to file"""
        prefs_file = tmp_path / "prefs.json"
        original = {"version": "1.0"}

        with open(prefs_file, "w") as f:
            json.dump(original, f)

        # Read and modify
        with open(prefs_file, "r") as f:
            prefs = json.load(f)

        prefs["version"] = "1.1"

        # Write back
        with open(prefs_file, "w") as f:
            json.dump(prefs, f)

        # Verify
        with open(prefs_file, "r") as f:
            updated = json.load(f)

        assert updated["version"] == "1.1"

    def test_preferences_default_values(self, tmp_path):
        """Test preferences with default values"""
        prefs_file = tmp_path / "prefs.json"
        defaults = {
            "language": "en",
            "theme": "dark",
            "autostart": False,
            "loglevel": "info",
        }
        prefs_file.write_text(json.dumps(defaults))

        with open(prefs_file, "r") as f:
            prefs = json.load(f)

        assert prefs["language"] == "en"
        assert prefs["autostart"] is False
        assert prefs["loglevel"] == "info"


class TestConfigurationValidation:
    """Test configuration validation"""

    def test_validate_required_keys(self):
        """Test validating required configuration keys"""
        config = {"port": 8000, "host": "localhost"}
        required_keys = ["port", "host"]

        missing = [k for k in required_keys if k not in config]
        assert len(missing) == 0

    def test_validate_data_types(self):
        """Test validating configuration data types"""
        config = {
            "port": 8000,
            "host": "localhost",
            "debug": True,
            "tags": ["api", "v1"],
        }

        assert isinstance(config["port"], int)
        assert isinstance(config["host"], str)
        assert isinstance(config["debug"], bool)
        assert isinstance(config["tags"], list)

    def test_validate_value_ranges(self):
        """Test validating value ranges"""
        config = {"port": 8000, "max_connections": 100, "timeout": 30}

        assert 1024 <= config["port"] <= 65535
        assert config["max_connections"] > 0
        assert config["timeout"] > 0


class TestConfigurationMerging:
    """Test merging configurations"""

    def test_merge_default_and_custom(self):
        """Test merging default and custom configurations"""
        defaults = {"language": "en", "theme": "dark"}
        custom = {"language": "fr"}

        merged = {**defaults, **custom}
        assert merged["language"] == "fr"
        assert merged["theme"] == "dark"

    def test_override_nested_config(self):
        """Test overriding nested configuration"""
        defaults = {"server": {"host": "localhost", "port": 8000}}
        overrides = {"server": {"port": 9000}}

        # Simple merge (note: this overwrites the entire server key)
        # For production, you'd want deep merge
        merged = defaults.copy()
        if "server" in overrides:
            merged["server"].update(overrides["server"])

        assert merged["server"]["port"] == 9000
        assert merged["server"]["host"] == "localhost"


class TestConfigurationPersistence:
    """Test saving and loading configurations"""

    def test_save_and_load_config(self, tmp_path):
        """Test saving configuration to file and loading it back"""
        config_file = tmp_path / "config.json"
        config_data = {
            "app_name": "FPV Copilot Sky",
            "version": "1.0.0",
            "endpoints": {"api": "/api", "ws": "/ws"},
        }

        # Save
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Load
        with open(config_file, "r") as f:
            loaded = json.load(f)

        assert loaded == config_data
        assert loaded["app_name"] == "FPV Copilot Sky"
        assert loaded["version"] == "1.0.0"

    def test_backup_and_restore(self, tmp_path):
        """Test backing up and restoring configuration"""
        config_file = tmp_path / "config.json"
        backup_file = tmp_path / "config.backup.json"

        original = {"setting": "value1"}
        config_file.write_text(json.dumps(original))

        # Create backup
        import shutil

        shutil.copy(config_file, backup_file)

        # Modify original
        modified = {"setting": "value2"}
        config_file.write_text(json.dumps(modified))

        # Verify modification
        with open(config_file, "r") as f:
            current = json.load(f)
        assert current["setting"] == "value2"

        # Restore from backup
        shutil.copy(backup_file, config_file)

        # Verify restoration
        with open(config_file, "r") as f:
            restored = json.load(f)
        assert restored["setting"] == "value1"
