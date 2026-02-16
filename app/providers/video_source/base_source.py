"""
Base Video Source Provider

Abstract base class for all video input sources
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class VideoCapabilities:
    """Video source capabilities"""

    resolutions: List[Tuple[int, int]]  # [(1920, 1080), (1280, 720), ...]
    framerates: List[int]  # [30, 60, ...]
    native_formats: List[str]  # ["MJPEG", "H264", "YUYV"]
    controls: Dict  # Camera controls (brightness, contrast, etc.)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "resolutions": [{"width": w, "height": h} for w, h in self.resolutions],
            "framerates": self.framerates,
            "native_formats": self.native_formats,
            "controls": self.controls,
        }


class VideoSourceProvider(ABC):
    """
    Abstract base class for video source providers.

    Each provider handles a specific type of video input:
    - V4L2 for USB cameras
    - LibCamera for CSI cameras
    - HDMI Capture for capture cards
    - Network streams for RTSP/HTTP sources
    """

    def __init__(self, source_id: str, device_path: str):
        """
        Initialize video source provider.

        Args:
            source_id: Unique identifier (e.g., "v4l2:/dev/video0")
            device_path: Physical or virtual device path
        """
        self.source_id = source_id
        self.device_path = device_path
        self.device_name = "Unknown Device"
        self.device_info = {}
        self._capabilities = None
        self.display_name = self.__class__.__name__
        self.device_name = "Unknown"
        self.device_info = {}
        self._capabilities: Optional[VideoCapabilities] = None

    @classmethod
    @abstractmethod
    def get_prefix(cls) -> str:
        """
        Get the prefix for this provider type.

        Returns:
            Prefix string (e.g., "v4l2:", "libcamera:", "hdmi:", "rtsp:")
        """
        pass

    @classmethod
    @abstractmethod
    def detect_sources(cls) -> List[Dict]:
        """
        Detect all available sources of this type.

        Returns:
            List of source dictionaries with basic info
        """
        pass

    @classmethod
    @abstractmethod
    def from_id(cls, source_id: str) -> "VideoSourceProvider":
        """
        Create provider instance from source ID.

        Args:
            source_id: Source identifier

        Returns:
            VideoSourceProvider instance
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the source is currently available.

        Returns:
            True if source can be used
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> VideoCapabilities:
        """
        Get detailed capabilities of this source.

        Returns:
            VideoCapabilities with all supported configs
        """
        pass

    @abstractmethod
    def get_compatible_encoders(self) -> List[str]:
        """
        Get list of compatible encoder IDs for this source.

        Returns:
            List of encoder provider IDs (e.g., ["h264_passthrough", "x264", "mjpeg"])
        """
        pass

    @abstractmethod
    def get_gstreamer_element(self, width: int, height: int, fps: int) -> str:
        """
        Get GStreamer source element for this device.

        Args:
            width: Video width
            height: Video height
            fps: Framerate

        Returns:
            GStreamer element string (e.g., "v4l2src device=/dev/video0 ! ...")
        """
        pass

    def to_dict(self) -> Dict:
        """
        Convert source to dictionary for API responses.

        Returns:
            Dictionary with source information
        """
        caps = self.get_capabilities() if self._capabilities is None else self._capabilities

        return {
            "id": self.source_id,
            "type": self.get_prefix().rstrip(":"),
            "name": self.device_name,
            "device_path": self.device_path,
            "available": self.is_available(),
            "capabilities": caps.to_dict() if caps else None,
            "compatible_encoders": self.get_compatible_encoders(),
            "device_info": self.device_info,
        }
