"""
Auto-registration of video encoder providers
This module registers all available video encoders on import
"""

import logging
from .registry import get_provider_registry
from .video import MJPEGEncoder, X264Encoder, OpenH264Encoder, HardwareH264Encoder, H264PassthroughEncoder

logger = logging.getLogger(__name__)


def register_all_video_encoders():
    """Register all video encoder providers"""
    registry = get_provider_registry()

    # Register Hardware H.264 encoder (highest priority if available)
    try:
        registry.register_video_encoder("h264_hardware", HardwareH264Encoder)
        logger.info("✅ Hardware H.264 encoder registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Hardware H.264 encoder: {e}")

    # Register H.264 Passthrough encoder (very high priority for H.264 cameras)
    try:
        registry.register_video_encoder("h264_passthrough", H264PassthroughEncoder)
        logger.info("✅ H.264 Passthrough encoder registered")
    except Exception as e:
        logger.error(f"❌ Failed to register H.264 Passthrough encoder: {e}")

    # Register MJPEG encoder
    try:
        registry.register_video_encoder("mjpeg", MJPEGEncoder)
        logger.info("✅ MJPEG encoder registered")
    except Exception as e:
        logger.error(f"❌ Failed to register MJPEG encoder: {e}")

    # Register x264 H.264 encoder
    try:
        registry.register_video_encoder("h264", X264Encoder)
        logger.info("✅ x264 H.264 encoder registered")
    except Exception as e:
        logger.error(f"❌ Failed to register x264 encoder: {e}")

    # Register OpenH264 encoder
    try:
        registry.register_video_encoder("h264_openh264", OpenH264Encoder)
        logger.info("✅ OpenH264 encoder registered")
    except Exception as e:
        logger.error(f"❌ Failed to register OpenH264 encoder: {e}")

    # NOTE: Encoder availability probing (gst-inspect-1.0, v4l2-ctl) is intentionally
    # NOT triggered here. It runs as a background task after startup to avoid
    # blocking the asyncio event loop for up to several minutes on first boot.
    logger.info("Video encoder classes registered (availability probe deferred to background)")


# Auto-register on import
register_all_video_encoders()
