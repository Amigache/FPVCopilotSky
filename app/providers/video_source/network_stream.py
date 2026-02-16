"""
Network Stream Source Provider
Handles remote video streams (RTSP, HTTP, HLS)
"""

import logging
from typing import Dict, List
from .base_source import VideoSourceProvider, VideoCapabilities

logger = logging.getLogger(__name__)


class NetworkStreamSource(VideoSourceProvider):
    """Network stream source provider for remote video feeds"""

    @classmethod
    def get_prefix(cls) -> str:
        return "network:"

    @classmethod
    def detect_sources(cls) -> List[Dict]:
        """
        Network streams cannot be auto-discovered.
        They must be configured manually by the user.
        """
        # Return empty list - streams must be added manually
        return []

    @classmethod
    def from_id(cls, source_id: str) -> "NetworkStreamSource":
        """Create instance from source ID"""
        uri = source_id.replace("network:", "")
        return cls(source_id, uri)

    @classmethod
    def add_stream(cls, uri: str, name: str = None) -> Dict:
        """
        Helper to add a network stream configuration.

        Args:
            uri: Stream URI (rtsp://..., http://..., etc.)
            name: Friendly name for the stream
        """
        source_id = f"network:{uri}"
        instance = cls(source_id, uri)

        if not name:
            # Determine stream type from URI
            uri_lower = uri.lower()
            if uri_lower.startswith("rtsp://"):
                name = "RTSP Stream"
            elif uri_lower.startswith("rtmp://"):
                name = "RTMP Stream"
            elif ".m3u8" in uri_lower:
                name = "HLS Stream"
            else:
                name = "Network Stream"

        instance.device_name = name
        instance.device_info = {
            "uri": uri,
            "protocol": uri.split("://")[0] if "://" in uri else "unknown",
        }

        try:
            instance._capabilities = instance.get_capabilities()
        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")

        return instance.to_dict()

    def __init__(self, source_id: str, device_path: str):
        super().__init__(source_id, device_path)

    def is_available(self) -> bool:
        """Network streams availability depends on network connectivity"""
        # Cannot reliably check without trying to connect
        # Return True and let GStreamer handle connection
        return True

    def get_capabilities(self) -> VideoCapabilities:
        """
        Get generic network stream capabilities.
        Actual capabilities determined at runtime by stream.
        """
        # Generic resolutions - actual depends on stream
        resolutions = [
            (3840, 2160),  # 4K
            (1920, 1080),  # Full HD
            (1280, 720),  # HD
            (640, 480),  # VGA
        ]

        framerates = [60, 50, 30, 25, 15]

        # Network streams typically provide encoded data
        native_formats = ["H264", "H265", "MJPEG"]

        return VideoCapabilities(
            resolutions=resolutions,
            framerates=framerates,
            native_formats=native_formats,
            controls={
                "requires_network": True,
                "latency": "variable",
                "auto_capabilities": True,
            },
        )

    def get_compatible_encoders(self) -> List[str]:
        """Get compatible encoders for network streams"""
        # Network streams usually provide encoded data already
        # Re-encoding may be necessary depending on codec
        return ["h264_passthrough", "h264_hardware", "h264", "h264_openh264", "mjpeg"]

    def get_gstreamer_element(self, width: int, height: int, fps: int) -> str:
        """Get GStreamer source element"""
        uri = self.device_path

        # Use rtspsrc for RTSP, urisourcebin for others
        if uri.lower().startswith("rtsp://"):
            return (
                f"rtspsrc location={uri} latency=100 drop-on-latency=true protocols=tcp ! "
                f"decodebin ! "
                f"videoscale ! video/x-raw,width={width},height={height}"
            )
        else:
            # urisourcebin for HTTP/HLS/RTMP
            return (
                f"urisourcebin uri={uri} ! " f"decodebin ! " f"videoscale ! video/x-raw,width={width},height={height}"
            )
