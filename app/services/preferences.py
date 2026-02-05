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
        "/dev/ttyS0",    # Secondary UART
        "/dev/ttyS1",
        "/dev/ttyS2",
    ]
    
    # USB serial ports (check after hardware)
    USB_SERIAL_PATTERNS = [
        "/dev/ttyUSB",   # USB-Serial adapters
        "/dev/ttyACM",   # Arduino/CDC devices
    ]
    
    # Common baudrates for flight controllers
    COMMON_BAUDRATES = [115200, 57600, 921600, 460800, 230400]
    
    def __init__(self):
        self._lock = threading.Lock()
        self._preferences: Dict[str, Any] = self._default_preferences()
        self._config_path = self._get_config_path()
        self._load()
    
    def _get_config_path(self) -> str:
        """Get path to preferences file."""
        # Store in FPVCopilotSky root directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "..", self.PREFERENCES_FILE)
    
    def _default_preferences(self) -> Dict[str, Any]:
        """Return default preferences structure."""
        return {
            "serial": {
                "port": "",
                "baudrate": 115200,
                "auto_connect": True,
                "last_successful": False
            },
            "router": {
                "outputs": [
                    {
                        "id": "default-tcp",
                        "type": "tcp_server",
                        "host": "0.0.0.0",
                        "port": 5760,
                        "name": "Mission Planner",
                        "enabled": True,
                        "auto_start": True
                    }
                ]
            },
            "video": {
                "device": "/dev/video0",
                "width": 960,
                "height": 720,
                "framerate": 30,
                "codec": "mjpeg",
                "quality": 85,
                "h264_bitrate": 2000
            },
            "streaming": {
                "udp_host": "192.168.1.136",
                "udp_port": 5600,
                "enabled": True,
                "auto_start": False
            },
            "ui": {
                "language": "es",
                "theme": "dark"
            },
            "system": {
                "version": "1.0.0",
                "first_run": True
            }
        }
    
    def _load(self):
        """Load preferences from file."""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as f:
                    loaded = json.load(f)
                
                # Merge with defaults (to add any new fields)
                defaults = self._default_preferences()
                self._deep_merge(defaults, loaded)
                self._preferences = defaults
                
                print(f"✅ Loaded preferences from {self._config_path}")
            else:
                print(f"📝 Using default preferences (no file found)")
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
        """Save preferences to file."""
        try:
            with open(self._config_path, 'w') as f:
                json.dump(self._preferences, f, indent=2)
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
                last_successful=cfg.get("last_successful", False)
            )
    
    def set_serial_config(self, port: str, baudrate: int, successful: bool = False):
        """Update serial configuration."""
        with self._lock:
            self._preferences["serial"]["port"] = port
            self._preferences["serial"]["baudrate"] = baudrate
            self._preferences["serial"]["last_successful"] = successful
            if successful:
                self._preferences["system"]["first_run"] = False
            self._save()
    
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
        """Get video configuration."""
        with self._lock:
            return self._preferences.get("video", {})
    
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
        """Set streaming configuration."""
        with self._lock:
            if "streaming" not in self._preferences:
                self._preferences["streaming"] = {}
            self._preferences["streaming"].update(config)
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


# Singleton instance
_preferences_service: Optional[PreferencesService] = None

def get_preferences() -> PreferencesService:
    """Get the singleton preferences service instance."""
    global _preferences_service
    if _preferences_service is None:
        _preferences_service = PreferencesService()
    return _preferences_service
