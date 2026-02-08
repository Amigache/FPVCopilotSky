"""
LibCamera Source Provider
Handles CSI cameras via libcamera (modern Raspberry Pi, some Radxa boards)
"""

import subprocess
import json
import logging
from typing import Dict, List, Optional, Any
from ..base.video_source_provider import VideoSourceProvider

logger = logging.getLogger(__name__)


class LibCameraSource(VideoSourceProvider):
    """
    LibCamera source provider for CSI/MIPI cameras.

    Supports:
    - Raspberry Pi Camera Module v1/v2/v3/HQ
    - Radxa boards with libcamera support
    - Other SBCs with CSI interface and libcamera

    Higher quality and lower latency than V4L2 for CSI cameras.
    """

    def __init__(self):
        super().__init__()
        self.source_type = "libcamera"
        self.display_name = "LibCamera (CSI)"
        self.priority = 80  # Higher priority than V4L2 for CSI cameras
        self.gst_source_element = "libcamerasrc"

    def is_available(self) -> bool:
        """Check if libcamera and GStreamer element are available"""
        try:
            # Check if libcamera-hello exists (indicates libcamera is installed)
            result = subprocess.run(
                ["which", "libcamera-hello"], capture_output=True, timeout=2
            )

            if result.returncode != 0:
                return False

            # Check if GStreamer libcamerasrc element is available
            gst_result = subprocess.run(
                ["gst-inspect-1.0", "libcamerasrc"], capture_output=True, timeout=2
            )

            return gst_result.returncode == 0

        except Exception as e:
            logger.debug(f"LibCamera not available: {e}")
            return False

    def discover_sources(self) -> List[Dict[str, Any]]:
        """
        Discover libcamera sources.

        Uses libcamera-hello --list-cameras to detect available cameras.
        """
        if not self.is_available():
            return []

        cameras = []

        try:
            # List cameras using libcamera-hello
            result = subprocess.run(
                ["libcamera-hello", "--list-cameras"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return []

            # Parse output
            # Example output:
            # Available cameras
            # -----------------
            # 0 : imx219 [3280x2464] (/base/soc/i2c0mux/i2c@1/imx219@10)
            #     Modes: 'SRGGB10_CSI2P' : 640x480 [206.65 fps - (1000, 752)/1280x960 crop]

            current_camera = None
            for line in result.stdout.split("\n"):
                line = line.strip()

                # Parse camera line (starts with number)
                if line and line[0].isdigit() and ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        camera_id = parts[0].strip()
                        info = parts[1].strip()

                        # Extract name and sensor
                        name_parts = info.split("[")
                        sensor_name = name_parts[0].strip()

                        # Extract max resolution
                        max_res = None
                        if len(name_parts) > 1:
                            res_str = name_parts[1].split("]")[0]
                            if "x" in res_str:
                                max_res = res_str

                        current_camera = {
                            "camera_id": camera_id,
                            "sensor_name": sensor_name,
                            "max_resolution": max_res,
                        }

            # If we found at least one camera, add it
            if current_camera:
                caps = self.get_source_capabilities(current_camera["camera_id"])
                if caps:
                    cameras.append(
                        {
                            "source_id": f"libcamera:{current_camera['camera_id']}",
                            "name": f"{current_camera['sensor_name']} (CSI)",
                            "type": self.source_type,
                            "device": current_camera["camera_id"],
                            "capabilities": caps,
                            "provider": self.display_name,
                        }
                    )

        except Exception as e:
            logger.error(f"Failed to discover libcamera sources: {e}")

        return cameras

    def get_source_capabilities(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get capabilities for a libcamera source.

        LibCamera provides comprehensive ISP capabilities, better than V4L2.
        """
        try:
            # Common resolutions for Raspberry Pi cameras
            # Will be available based on sensor (imx219, imx477, etc.)
            common_resolutions = [
                "3280x2464",  # Max for IMX219
                "1920x1080",  # Full HD
                "1640x1232",  # 4:3 mid
                "1280x720",  # HD
                "640x480",  # VGA
            ]

            # Common framerates (libcamera supports variable)
            common_fps = {
                "640x480": [120, 90, 60, 30, 15],
                "1280x720": [60, 30, 24, 15],
                "1640x1232": [40, 30, 24, 15],
                "1920x1080": [30, 24, 15],
                "3280x2464": [15, 10],
            }

            return {
                "is_capture_device": True,
                "identity": {
                    "name": f"LibCamera {source_id}",
                    "driver": "libcamera",
                    "bus_info": "csi",
                },
                "is_usb": False,
                "is_csi": True,
                "supported_formats": [
                    "NV12",
                    "YUYV",
                    "RGB",
                    "MJPEG",
                    "H264",
                ],  # LibCamera ISP can output many formats
                "default_format": "NV12",  # Native format, best performance
                "format_resolutions": {
                    "NV12": common_resolutions,
                    "H264": [
                        "1920x1080",
                        "1280x720",
                        "640x480",
                    ],  # Hardware encoding available
                },
                "supported_resolutions": common_resolutions,
                "supported_framerates": common_fps,
                "hardware_encoding": True,  # LibCamera often has ISP with H264 encoder
                "device_path": source_id,
                "isp_available": True,  # Image Signal Processor features
                "autofocus": False,  # Depends on camera module
                "autoexposure": True,
                "autowhitebalance": True,
            }

        except Exception as e:
            logger.error(f"Failed to get capabilities for libcamera {source_id}: {e}")
            return None

    def build_source_element(self, source_id: str, config: Dict) -> Dict:
        """
        Build libcamerasrc element configuration.

        LibCamera has different properties than v4l2src.
        """
        try:
            # Extract camera ID if source_id is in format "libcamera:0"
            camera_id = source_id
            if ":" in source_id:
                camera_id = source_id.split(":")[1]

            width = config.get("width", 1920)
            height = config.get("height", 1080)
            framerate = config.get("framerate", 30)

            # LibCamera outputs video/x-raw by default (NV12 format)
            # This is better than MJPEG for CSI cameras
            caps_str = f"video/x-raw,width={width},height={height},framerate={framerate}/1,format=NV12"

            return {
                "success": True,
                "source_element": {
                    "name": "source",
                    "element": "libcamerasrc",
                    "properties": {"camera-name": camera_id, "do-timestamp": True},
                },
                "caps_filter": caps_str,
                "post_elements": [],  # No conversion needed, raw output
                "output_format": "video/x-raw",
                "error": None,
            }

        except Exception as e:
            logger.error(f"Failed to build libcamera source element: {e}")
            return {"success": False, "error": str(e)}

    def validate_config(self, source_id: str, config: Dict) -> Dict[str, Any]:
        """Validate configuration for libcamera source"""
        caps = self.get_source_capabilities(source_id)
        if not caps:
            return {
                "valid": False,
                "errors": [f"LibCamera source {source_id} not available"],
                "warnings": [],
                "adjusted_config": config,
            }

        errors = []
        warnings = []
        adjusted = dict(config)

        width = config.get("width", 1920)
        height = config.get("height", 1080)
        framerate = config.get("framerate", 30)

        resolution = f"{width}x{height}"

        # Check if resolution is supported
        if resolution not in caps["supported_resolutions"]:
            warnings.append(
                f"Resolution {resolution} may not be optimal for this sensor"
            )

        # Check framerate
        if resolution in caps["supported_framerates"]:
            if framerate not in caps["supported_framerates"][resolution]:
                max_fps = max(caps["supported_framerates"][resolution])
                if framerate > max_fps:
                    warnings.append(
                        f"Framerate {framerate} may be too high. Max recommended: {max_fps}"
                    )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "adjusted_config": adjusted,
        }
