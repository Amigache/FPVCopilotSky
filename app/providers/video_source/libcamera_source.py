"""
LibCamera Source Provider
Handles CSI cameras via libcamera (modern Raspberry Pi, some Radxa boards)
"""

import re
import subprocess
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
            result = subprocess.run(["which", "libcamera-hello"], capture_output=True, timeout=2)

            if result.returncode != 0:
                return False

            # Check if GStreamer libcamerasrc element is available
            gst_result = subprocess.run(["gst-inspect-1.0", "libcamerasrc"], capture_output=True, timeout=2)

            return gst_result.returncode == 0

        except Exception as e:
            logger.debug(f"LibCamera not available: {e}")
            return False

    def discover_sources(self) -> List[Dict[str, Any]]:
        """
        Discover libcamera sources.

        Uses libcamera-hello --list-cameras to detect available cameras
        and parse real sensor modes (resolutions + FPS).
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

            # Parse the full output to extract per-camera modes
            parsed_cameras = self._parse_camera_list(result.stdout)

            # Add all discovered cameras
            for cam in parsed_cameras:
                caps = self._build_capabilities(cam)
                if caps:
                    cameras.append(
                        {
                            "source_id": f"libcamera:{cam['camera_id']}",
                            "name": f"{cam['sensor_name']} (CSI)",
                            "type": self.source_type,
                            "device": cam["camera_id"],
                            "capabilities": caps,
                            "provider": self.display_name,
                        }
                    )

        except Exception as e:
            logger.error(f"Failed to discover libcamera sources: {e}")

        return cameras

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_camera_list(stdout: str) -> List[Dict[str, Any]]:
        """Parse ``libcamera-hello --list-cameras`` output.

        Example output::

            Available cameras
            -----------------
            0 : imx219 [3280x2464 10-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx219@10)
                Modes: 'SRGGB10_CSI2P' : 640x480 [206.65 fps - (1000, 752)/1280x960 crop]
                                          1640x1232 [41.85 fps - (0, 0)/3280x2464 crop]
                                          1920x1080 [47.57 fps - (680, 692)/1920x1080 crop]
                                          3280x2464 [21.19 fps - (0, 0)/3280x2464 crop]
                       'SRGGB8' :         640x480 [206.65 fps - ...]
                                          ...

        Returns a list of dicts with keys:
            camera_id, sensor_name, max_resolution, modes [{width, height, fps}]
        """
        cameras: List[Dict[str, Any]] = []
        current_cam: Optional[Dict[str, Any]] = None
        # Regex for camera header: "0 : imx219 [3280x2464 ...] (/path)"
        cam_re = re.compile(r"^\s*(\d+)\s*:\s*(\S+)\s*\[(\d+)x(\d+)")
        # Regex for a mode line: "1920x1080 [47.57 fps"
        mode_re = re.compile(r"(\d{3,5})x(\d{3,5})\s*\[\s*([\d.]+)\s*fps")

        for line in stdout.split("\n"):
            cam_match = cam_re.match(line)
            if cam_match:
                if current_cam is not None:
                    cameras.append(current_cam)
                current_cam = {
                    "camera_id": cam_match.group(1),
                    "sensor_name": cam_match.group(2),
                    "max_resolution": f"{cam_match.group(3)}x{cam_match.group(4)}",
                    "modes": [],
                    "_seen": set(),
                }
                continue
            if current_cam is not None:
                for m in mode_re.finditer(line):
                    w, h, fps = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    key = (w, h)
                    if key not in current_cam["_seen"]:
                        current_cam["_seen"].add(key)
                        current_cam["modes"].append({"width": w, "height": h, "fps": fps})

        if current_cam is not None:
            cameras.append(current_cam)

        # Clean up internal field
        for cam in cameras:
            cam.pop("_seen", None)

        return cameras

    def _build_capabilities(self, cam: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build a capabilities dict from parsed camera data.

        If the camera has real modes (parsed from ``--list-cameras``), those
        are used.  Otherwise falls back to a conservative default set.
        """
        modes = cam.get("modes", [])

        if modes:
            # Build resolution list from real modes (largest first)
            modes_sorted = sorted(modes, key=lambda m: m["width"] * m["height"], reverse=True)
            resolutions = [f"{m['width']}x{m['height']}" for m in modes_sorted]

            # Build FPS-per-resolution from real data
            fps_map: Dict[str, List[int]] = {}
            for m in modes_sorted:
                res = f"{m['width']}x{m['height']}"
                max_fps = int(m["fps"])
                # Build a sensible set of lower framerates
                fps_list = sorted(
                    {f for f in [max_fps, 30, 24, 15, 10] if f <= max_fps},
                    reverse=True,
                )
                fps_map[res] = fps_list
        else:
            # Fallback: conservative defaults
            resolutions = ["1920x1080", "1280x720", "640x480"]
            fps_map = {
                "1920x1080": [30, 24, 15],
                "1280x720": [60, 30, 24, 15],
                "640x480": [120, 90, 60, 30, 15],
            }

        sensor_name = cam.get("sensor_name", "unknown")

        return {
            "is_capture_device": True,
            "identity": {
                "name": f"LibCamera {cam.get('camera_id', '0')} ({sensor_name})",
                "driver": "libcamera",
                "bus_info": "csi",
                "sensor": sensor_name,
            },
            "is_usb": False,
            "is_csi": True,
            "supported_formats": [
                "NV12",
                "YUYV",
                "RGB",
            ],
            "default_format": "NV12",
            "format_resolutions": {
                "NV12": resolutions,
            },
            "supported_resolutions": resolutions,
            "supported_framerates": fps_map,
            "hardware_encoding": False,  # ISP does NOT encode H264; encoder providers handle that
            "device_path": cam.get("camera_id", "0"),
            "isp_available": True,
            "autofocus": sensor_name.lower() in ("imx708",),
            "autoexposure": True,
            "autowhitebalance": True,
        }

    def get_source_capabilities(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get capabilities for a libcamera source.

        Delegates to ``_build_capabilities`` using cached discovery data
        when available, falling back to a conservative default set.
        """
        # Try to find real data from a previous discover_sources() call
        try:
            result = subprocess.run(
                ["libcamera-hello", "--list-cameras"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                cams = self._parse_camera_list(result.stdout)
                for cam in cams:
                    if cam["camera_id"] == source_id or f"libcamera:{cam['camera_id']}" == source_id:
                        return self._build_capabilities(cam)
        except Exception:
            pass

        # Fallback: build with no modes (will use defaults)
        return self._build_capabilities({"camera_id": source_id, "sensor_name": "unknown", "modes": []})

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
            warnings.append(f"Resolution {resolution} may not be optimal for this sensor")

        # Check framerate
        if resolution in caps["supported_framerates"]:
            if framerate not in caps["supported_framerates"][resolution]:
                max_fps = max(caps["supported_framerates"][resolution])
                if framerate > max_fps:
                    warnings.append(f"Framerate {framerate} may be too high. Max recommended: {max_fps}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "adjusted_config": adjusted,
        }
