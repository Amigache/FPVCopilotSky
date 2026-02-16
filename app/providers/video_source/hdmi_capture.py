"""
HDMI Capture Source Provider
Handles HDMI capture cards/dongles (USB or PCIe)
"""

import subprocess
import glob
import os
import re
import logging
from typing import Dict, List
from .base_source import VideoSourceProvider, VideoCapabilities

logger = logging.getLogger(__name__)


class HDMICaptureSource(VideoSourceProvider):
    """HDMI capture card/dongle source provider"""

    @classmethod
    def get_prefix(cls) -> str:
        return "hdmi:"

    @classmethod
    def _is_hdmi_capture_device(cls, card_type: str, driver: str) -> bool:
        """Determine if a V4L2 device is an HDMI capture card"""
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

        for keyword in capture_keywords:
            if keyword in name_lower:
                return True

        # If it's uvcvideo, it's likely a camera, not capture
        if driver == "uvcvideo":
            return False

        # Generic "capture" but not "camera"
        if "capture" in name_lower and "camera" not in name_lower and "webcam" not in name_lower:
            return True

        return False

    @classmethod
    def detect_sources(cls) -> List[Dict]:
        """Detect all HDMI capture devices"""
        sources = []

        try:
            # Check if v4l2-ctl is available
            check = subprocess.run(["which", "v4l2-ctl"], capture_output=True, timeout=2)
            if check.returncode != 0:
                return []

            devices = sorted(glob.glob("/dev/video*"))

            for device in devices:
                try:
                    result = subprocess.run(
                        ["v4l2-ctl", "-d", device, "--info"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                    if result.returncode != 0:
                        continue

                    card_type = ""
                    driver = ""
                    bus_info = ""
                    is_capture = False

                    for line in result.stdout.split("\n"):
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

                    if not is_capture:
                        continue

                    # Check if it's an HDMI capture device
                    if cls._is_hdmi_capture_device(card_type, driver):
                        source_id = f"hdmi:{device}"
                        source = cls._create_source_dict(source_id, device, card_type, driver, bus_info)
                        sources.append(source)

                except Exception as e:
                    logger.debug(f"Skipping {device}: {e}")
                    continue

            logger.info(f"Discovered {len(sources)} HDMI capture devices")

        except Exception as e:
            logger.error(f"Failed to discover HDMI capture devices: {e}")

        return sources

    @classmethod
    def _create_source_dict(cls, source_id: str, device: str, name: str, driver: str, bus_info: str) -> Dict:
        """Create source dictionary with full capabilities"""
        instance = cls(source_id, device)
        instance.device_name = name
        instance.device_info = {
            "driver": driver,
            "bus_info": bus_info,
            "is_usb": "usb" in bus_info.lower(),
        }

        try:
            caps = instance.get_capabilities()
            instance._capabilities = caps
        except Exception as e:
            logger.error(f"Failed to get capabilities for {device}: {e}")

        return instance.to_dict()

    @classmethod
    def from_id(cls, source_id: str) -> "HDMICaptureSource":
        """Create instance from source ID"""
        device_path = source_id.replace("hdmi:", "")
        return cls(source_id, device_path)

    def __init__(self, source_id: str, device_path: str):
        super().__init__(source_id, device_path)

    def is_available(self) -> bool:
        """Check if device exists and is accessible"""
        return os.path.exists(self.device_path)

    def get_capabilities(self) -> VideoCapabilities:
        """Get HDMI capture device capabilities"""
        resolutions = []
        framerates = []
        native_formats = []

        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", self.device_path, "--list-formats-ext"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                current_format = None

                for line in result.stdout.split("\n"):
                    line = line.strip()

                    if line.startswith("["):
                        format_match = re.search(r"'(.+?)'", line)
                        if format_match:
                            current_format = format_match.group(1)
                            if current_format and current_format not in native_formats:
                                native_formats.append(current_format)

                    elif "Size:" in line and current_format:
                        res_match = re.search(r"(\d+)x(\d+)", line)
                        if res_match:
                            width = int(res_match.group(1))
                            height = int(res_match.group(2))
                            res_tuple = (width, height)
                            if res_tuple not in resolutions:
                                resolutions.append(res_tuple)

                    elif "Interval:" in line:
                        fps_match = re.search(r"\(([\d.]+) fps\)", line)
                        if fps_match:
                            fps = int(float(fps_match.group(1)))
                            if fps not in framerates:
                                framerates.append(fps)

            resolutions.sort(key=lambda x: x[0] * x[1], reverse=True)
            framerates.sort(reverse=True)

            # Defaults for HDMI capture
            if not resolutions:
                resolutions = [(1920, 1080), (1280, 720), (1024, 768), (720, 576)]
            if not framerates:
                framerates = [60, 50, 30, 25]
            if not native_formats:
                native_formats = ["MJPEG", "YUYV"]

        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            resolutions = [(1920, 1080), (1280, 720)]
            framerates = [60, 30, 25]
            native_formats = ["MJPEG", "YUYV"]

        return VideoCapabilities(
            resolutions=resolutions,
            framerates=framerates,
            native_formats=native_formats,
            controls={"latency": "low", "passthrough": "H264" in native_formats},
        )

    def get_compatible_encoders(self) -> List[str]:
        """Get compatible encoders for HDMI capture"""
        caps = self.get_capabilities()
        encoders = []

        # Software encoders
        encoders.extend(["h264", "h264_openh264"])

        # MJPEG if supported
        if "MJPEG" in caps.native_formats or "MJPG" in caps.native_formats:
            encoders.insert(0, "mjpeg")

        # H264 passthrough if supported
        if "H264" in caps.native_formats:
            encoders.insert(0, "h264_passthrough")
            encoders.insert(1, "h264_hardware")

        return encoders

    def get_gstreamer_element(self, width: int, height: int, fps: int) -> str:
        """Get GStreamer source element"""
        return (
            f"v4l2src device={self.device_path} io-mode=2 ! "
            f"video/x-raw,width={width},height={height},framerate={fps}/1"
        )
