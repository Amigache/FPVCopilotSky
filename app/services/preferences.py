"""
Preferences Service - Unified persistence for all configuration
Stores serial connection, router outputs, and user preferences
"""

import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import threading


@dataclass
class SerialConfig:
    """Serial port configuration."""

    port: str = ""
    baudrate: int = 115200
    auto_connect: bool = True
    last_successful: bool = False


@dataclass
class RouterOutput:
    """Router output configuration."""

    id: str = ""
    type: str = "tcp_server"
    host: str = "0.0.0.0"
    port: int = 5760
    name: str = ""
    enabled: bool = True
    auto_start: bool = True


class PreferencesService:
    """
    Unified preferences and configuration persistence.
    Single source of truth for all configuration.
    """

    PREFERENCES_FILE = "preferences.json"

    # Radxa Zero hardware serial ports (priority order for auto-detection)
    HARDWARE_SERIAL_PORTS = [
        "/dev/ttyAML0",  # Main UART on GPIO (pins 8/10)
        "/dev/ttyS0",  # Secondary UART
        "/dev/ttyS1",
        "/dev/ttyS2",
    ]

    # USB serial ports (check after hardware)
    USB_SERIAL_PATTERNS = [
        "/dev/ttyUSB",  # USB-Serial adapters
        "/dev/ttyACM",  # Arduino/CDC devices
    ]

    # Common baudrates for flight controllers
    COMMON_BAUDRATES = [115200, 57600, 921600, 460800, 230400]

    def __init__(self, config_path: str = None):
        self._lock = threading.RLock()  # RLock allows re-entrant locking from same thread
        self._preferences: Dict[str, Any] = self._default_preferences()
        self._config_path = config_path if config_path else self._get_config_path()
        self._load()

    def _get_config_path(self) -> str:
        """Get path to preferences file."""
        # Store in FPVCopilotSky root directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "..", self.PREFERENCES_FILE)

    def _default_preferences(self) -> Dict[str, Any]:
        """Return default preferences structure."""
        return {
            "serial": {"port": "", "baudrate": 115200, "auto_connect": True, "last_successful": False},
            "router": {"outputs": []},  # No outputs by default, user creates them
            "video": {
                "device": "",  # Will be auto-detected when user saves first time
                "device_name": "",  # Camera card name (e.g. "Brio 100") for stable identification
                "device_bus_info": "",  # USB bus info for disambiguation
                "width": 960,
                "height": 720,
                "framerate": 30,
                "codec": "mjpeg",
                "quality": 85,
                "h264_bitrate": 2000,
            },
            "streaming": {
                "udp_host": "",  # No default IP, user must configure
                "udp_port": 5600,
                "enabled": False,  # Not enabled by default
                "auto_start": False,
            },
            "vpn": {
                "provider": "",  # No provider by default (empty = none, "tailscale", "zerotier", "wireguard")
                "enabled": False,  # VPN not enabled by default
                "auto_connect": False,  # Don't auto-connect on startup
                "provider_settings": {},  # Provider-specific settings (e.g., exit_node, etc.)
            },
            "ui": {"language": "es", "theme": "dark"},
            "system": {"version": "1.0.0", "first_run": True},
        }

    def _load(self):
        """Load preferences from file."""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r") as f:
                    loaded = json.load(f)

                # Merge with defaults (to add any new fields)
                defaults = self._default_preferences()
                self._deep_merge(defaults, loaded)
                self._preferences = defaults

                print(f"✅ Loaded preferences from {self._config_path}")
            else:
                # First run - create preferences file with defaults
                print(f"📝 First run detected - creating preferences file")
                self._preferences = self._default_preferences()
                self._save()
                print(f"✅ Created default preferences at {self._config_path}")
        except Exception as e:
            print(f"⚠️ Failed to load preferences: {e}")
            self._preferences = self._default_preferences()

    def _deep_merge(self, base: dict, override: dict):
        """Deep merge override into base (modifies base in place)."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _save(self):
        """Save preferences to file with synchronization."""
        try:
            with self._lock:
                with open(self._config_path, "w") as f:
                    json.dump(self._preferences, f, indent=2)
                    # Force OS to write to disk while file is still open
                    f.flush()
                    import os

                    os.fsync(f.fileno())
        except Exception as e:
            print(f"⚠️ Failed to save preferences: {e}")

    # ==================== Serial Configuration ====================

    def get_serial_config(self) -> SerialConfig:
        """Get serial port configuration."""
        with self._lock:
            cfg = self._preferences.get("serial", {})
            return SerialConfig(
                port=cfg.get("port", ""),
                baudrate=cfg.get("baudrate", 115200),
                auto_connect=cfg.get("auto_connect", True),
                last_successful=cfg.get("last_successful", False),
            )

    def set_serial_config(self, port: str, baudrate: int, successful: bool = False):
        """Update serial configuration with verification."""
        try:
            with self._lock:
                self._preferences["serial"]["port"] = port
                self._preferences["serial"]["baudrate"] = baudrate
                self._preferences["serial"]["last_successful"] = successful
                if successful:
                    self._preferences["system"]["first_run"] = False
                self._save()

                # Verify the save was successful
                saved_config = self._preferences.get("serial", {})
                if (
                    saved_config.get("port") == port
                    and saved_config.get("baudrate") == baudrate
                    and saved_config.get("last_successful") == successful
                ):
                    print(f"✅ Serial preferences saved: {port} @ {baudrate} baud (successful={successful})")
                else:
                    print(f"⚠️ Serial preferences save verification failed")
        except Exception as e:
            print(f"⚠️ Failed to save serial config: {e}")

    def set_serial_auto_connect(self, enabled: bool):
        """Enable/disable auto-connect."""
        with self._lock:
            self._preferences["serial"]["auto_connect"] = enabled
            self._save()

    # ==================== Router Configuration ====================

    def get_router_outputs(self) -> List[Dict[str, Any]]:
        """Get router output configurations."""
        with self._lock:
            return self._preferences.get("router", {}).get("outputs", [])

    def set_router_outputs(self, outputs: List[Dict[str, Any]]):
        """Set router output configurations."""
        with self._lock:
            self._preferences["router"]["outputs"] = outputs
            self._save()

    def add_router_output(self, output: Dict[str, Any]):
        """Add a router output."""
        with self._lock:
            outputs = self._preferences.get("router", {}).get("outputs", [])
            outputs.append(output)
            self._preferences["router"]["outputs"] = outputs
            self._save()

    def remove_router_output(self, output_id: str):
        """Remove a router output by ID."""
        with self._lock:
            outputs = self._preferences.get("router", {}).get("outputs", [])
            outputs = [o for o in outputs if o.get("id") != output_id]
            self._preferences["router"]["outputs"] = outputs
            self._save()

    # ==================== UI Preferences ====================

    def get_ui_preferences(self) -> Dict[str, Any]:
        """Get UI preferences."""
        with self._lock:
            return self._preferences.get("ui", {})

    def set_ui_preference(self, key: str, value: Any):
        """Set a UI preference."""
        with self._lock:
            if "ui" not in self._preferences:
                self._preferences["ui"] = {}
            self._preferences["ui"][key] = value
            self._save()

    # ==================== Video Configuration ====================

    def get_video_config(self) -> Dict[str, Any]:
        """Get video configuration with smart device matching.

        If the saved device path doesn't exist or doesn't match the saved camera name,
        attempts to find the correct device by matching device_name and bus_info.
        This handles device path changes between reboots (e.g. /dev/video1 → /dev/video0).
        """
        with self._lock:
            config = self._preferences.get("video", {})
            device = config.get("device", "")
            saved_name = config.get("device_name", "")
            saved_bus = config.get("device_bus_info", "")

            # If we have a saved camera identity, use it for smart matching
            if saved_name:
                from .video_config import get_device_identity, find_device_by_identity

                needs_rematch = False

                if not device or not os.path.exists(device):
                    # Device path doesn't exist at all
                    needs_rematch = True
                else:
                    # Device path exists - verify it's the same camera
                    current_identity = get_device_identity(device)
                    if not current_identity or current_identity.get("name") != saved_name:
                        # Device path exists but is a different camera or not a capture device
                        needs_rematch = True

                if needs_rematch:
                    # Find the camera by its name/bus_info
                    new_device = find_device_by_identity(saved_name, saved_bus)
                    if new_device:
                        print(f"🔄 Camera '{saved_name}' moved: {device} → {new_device}")
                        config["device"] = new_device
                        # Persist the corrected device path
                        self._preferences["video"]["device"] = new_device
                        self._save()
                    else:
                        print(f"⚠️ Camera '{saved_name}' not found on any /dev/video* device")
                        # Fallback: find any capture device
                        self._fallback_detect_device(config, device)
            elif device and not os.path.exists(device):
                # Legacy: no saved name, device doesn't exist - basic fallback
                self._fallback_detect_device(config, device)
            elif not device:
                # No device configured at all - auto-detect
                self._fallback_detect_device(config, device)

            return config

    def _fallback_detect_device(self, config: Dict, old_device: str):
        """Fallback device detection when smart matching isn't possible."""
        import glob
        import subprocess

        devices = sorted(glob.glob("/dev/video*"))
        if devices:
            for dev in devices:
                try:
                    result = subprocess.run(
                        ["v4l2-ctl", "--device", dev, "--info"], capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0 and "video capture" in result.stdout.lower():
                        config["device"] = dev
                        if old_device:
                            print(f"⚠️ Video device {old_device} not found, using {dev}")
                        else:
                            print(f"ℹ️ Auto-detected video device: {dev}")
                        break
                except Exception:
                    continue
            else:
                if old_device:
                    print(f"⚠️ Video device {old_device} not found and no alternative detected")
                else:
                    print(f"ℹ️ No video capture devices detected")
        else:
            if old_device:
                print(f"⚠️ Video device {old_device} not found, no /dev/video* devices available")
            else:
                print(f"ℹ️ No video devices detected")

    def set_video_config(self, config: Dict[str, Any]):
        """Set video configuration."""
        with self._lock:
            if "video" not in self._preferences:
                self._preferences["video"] = {}
            self._preferences["video"].update(config)
            self._save()

    # ==================== Streaming Configuration ====================

    def get_streaming_config(self) -> Dict[str, Any]:
        """Get streaming configuration."""
        with self._lock:
            return self._preferences.get("streaming", {})

    def set_streaming_config(self, config: Dict[str, Any]):
        """Set streaming configuration with verification."""
        try:
            with self._lock:
                if "streaming" not in self._preferences:
                    self._preferences["streaming"] = {}
                self._preferences["streaming"].update(config)
                self._save()

                # Verify the save was successful
                saved = self._preferences.get("streaming", {})
                enabled = config.get("enabled", False)
                auto_start = config.get("auto_start", False)

                if saved.get("enabled") == enabled and saved.get("auto_start") == auto_start:
                    print(f"✅ Streaming preferences saved: enabled={enabled}, auto_start={auto_start}")
                else:
                    print(f"⚠️ Streaming preferences save verification failed")
        except Exception as e:
            print(f"⚠️ Failed to save streaming config: {e}")

    # ==================== VPN Configuration ====================

    def get_vpn_config(self) -> Dict[str, Any]:
        """Get VPN configuration."""
        with self._lock:
            return self._preferences.get("vpn", {})

    def set_vpn_config(self, config: Dict[str, Any]):
        """Set VPN configuration with verification."""
        try:
            with self._lock:
                if "vpn" not in self._preferences:
                    self._preferences["vpn"] = {}
                self._preferences["vpn"].update(config)
                self._save()

                # Verify the save was successful
                saved = self._preferences.get("vpn", {})
                provider = config.get("provider", "")
                enabled = config.get("enabled", False)
                auto_connect = config.get("auto_connect", False)

                if (
                    saved.get("provider") == provider
                    and saved.get("enabled") == enabled
                    and saved.get("auto_connect") == auto_connect
                ):
                    print(
                        f"✅ VPN preferences saved: provider={provider}, enabled={enabled}, auto_connect={auto_connect}"
                    )
                else:
                    print(f"⚠️ VPN preferences save verification failed")
        except Exception as e:
            print(f"⚠️ Failed to save VPN config: {e}")

    def set_vpn_provider(self, provider: str):
        """Set VPN provider (e.g., 'tailscale', 'zerotier', 'wireguard', or '' for none)."""
        with self._lock:
            if "vpn" not in self._preferences:
                self._preferences["vpn"] = {}
            self._preferences["vpn"]["provider"] = provider
            self._save()

    def set_vpn_enabled(self, enabled: bool):
        """Enable or disable VPN."""
        with self._lock:
            if "vpn" not in self._preferences:
                self._preferences["vpn"] = {}
            self._preferences["vpn"]["enabled"] = enabled
            self._save()

    def set_vpn_auto_connect(self, auto_connect: bool):
        """Enable or disable VPN auto-connect on startup."""
        with self._lock:
            if "vpn" not in self._preferences:
                self._preferences["vpn"] = {}
            self._preferences["vpn"]["auto_connect"] = auto_connect
            self._save()

    # ==================== Auto-Detection ====================

    def get_serial_ports_to_scan(self) -> List[str]:
        """Get list of serial ports to scan for auto-detection."""
        import glob

        ports = []

        # First: saved port if available
        saved_port = self._preferences.get("serial", {}).get("port", "")
        if saved_port and os.path.exists(saved_port):
            ports.append(saved_port)

        # Second: hardware serial ports
        for port in self.HARDWARE_SERIAL_PORTS:
            if os.path.exists(port) and port not in ports:
                ports.append(port)

        # Third: USB serial devices
        for pattern in self.USB_SERIAL_PATTERNS:
            for port in sorted(glob.glob(f"{pattern}*")):
                if port not in ports:
                    ports.append(port)

        return ports

    def get_baudrates_to_try(self) -> List[int]:
        """Get list of baudrates to try for auto-detection."""
        baudrates = []

        # First: saved baudrate
        saved_baudrate = self._preferences.get("serial", {}).get("baudrate", 115200)
        if saved_baudrate:
            baudrates.append(saved_baudrate)

        # Then: common baudrates
        for br in self.COMMON_BAUDRATES:
            if br not in baudrates:
                baudrates.append(br)

        return baudrates

    # ==================== System Info ====================

    def is_first_run(self) -> bool:
        """Check if this is the first run."""
        with self._lock:
            return self._preferences.get("system", {}).get("first_run", True)

    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all preferences (for debugging/export)."""
        with self._lock:
            return self._preferences.copy()

    def reset_preferences(self) -> bool:
        """Reset all preferences to defaults and save."""
        try:
            with self._lock:
                # Keep a backup
                backup_path = self._config_path + ".backup"
                if os.path.exists(self._config_path):
                    import shutil

                    shutil.copy2(self._config_path, backup_path)
                    print(f"📦 Backed up preferences to {backup_path}")

                # Reset to defaults
                self._preferences = self._default_preferences()
                self._save()
                print(f"✅ Preferences reset to defaults")
                return True
        except Exception as e:
            print(f"⚠️ Failed to reset preferences: {e}")
            return False


# Singleton instance
_preferences_service: Optional[PreferencesService] = None


def get_preferences() -> PreferencesService:
    """Get the singleton preferences service instance."""
    global _preferences_service
    if _preferences_service is None:
        _preferences_service = PreferencesService()
    return _preferences_service
