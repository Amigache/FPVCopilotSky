"""
Video Source Provider System

Manages detection and configuration of video input sources:
- V4L2 USB cameras
- LibCamera CSI cameras
- HDMI capture cards
- Network streams (RTSP/HTTP)
"""

import logging
from typing import Dict, List, Optional, Type
from .base_source import VideoSourceProvider, VideoCapabilities
from .v4l2_camera import V4L2CameraSource
from .libcamera_source import LibCameraSource
from .hdmi_capture import HDMICaptureSource
from .network_stream import NetworkStreamSource

logger = logging.getLogger(__name__)


class VideoSourceRegistry:
    """Registry for all video source providers"""

    def __init__(self):
        self._provider_classes: Dict[str, Type[VideoSourceProvider]] = {}
        self._register_default_providers()

    def _register_default_providers(self):
        """Register all built-in video source provider classes"""
        self.register(V4L2CameraSource)
        self.register(LibCameraSource)
        self.register(HDMICaptureSource)
        self.register(NetworkStreamSource)

    def register(self, provider_class: Type[VideoSourceProvider]):
        """Register a video source provider class"""
        prefix = provider_class.get_prefix()
        self._provider_classes[prefix] = provider_class
        logger.debug(f"Registered video source provider: {provider_class.__name__} with prefix '{prefix}'")

    def get_available_sources(self) -> List[Dict]:
        """
        Detect all available video sources from all providers.

        Returns:
            List of source dictionaries with capabilities
        """
        sources = []

        for prefix, provider_class in self._provider_classes.items():
            try:
                detected = provider_class.detect_sources()
                sources.extend(detected)
                logger.info(f"{provider_class.__name__}: detected {len(detected)} sources")
            except Exception as e:
                logger.error(f"Error detecting {provider_class.__name__}: {e}")

        return sources

    def get_source_by_id(self, source_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific video source.

        Args:
            source_id: Source identifier (e.g., "v4l2:/dev/video0")

        Returns:
            Source dictionary with full capabilities or None
        """
        for prefix, provider_class in self._provider_classes.items():
            if source_id.startswith(prefix):
                try:
                    # Use from_id to create instance
                    instance = provider_class.from_id(source_id)
                    if instance.is_available():
                        return instance.to_dict()
                except Exception as e:
                    logger.error(f"Error getting source {source_id}: {e}")
        return None

    def get_provider_for_source(self, source_id: str) -> Optional[VideoSourceProvider]:
        """
        Get a provider instance for a specific source.

        Args:
            source_id: Source identifier (e.g., "v4l2:/dev/video0")

        Returns:
            Provider instance or None
        """
        for prefix, provider_class in self._provider_classes.items():
            if source_id.startswith(prefix):
                try:
                    return provider_class.from_id(source_id)
                except Exception as e:
                    logger.error(f"Error creating provider for {source_id}: {e}")
        return None

    def list_video_source_providers(self) -> List[str]:
        """Get list of registered video source provider types"""
        return list(self._provider_classes.keys())

    def get_video_source(self, source_type: str) -> Optional[Type[VideoSourceProvider]]:
        """
        Get video source provider class by type.

        Args:
            source_type: Provider type/prefix (e.g., "v4l2:")

        Returns:
            Provider class or None
        """
        return self._provider_classes.get(source_type)


# Global registry instance
_registry = None


def get_video_source_registry() -> VideoSourceRegistry:
    """Get the global video source registry (singleton)"""
    global _registry
    if _registry is None:
        _registry = VideoSourceRegistry()
    return _registry


__all__ = [
    "VideoSourceProvider",
    "VideoCapabilities",
    "VideoSourceRegistry",
    "get_video_source_registry",
    "V4L2CameraSource",
    "LibCameraSource",
    "HDMICaptureSource",
    "NetworkStreamSource",
]
