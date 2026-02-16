"""
LibCamera Source Provider
Handles CSI cameras via libcamera (modern Raspberry Pi, some Radxa boards)
"""

import subprocess
import logging
from typing import Dict, List
from .base_source import VideoSourceProvider, VideoCapabilities

logger = logging.getLogger(__name__)


class LibCameraSource(VideoSourceProvider):
    """LibCamera source provider for CSI/MIPI cameras"""

    @classmethod
    def get_prefix(cls) -> str:
        return "libcamera:"

    @classmethod
    def detect_sources(cls) -> List[Dict]:
        """Detect all LibCamera CSI sources"""
        sources = []

        try:
            # Check if libcamera-hello exists
            check = subprocess.run(["which", "libcamera-hello"], capture_output=True, timeout=2)
            if check.returncode != 0:
                logger.debug("libcamera-hello not found")
                return []

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
            # Example: 0 : imx219 [3280x2464] (/base/soc/i2c0mux/i2c@1/imx219@10)
            for line in result.stdout.split("\n"):
                line = line.strip()

                if line and line[0].isdigit() and ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        camera_id = parts[0].strip()
                        info = parts[1].strip()

                        # Extract sensor name
                        name_parts = info.split("[")
                        sensor_name = name_parts[0].strip()

                        # Extract max resolution
                        max_res = None
                        if len(name_parts) > 1:
                            res_str = name_parts[1].split("]")[0]
                            if "x" in res_str:
                                max_res = res_str

                        source_id = f"libcamera:{camera_id}"
                        source = cls._create_source_dict(source_id, camera_id, sensor_name, max_res)
                        sources.append(source)

            logger.info(f"Discovered {len(sources)} LibCamera sources")

        except Exception as e:
            logger.error(f"Failed to discover libcamera sources: {e}")

        return sources

    @classmethod
    def _create_source_dict(cls, source_id: str, camera_id: str, sensor_name: str, max_res: str) -> Dict:
        """Create source dictionary with full capabilities"""
        instance = cls(source_id, camera_id)
        instance.device_name = f"{sensor_name} (CSI)"
        instance.device_info = {
            "sensor": sensor_name,
            "max_resolution": max_res,
            "bus": "csi",
        }

        # Get capabilities
        try:
            caps = instance.get_capabilities()
            instance._capabilities = caps
        except Exception as e:
            logger.error(f"Failed to get capabilities for {camera_id}: {e}")

        return instance.to_dict()

    @classmethod
    def from_id(cls, source_id: str) -> "LibCameraSource":
        """Create instance from source ID"""
        camera_id = source_id.replace("libcamera:", "")
        return cls(source_id, camera_id)

    def __init__(self, source_id: str, device_path: str):
        super().__init__(source_id, device_path)

    def is_available(self) -> bool:
        """Check if libcamera is available"""
        try:
            result = subprocess.run(
                ["libcamera-hello", "--list-cameras"],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_capabilities(self) -> VideoCapabilities:
        """Get LibCamera capabilities"""
        # Common resolutions for Raspberry Pi cameras (IMX219, IMX477, etc.)
        resolutions = [
            (3280, 2464),  # Max for IMX219
            (1920, 1080),  # Full HD
            (1640, 1232),  # 4:3 mid
            (1280, 720),  # HD
            (640, 480),  # VGA
        ]

        # LibCamera supports variable framerates depending on resolution
        framerates = [120, 90, 60, 30, 24, 15, 10]

        # LibCamera ISP can output many formats
        native_formats = ["NV12", "YUYV", "RGB", "MJPEG", "H264"]

        return VideoCapabilities(
            resolutions=resolutions,
            framerates=framerates,
            native_formats=native_formats,
            controls={
                "isp_available": True,
                "autofocus": False,  # Depends on module
                "autoexposure": True,
                "autowhitebalance": True,
            },
        )

    def get_compatible_encoders(self) -> List[str]:
        """Get compatible encoders for LibCamera"""
        encoders = []

        # LibCamera often has ISP with hardware H264 encoding
        encoders.append("h264_passthrough")
        encoders.append("h264_hardware")

        # Software encoders always work
        encoders.extend(["h264", "h264_openh264", "mjpeg"])

        return encoders

    def get_gstreamer_element(self, width: int, height: int, fps: int) -> str:
        """Get GStreamer source element"""
        camera_id = self.device_path  # Already extracted in __init__
        return (
            f"libcamerasrc camera-name={camera_id} ! "
            f"video/x-raw,width={width},height={height},framerate={fps}/1,format=NV12"
        )
