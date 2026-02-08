"""
HDMI Capture Source Provider
Handles HDMI capture cards/dongles (USB or PCIe)
"""

import subprocess
import glob
import re
import logging
from typing import Dict, List, Optional, Any
from ..base.video_source_provider import VideoSourceProvider

logger = logging.getLogger(__name__)


class HDMICaptureSource(VideoSourceProvider):
    """
    HDMI capture card/dongle source provider.

    Supports:
    - USB HDMI capture devices (Elgato, AVerMedia, generic)
    - PCIe capture cards
    - Detected via V4L2 but identified as capture devices

    Common use cases:
    - Capturing video from FPV goggles with HDMI out
    - Recording drone OSD feed
    - External camera capture
    """

    def __init__(self):
        super().__init__()
        self.source_type = "hdmi_capture"
        self.display_name = "HDMI Capture"
        self.priority = 75  # Higher than regular V4L2, lower than libcamera
        self.gst_source_element = "v4l2src"

    def is_available(self) -> bool:
        """Check if v4l2-ctl is available (needed to detect HDMI capture)"""
        try:
            result = subprocess.run(["which", "v4l2-ctl"], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def _is_hdmi_capture_device(self, device_name: str, driver: str, card_type: str) -> bool:
        """
        Determine if a V4L2 device is an HDMI capture card.

        Heuristics:
        - Card name contains "HDMI", "Capture", "Game Capture", "Video Capture"
        - Driver is not 'uvcvideo' (regular cameras)
        - Common capture card identifiers
        """
        name_lower = card_type.lower()

        # Common HDMI capture card identifiers
        capture_keywords = [
            "hdmi capture",
            "game capture",
            "video capture card",
            "elgato",
            "avermedia",
            "magewell",
            "blackmagic",
            "intensity",
            "capture card",
        ]

        # Check if any keyword matches
        for keyword in capture_keywords:
            if keyword in name_lower:
                return True

        # If it's uvcvideo, it's likely a camera, not capture
        if driver == "uvcvideo":
            return False

        # Check for generic "capture" in name but not "camera"
        if "capture" in name_lower and "camera" not in name_lower and "webcam" not in name_lower:
            return True

        return False

    def discover_sources(self) -> List[Dict[str, Any]]:
        """
        Discover HDMI capture devices via V4L2.

        Filters V4L2 devices to find HDMI capture cards.
        """
        if not self.is_available():
            return []

        captures = []
        devices = sorted(glob.glob("/dev/video*"))

        for device in devices:
            try:
                # Get device info
                info_result = subprocess.run(
                    ["v4l2-ctl", "-d", device, "--info"], capture_output=True, text=True, timeout=5
                )

                if info_result.returncode != 0:
                    continue

                device_name = device
                card_type = ""
                driver = ""
                bus_info = ""
                is_capture = False

                for line in info_result.stdout.split("\n"):
                    if "Card type" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            card_type = parts[1].strip()
                    elif "Driver name" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            driver = parts[1].strip()
                    elif "Bus info" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            bus_info = parts[1].strip()
                    elif "Video Capture" in line:
                        is_capture = True

                # Skip if not a capture device
                if not is_capture:
                    continue

                # Check if it's an HDMI capture device
                if self._is_hdmi_capture_device(device_name, driver, card_type):
                    caps = self.get_source_capabilities(device)
                    if caps:
                        captures.append(
                            {
                                "source_id": device,
                                "name": card_type,
                                "type": self.source_type,
                                "device": device,
                                "capabilities": caps,
                                "provider": self.display_name,
                            }
                        )

            except Exception as e:
                logger.debug(f"Skipping {device}: {e}")
                continue

        return captures

    def get_source_capabilities(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get capabilities for HDMI capture device.

        HDMI capture cards typically support:
        - 1080p60, 1080p30, 720p60, 720p30
        - YUYV or MJPEG formats
        - Some support H264 passthrough
        """
        try:
            device = source_id

            # Get device info
            info_result = subprocess.run(
                ["v4l2-ctl", "-d", device, "--info"], capture_output=True, text=True, timeout=5
            )

            if info_result.returncode != 0:
                return None

            card_type = ""
            driver = ""
            bus_info = ""

            for line in info_result.stdout.split("\n"):
                if "Card type" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        card_type = parts[1].strip()
                elif "Driver name" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        driver = parts[1].strip()
                elif "Bus info" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        bus_info = parts[1].strip()

            # Get formats
            formats_result = subprocess.run(
                ["v4l2-ctl", "-d", device, "--list-formats-ext"], capture_output=True, text=True, timeout=5
            )

            formats = []
            resolutions_fps = {}

            current_format = None
            current_resolution = None

            for line in formats_result.stdout.split("\n"):
                if "'" in line:
                    parts = line.split("'")
                    if len(parts) >= 2:
                        current_format = parts[1]
                        if current_format not in formats:
                            formats.append(current_format)

                if "Size: Discrete" in line and current_format:
                    parts = line.split()
                    for part in parts:
                        if "x" in part and part[0].isdigit():
                            current_resolution = part
                            if current_resolution not in resolutions_fps:
                                resolutions_fps[current_resolution] = []

                if "Interval: Discrete" in line and current_resolution:
                    fps_match = re.search(r"\(([0-9.]+)\s*fps\)", line)
                    if fps_match:
                        fps = int(float(fps_match.group(1)))
                        if fps not in resolutions_fps[current_resolution]:
                            resolutions_fps[current_resolution].append(fps)

            # Sort
            for res in resolutions_fps:
                resolutions_fps[res].sort(reverse=True)

            sorted_resolutions = sorted(
                resolutions_fps.keys(),
                key=lambda x: tuple(map(int, x.split("x"))) if "x" in x else (0, 0),
                reverse=True,
            )

            # Determine default format
            default_format = "MJPEG" if "MJPG" in formats or "MJPEG" in formats else formats[0] if formats else "YUYV"

            # Check for hardware encoding
            hardware_encoding = any(fmt in ["H264", "HEVC"] for fmt in formats)

            return {
                "is_capture_device": True,
                "is_hdmi_capture": True,
                "identity": {"name": card_type, "driver": driver, "bus_info": bus_info},
                "is_usb": "usb" in bus_info.lower(),
                "supported_formats": formats,
                "default_format": default_format,
                "supported_resolutions": sorted_resolutions,
                "supported_framerates": resolutions_fps,
                "hardware_encoding": hardware_encoding,
                "device_path": device,
                "passthrough": hardware_encoding,  # Some cards pass through H264/HEVC
                "latency": "low",  # HDMI capture typically low latency
            }

        except Exception as e:
            logger.error(f"Failed to get capabilities for {source_id}: {e}")
            return None

    def build_source_element(self, source_id: str, config: Dict) -> Dict:
        """
        Build V4L2 source element for HDMI capture.

        Similar to V4L2 camera but optimized for capture cards.
        """
        try:
            caps = self.get_source_capabilities(source_id)
            if not caps:
                return {"success": False, "error": f"HDMI capture device {source_id} not available"}

            width = config.get("width", 1920)
            height = config.get("height", 1080)
            framerate = config.get("framerate", 30)

            # Prefer MJPEG for low CPU usage
            pixel_format = config.get("format", caps.get("default_format", "MJPEG"))

            format_mapping = {
                "MJPEG": "image/jpeg",
                "MJPG": "image/jpeg",
                "YUYV": "video/x-raw,format=YUY2",
                "H264": "video/x-h264",
                "HEVC": "video/x-h265",
            }

            gst_format = format_mapping.get(pixel_format, "image/jpeg")
            caps_str = f"{gst_format},width={width},height={height},framerate={framerate}/1"

            return {
                "success": True,
                "source_element": {
                    "name": "source",
                    "element": "v4l2src",
                    "properties": {
                        "device": source_id,
                        "do-timestamp": True,
                        "io-mode": 2,  # MMAP mode for better performance with capture cards
                    },
                },
                "caps_filter": caps_str,
                "post_elements": [],
                "output_format": gst_format,
                "error": None,
            }

        except Exception as e:
            logger.error(f"Failed to build HDMI capture source element: {e}")
            return {"success": False, "error": str(e)}

    def validate_config(self, source_id: str, config: Dict) -> Dict[str, Any]:
        """Validate configuration for HDMI capture device"""
        caps = self.get_source_capabilities(source_id)
        if not caps:
            return {
                "valid": False,
                "errors": [f"HDMI capture device {source_id} not available"],
                "warnings": [],
                "adjusted_config": config,
            }

        errors = []
        warnings = []
        adjusted = dict(config)

        width = config.get("width")
        height = config.get("height")
        framerate = config.get("framerate")

        if width and height:
            resolution = f"{width}x{height}"
            if resolution not in caps["supported_resolutions"]:
                errors.append(f"Resolution {resolution} not supported by capture card")

        if framerate and width and height:
            resolution = f"{width}x{height}"
            if resolution in caps["supported_framerates"]:
                if framerate not in caps["supported_framerates"][resolution]:
                    warnings.append(f"Framerate {framerate}fps may not be available at {resolution}")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings, "adjusted_config": adjusted}
