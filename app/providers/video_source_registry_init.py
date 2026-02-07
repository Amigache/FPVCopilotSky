"""
Video Source Provider Auto-Registration
Automatically registers all available video source providers at import time
"""

import logging
from .registry import get_provider_registry
from .video_source import V4L2CameraSource, LibCameraSource, HDMICaptureSource, NetworkStreamSource

logger = logging.getLogger(__name__)


def register_video_sources():
    """Register all video source providers with the registry"""
    registry = get_provider_registry()
    
    # Register V4L2 camera source (USB, CSI via V4L2)
    try:
        registry.register_video_source('v4l2', V4L2CameraSource)
        logger.info("✅ Registered V4L2CameraSource")
    except Exception as e:
        logger.error(f"Failed to register V4L2CameraSource: {e}")
    
    # Register LibCamera source (CSI cameras with libcamera)
    try:
        registry.register_video_source('libcamera', LibCameraSource)
        logger.info("✅ Registered LibCameraSource")
    except Exception as e:
        logger.error(f"Failed to register LibCameraSource: {e}")
    
    # Register HDMI capture source
    try:
        registry.register_video_source('hdmi_capture', HDMICaptureSource)
        logger.info("✅ Registered HDMICaptureSource")
    except Exception as e:
        logger.error(f"Failed to register HDMICaptureSource: {e}")
    
    # Register network stream source
    try:
        registry.register_video_source('network_stream', NetworkStreamSource)
        logger.info("✅ Registered NetworkStreamSource")
    except Exception as e:
        logger.error(f"Failed to register NetworkStreamSource: {e}")


# Auto-register on import
register_video_sources()
