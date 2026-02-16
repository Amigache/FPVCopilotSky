"""
V4L2 Camera Source Provider
Handles USB cameras and CSI cameras exposed through video4linux2
"""

import subprocess
import glob
import os
import re
import logging
from typing import Dict, List
from .base_source import VideoSourceProvider, VideoCapabilities

logger = logging.getLogger(__name__)


class V4L2CameraSource(VideoSourceProvider):
    """Video4Linux2 camera source provider for USB cameras"""

    @classmethod
    def get_prefix(cls) -> str:
        return "v4l2:"

    @classmethod
    def detect_sources(cls) -> List[Dict]:
        """Detect all V4L2 video capture devices"""
        sources = []
        devices_by_bus = {}  # Group by bus_info to avoid duplicates

        devices = sorted(glob.glob("/dev/video*"))

        for device in devices:
            try:
                # Check if v4l2-ctl is available
                result = subprocess.run(
                    ["v4l2-ctl", "-d", device, "--info"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode != 0:
                    continue

                # Parse device info
                device_name = os.path.basename(device)
                driver = "unknown"
                bus_info = ""
                is_capture = False

                for line in result.stdout.split("\n"):
                    if "Card type" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            device_name = parts[1].strip()
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

                # Use bus_info to deduplicate (same camera, multiple /dev/video*)
                if bus_info and bus_info in devices_by_bus:
                    continue

                source_id = f"v4l2:{device}"
                source = cls._create_source_dict(source_id, device, device_name, driver, bus_info)

                if bus_info:
                    devices_by_bus[bus_info] = source

                sources.append(source)

            except Exception as e:
                logger.debug(f"Skipping {device}: {e}")
                continue

        logger.info(f"Discovered {len(sources)} V4L2 cameras")
        return sources

    @classmethod
    def _create_source_dict(cls, source_id: str, device: str, name: str, driver: str, bus_info: str) -> Dict:
        """Create source dictionary with full capabilities"""
        instance = cls(source_id, device)
        instance.device_name = name
        instance.device_info = {
            "driver": driver,
            "bus_info": bus_info,
        }

        # Get capabilities
        try:
            caps = instance.get_capabilities()
            instance._capabilities = caps
        except Exception as e:
            logger.error(f"Failed to get capabilities for {device}: {e}")

        return instance.to_dict()

    @classmethod
    def from_id(cls, source_id: str) -> "V4L2CameraSource":
        """Create instance from source ID"""
        device_path = source_id.replace("v4l2:", "")
        return cls(source_id, device_path)

    def __init__(self, source_id: str, device_path: str):
        super().__init__(source_id, device_path)

    def is_available(self) -> bool:
        """Check if device exists and is accessible"""
        return os.path.exists(self.device_path)

    def get_capabilities(self) -> VideoCapabilities:
        """Get detailed capabilities using v4l2-ctl"""
        resolutions = []
        framerates = []
        native_formats = []

        try:
            # Get formats and resolutions
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

                    # Parse format line
                    if line.startswith("["):
                        format_match = re.search(r"'(.+?)'", line)
                        if format_match:
                            current_format = format_match.group(1)
                            if current_format and current_format not in native_formats:
                                native_formats.append(current_format)

                    # Parse resolution line
                    elif "Size:" in line and current_format:
                        res_match = re.search(r"(\d+)x(\d+)", line)
                        if res_match:
                            width = int(res_match.group(1))
                            height = int(res_match.group(2))
                            res_tuple = (width, height)
                            if res_tuple not in resolutions:
                                resolutions.append(res_tuple)

                    # Parse framerate line
                    elif "Interval:" in line:
                        fps_match = re.search(r"\(([\d.]+) fps\)", line)
                        if fps_match:
                            fps = int(float(fps_match.group(1)))
                            if fps not in framerates:
                                framerates.append(fps)

            # Sort and deduplicate
            resolutions.sort(key=lambda x: x[0] * x[1], reverse=True)
            framerates.sort(reverse=True)

            # Default values if detection failed
            if not resolutions:
                resolutions = [(1920, 1080), (1280, 720), (640, 480)]
            if not framerates:
                framerates = [30, 25, 15]
            if not native_formats:
                native_formats = ["MJPEG", "YUYV"]

        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            resolutions = [(1920, 1080), (1280, 720), (640, 480)]
            framerates = [30, 25, 15]
            native_formats = ["MJPEG", "YUYV"]

        return VideoCapabilities(
            resolutions=resolutions,
            framerates=framerates,
            native_formats=native_formats,
            controls={},  # TODO: Parse v4l2 controls if needed
        )

    def get_compatible_encoders(self) -> List[str]:
        """Get compatible encoders based on native format"""
        caps = self.get_capabilities()
        encoders = []

        # Always compatible with software encoders
        encoders.extend(["h264", "h264_openh264"])  # x264 and openh264

        # If camera outputs MJPEG natively, MJPEG encoder is efficient
        if "MJPEG" in caps.native_formats or "MJPG" in caps.native_formats:
            encoders.insert(0, "mjpeg")  # Prefer MJPEG for MJPEG cameras

        # If camera outputs H264 natively, passthrough is best
        if "H264" in caps.native_formats:
            encoders.insert(0, "h264_passthrough")
            encoders.insert(1, "h264_hardware")  # Also add hardware encoder

        return encoders

    def get_gstreamer_element(self, width: int, height: int, fps: int) -> str:
        """Get GStreamer source element"""
        return f"v4l2src device={self.device_path} ! " f"video/x-raw,width={width},height={height},framerate={fps}/1"
