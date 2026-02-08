"""
Tests for PreferencesService

Tests the thread-safe preferences persistence service
"""

import pytest
import json
import threading
import time
from pathlib import Path
from app.services.preferences import PreferencesService


class TestPreferencesBasic:
    """Basic preferences operations"""

    def test_load_existing_preferences(self, temp_preferences):
        """Test loading preferences from existing file"""
        prefs = PreferencesService(config_path=str(temp_preferences))
        config = prefs.get_serial_config()

        assert config is not None
        assert config["port"] == "/dev/ttyUSB0"
        assert config["baudrate"] == 115200

    def test_save_serial_config(self, temp_preferences):
        """Test saving serial configuration"""
        prefs = PreferencesService(config_path=str(temp_preferences))

        result = prefs.set_serial_config(port="/dev/ttyUSB1", baudrate=57600)

        assert result is True
        config = prefs.get_serial_config()
        assert config["port"] == "/dev/ttyUSB1"
        assert config["baudrate"] == 57600

    def test_save_video_config(self, temp_preferences):
        """Test saving video configuration"""
        prefs = PreferencesService(config_path=str(temp_preferences))

        result = prefs.set_video_config(source="hdmi", codec="mjpeg", width=1920, height=1080)

        assert result is True
        config = prefs.get_video_config()
        assert config["source"] == "hdmi"
        assert config["codec"] == "mjpeg"
        assert config["width"] == 1920

    def test_save_vpn_config(self, temp_preferences):
        """Test saving VPN configuration"""
        prefs = PreferencesService(config_path=str(temp_preferences))

        result = prefs.set_vpn_config(provider="tailscale", auto_connect=True)

        assert result is True
        config = prefs.get_vpn_config()
        assert config["provider"] == "tailscale"
        assert config["auto_connect"] is True


class TestPreferencesPersistence:
    """Test persistence across instances"""

    def test_persistence_across_instances(self, temp_preferences):
        """Test that changes persist when reloading"""
        # First instance - modify
        prefs1 = PreferencesService(config_path=str(temp_preferences))
        prefs1.set_serial_config(port="/dev/ttyUSB2", baudrate=921600)

        # Second instance - should see changes
        prefs2 = PreferencesService(config_path=str(temp_preferences))
        config = prefs2.get_serial_config()

        assert config["port"] == "/dev/ttyUSB2"
        assert config["baudrate"] == 921600

    def test_file_content_matches(self, temp_preferences):
        """Test that file content matches what's saved"""
        prefs = PreferencesService(config_path=str(temp_preferences))
        prefs.set_serial_config(port="/dev/ttyS0", baudrate=115200)

        # Read file directly
        with open(temp_preferences, "r") as f:
            file_data = json.load(f)

        assert file_data["serial"]["port"] == "/dev/ttyS0"
        assert file_data["serial"]["baudrate"] == 115200


class TestPreferencesThreadSafety:
    """Test thread-safe operations with RLock"""

    def test_concurrent_writes(self, temp_preferences):
        """Test concurrent writes don't corrupt data"""
        prefs = PreferencesService(config_path=str(temp_preferences))
        errors = []

        def write_serial(port_num):
            try:
                time.sleep(0.01)  # Small delay to increase concurrency
                prefs.set_serial_config(port=f"/dev/ttyUSB{port_num}", baudrate=115200)
            except Exception as e:
                errors.append(e)

        # Create 10 threads writing concurrently
        threads = [threading.Thread(target=write_serial, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not have any errors (no deadlocks or exceptions)
        assert len(errors) == 0

        # Should have valid config (one of the ports)
        config = prefs.get_serial_config()
        assert config["port"].startswith("/dev/ttyUSB")
        assert config["baudrate"] == 115200

    def test_concurrent_read_write(self, temp_preferences):
        """Test concurrent reads and writes work correctly"""
        prefs = PreferencesService(config_path=str(temp_preferences))
        errors = []
        read_results = []

        def writer():
            try:
                for i in range(5):
                    prefs.set_serial_config(port=f"/dev/ttyUSB{i}", baudrate=115200)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(10):
                    config = prefs.get_serial_config()
                    read_results.append(config)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        # Start writer and multiple readers
        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader) for _ in range(3)]

        writer_thread.start()
        for rt in reader_threads:
            rt.start()

        writer_thread.join()
        for rt in reader_threads:
            rt.join()

        # No errors should occur
        assert len(errors) == 0
        # Should have successful reads
        assert len(read_results) > 0


class TestPreferencesEdgeCases:
    """Test edge cases and error handling"""

    def test_create_new_preferences_file(self, tmp_path):
        """Test creating preferences when file doesn't exist"""
        new_file = tmp_path / "new_prefs.json"
        prefs = PreferencesService(config_path=str(new_file))

        # Should have default structure
        config = prefs.get_serial_config()
        assert config is not None
        assert "port" in config
        assert "baudrate" in config

    def test_partial_config_update(self, temp_preferences):
        """Test updating only some fields preserves others"""
        prefs = PreferencesService(config_path=str(temp_preferences))

        # Initial state
        original_config = prefs.get_video_config()
        original_source = original_config["source"]

        # Update only bitrate
        prefs.set_video_config(bitrate=5000)

        # Check source is preserved
        new_config = prefs.get_video_config()
        assert new_config["source"] == original_source
        assert new_config["bitrate"] == 5000

    def test_invalid_path_handling(self):
        """Test handling of invalid file path"""
        # This should not crash, but handle gracefully
        prefs = PreferencesService(config_path="/invalid/path/prefs.json")

        # Should still return something (in-memory defaults)
        config = prefs.get_serial_config()
        assert config is not None


@pytest.mark.integration
class TestPreferencesIntegration:
    """Integration tests with real file I/O"""

    def test_large_concurrent_operations(self, temp_preferences):
        """Test system under load with many operations"""
        prefs = PreferencesService(config_path=str(temp_preferences))
        operations = 0
        errors = []

        def worker(worker_id):
            nonlocal operations
            try:
                for i in range(20):
                    # Mix of operations
                    if i % 3 == 0:
                        prefs.set_serial_config(port=f"/dev/ttyUSB{worker_id}", baudrate=115200)
                    elif i % 3 == 1:
                        prefs.set_video_config(bitrate=1000 + worker_id * 100)
                    else:
                        prefs.get_serial_config()
                    operations += 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert operations == 100  # 5 threads * 20 operations
