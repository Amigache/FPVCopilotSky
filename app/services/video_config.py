"""
Video Configuration for FPV Streaming
Supports MJPEG and H.264 encoding with UDP output
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import subprocess
import glob
import os
import re


def get_device_identity(device: str) -> Optional[Dict[str, str]]:
    """
    Get identifying information for a video device (name, driver, bus_info).
    Returns None if the device is not a valid capture device.
    """
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--device', device, '--info'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode != 0:
            return None

        info = {"device": device}
        is_capture = False

        for line in result.stdout.split('\n'):
            if 'Card type' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    info["name"] = parts[1].strip()
            elif 'Driver name' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    info["driver"] = parts[1].strip()
            elif 'Bus info' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    info["bus_info"] = parts[1].strip()
            elif 'Video Capture' in line:
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
    devices = sorted(glob.glob('/dev/video*'))
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


def auto_detect_camera() -> str:
    """
    Auto-detect USB camera device.
    Looks for uvcvideo devices and returns the first one found.
    Falls back to /dev/video0 if nothing found.
    """
    try:
        # Get all video devices
        devices = glob.glob('/dev/video*')
        
        for device in sorted(devices):
            try:
                # Check if it's a USB camera (uvcvideo driver)
                result = subprocess.run(
                    ['v4l2-ctl', '--device', device, '--info'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    output = result.stdout.lower()
                    # Look for uvcvideo driver (USB cameras) and video capture capability
                    if 'uvcvideo' in output and 'video capture' in output:
                        return device
            except Exception:
                continue
        
        # If no uvcvideo found, return first available device
        if devices:
            return devices[0]
        
    except Exception:
        pass
    
    # Fallback
    return "/dev/video0"


def get_device_resolutions(device: str) -> Dict:
    """
    Get supported resolutions, fps, and device info for a video device using v4l2-ctl.
    Returns dict with name, type, resolutions list, and resolutions_fps mapping.
    """
    try:
        # Get device info
        info_result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        device_name = device
        device_type = "Dispositivo de captura"
        driver = "unknown"
        bus_info = ""
        is_capture = False
        
        for line in info_result.stdout.split('\n'):
            if 'Card type' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    device_name = parts[1].strip()
                    if 'camera' in device_name.lower() or 'webcam' in device_name.lower():
                        device_type = "Cámara"
            elif 'Driver name' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    driver = parts[1].strip()
            elif 'Bus info' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    bus_info = parts[1].strip()
            elif 'Video Capture' in line:
                is_capture = True
        
        # If not a capture device, skip
        if not is_capture:
            return None
        
        # Get formats and resolutions with FPS
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--list-formats-ext"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        resolutions_fps = {}  # {resolution: [fps list]}
        current_format = None
        current_resolution = None
        
        for line in result.stdout.split('\n'):
            # Parse format line
            if "'" in line and "'" in line:
                parts = line.split("'")
                if len(parts) >= 2:
                    current_format = parts[1]
            
            # Parse resolution line
            if 'Size: Discrete' in line and current_format:
                parts = line.split()
                for part in parts:
                    if 'x' in part and part[0].isdigit():
                        current_resolution = part
                        if current_resolution not in resolutions_fps:
                            resolutions_fps[current_resolution] = []
            
            # Parse FPS line
            if 'Interval: Discrete' in line and current_resolution:
                # Extract FPS from "Interval: Discrete 0.033s (30.000 fps)"
                fps_match = re.search(r'\(([0-9.]+)\s*fps\)', line)
                if fps_match:
                    fps = float(fps_match.group(1))
                    fps_int = int(fps)
                    if fps_int not in resolutions_fps[current_resolution]:
                        resolutions_fps[current_resolution].append(fps_int)
        
        # Sort FPS for each resolution (highest first)
        for res in resolutions_fps:
            resolutions_fps[res].sort(reverse=True)
        
        # Sort resolutions by pixel count (highest first)
        sorted_resolutions = sorted(
            resolutions_fps.keys(),
            key=lambda x: tuple(map(int, x.split('x'))) if 'x' in x else (0, 0),
            reverse=True
        )
        
        return {
            "device": device,
            "name": device_name,
            "type": device_type,
            "driver": driver,
            "bus_info": bus_info,
            "is_usb": driver == "uvcvideo",
            "resolutions": sorted_resolutions,
            "resolutions_fps": resolutions_fps
        }
    except Exception as e:
        print(f"⚠️ Error getting resolutions for {device}: {e}")
        return None


def get_available_cameras() -> List[dict]:
    """Get list of available camera devices with resolutions and FPS info"""
    cameras = []
    devices = glob.glob('/dev/video*')
    
    for device in sorted(devices):
        try:
            device_info = get_device_resolutions(device)
            if device_info and device_info.get("resolutions"):
                cameras.append(device_info)
        except Exception:
            continue
    
    return cameras


@dataclass
class VideoConfig:
    """Video capture and encoding configuration"""
    # Camera settings - auto-detect at initialization
    device: str = field(default_factory=auto_detect_camera)
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
    
    # Buffer tuning
    max_latency_ms: int = 50


@dataclass 
class StreamingConfig:
    """Network streaming configuration"""
    # UDP output for Mission Planner / QGroundControl
    udp_host: str = "192.168.1.136"
    udp_port: int = 5600
    
    # Enable/disable streaming
    enabled: bool = True
    auto_start: bool = True


# Default configurations
DEFAULT_VIDEO_CONFIG = VideoConfig()
DEFAULT_STREAMING_CONFIG = StreamingConfig()
