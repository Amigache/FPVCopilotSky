"""
Video Configuration for FPV Streaming
Supports MJPEG and H.264 encoding with UDP output
"""

from dataclasses import dataclass
from typing import Optional, Dict
import ipaddress
import subprocess
import glob


def get_device_identity(device: str) -> Optional[Dict[str, str]]:
    """
    Get identifying information for a video device (name, driver, bus_info).
    Returns None if the device is not a valid capture device.
    """
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--device", device, "--info"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None

        info = {"device": device}
        is_capture = False

        for line in result.stdout.split("\n"):
            if "Card type" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    info["name"] = parts[1].strip()
            elif "Driver name" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    info["driver"] = parts[1].strip()
            elif "Bus info" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    info["bus_info"] = parts[1].strip()
            elif "Video Capture" in line:
                is_capture = True

        if not is_capture:
            return None

        return info
    except Exception:
        return None


def find_device_by_identity(name: str, bus_info: str = "") -> Optional[str]:
    """
    Find a video device path that matches the given camera name (and optionally bus_info).
    Scans all /dev/video* devices and returns the first match.
    Priority: match both name+bus_info > match name only.
    """
    devices = sorted(glob.glob("/dev/video*"))
    name_match = None

    for device in devices:
        identity = get_device_identity(device)
        if not identity:
            continue
        dev_name = identity.get("name", "")
        dev_bus = identity.get("bus_info", "")

        if dev_name == name:
            if bus_info and dev_bus == bus_info:
                # Exact match on name + bus_info
                return device
            if name_match is None:
                name_match = device

    return name_match


@dataclass
class VideoConfig:
    """Video capture and encoding configuration"""

    # Camera settings - no auto-detection, use provider system instead
    device: str = "/dev/video0"  # Default device, will be set by provider system
    width: int = 960
    height: int = 720
    framerate: int = 30

    # Codec selection: 'mjpeg' or 'h264'
    codec: str = "mjpeg"

    # MJPEG encoding parameters (ultra-low latency)
    quality: int = 85  # JPEG quality (0-100)

    # H.264 encoding parameters (low latency)
    h264_bitrate: int = 2000  # kbps
    h264_preset: str = "ultrafast"  # ultrafast, superfast, veryfast
    h264_tune: str = "zerolatency"
    gop_size: int = 2  # OpenH264: keyframe interval in frames (for low latency)

    # Buffer tuning
    max_latency_ms: int = 50

    def __post_init__(self):
        """Clamp all values to safe ranges."""
        self.width = max(1, min(7680, int(self.width)))
        self.height = max(1, min(4320, int(self.height)))
        self.framerate = max(1, min(120, int(self.framerate)))
        self.quality = max(1, min(100, int(self.quality)))
        self.h264_bitrate = max(100, min(50000, int(self.h264_bitrate)))
        self.gop_size = max(1, min(300, int(self.gop_size)))
        if self.codec not in ("mjpeg", "h264", "h264_openh264", "h264_hardware", "h264_v4l2"):
            self.codec = "mjpeg"


@dataclass
class StreamingConfig:
    """Network streaming configuration with multiple modes"""

    # Streaming mode: 'udp', 'rtsp', 'multicast', 'webrtc'
    mode: str = "udp"

    # Mode 1: Direct UDP (unicast) - Current default
    # Best for: Single client, minimum latency
    udp_host: str = "192.168.1.136"
    udp_port: int = 5600

    # Mode 2: RTSP Server (multi-client via GStreamer RTSP Server)
    # Best for: Multiple clients, VLC, Mission Planner, recording
    rtsp_enabled: bool = False
    rtsp_url: str = "rtsp://localhost:8554/fpv"
    rtsp_transport: str = "tcp"  # 'tcp' or 'udp' (udp for lower latency)

    # Mode 3: UDP Multicast (multiple clients on same LAN)
    # Best for: Multiple clients on local network, low latency
    multicast_group: str = "239.1.1.1"  # Multicast group address (239.0.0.0 - 239.255.255.255)
    multicast_port: int = 5600
    multicast_ttl: int = 1  # Time-to-live (1 = local network only)

    # Enable/disable streaming
    enabled: bool = True
    auto_start: bool = True

    def __post_init__(self):
        """Clamp and validate all values to safe ranges."""
        if self.mode not in ("udp", "multicast", "rtsp", "webrtc"):
            self.mode = "udp"
        self.udp_port = max(1024, min(65535, int(self.udp_port)))
        self.multicast_port = max(1024, min(65535, int(self.multicast_port)))
        self.multicast_ttl = max(1, min(255, int(self.multicast_ttl)))
        if self.rtsp_transport not in ("tcp", "udp"):
            self.rtsp_transport = "tcp"
        # Validate multicast group is in 224.0.0.0 – 239.255.255.255
        try:
            addr = ipaddress.IPv4Address(self.multicast_group)
            if not addr.is_multicast:
                self.multicast_group = "239.1.1.1"
        except (ipaddress.AddressValueError, ValueError):
            self.multicast_group = "239.1.1.1"
        # Validate UDP host is valid IPv4
        try:
            ipaddress.IPv4Address(self.udp_host)
        except (ipaddress.AddressValueError, ValueError):
            self.udp_host = "127.0.0.1"
        # Validate RTSP URL format
        if self.rtsp_url and not self.rtsp_url.startswith("rtsp://"):
            self.rtsp_url = "rtsp://localhost:8554/fpv"


# Default configurations
DEFAULT_VIDEO_CONFIG = VideoConfig()
DEFAULT_STREAMING_CONFIG = StreamingConfig()
