"""
Video Provider Manager
Handles provider detection, instantiation, and pipeline integration
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class VideoProviderManager:
    """
    Centralized manager for video source and encoder providers.
    Eliminates code duplication across different pipeline builders.
    """

    def __init__(self):
        """Initialize the provider manager"""
        self.video_registry = None
        self.encoder_registry = None
        self._initialize_registries()

    def _initialize_registries(self):
        """Lazy initialization of provider registries"""
        try:
            from app.providers.video_source import get_video_source_registry
            from app.providers.registry import get_provider_registry

            self.video_registry = get_video_source_registry()
            self.encoder_registry = get_provider_registry()
        except Exception as e:
            logger.error(f"Failed to initialize provider registries: {e}")

    def get_video_source_provider(self, device_path: str):
        """
        Find and return the appropriate video source provider for a device.

        Args:
            device_path: Device path (e.g., /dev/video0)

        Returns:
            VideoSourceProvider instance or None
        """
        if not self.video_registry:
            return None

        # Try to find provider matching the device
        for source_type in self.video_registry.list_video_source_providers():
            provider_class = self.video_registry.get_video_source(source_type)
            if provider_class:
                try:
                    sources = provider_class.detect_sources()
                    for src in sources:
                        if src["device_path"] == device_path:
                            return provider_class.from_id(src["id"])
                except Exception as e:
                    logger.error(f"Error detecting sources for {source_type}: {e}")

        # Fallback to v4l2 if no provider found
        v4l2_class = self.video_registry.get_video_source("v4l2:")
        if v4l2_class:
            try:
                source_id = f"v4l2:{device_path}"
                return v4l2_class.from_id(source_id)
            except Exception as e:
                logger.error(f"Failed to create v4l2 fallback provider: {e}")

        return None

    def get_available_video_sources(self) -> list:
        """
        Get all available video sources from all providers.

        Returns:
            List of source dictionaries
        """
        if not self.video_registry:
            return []

        all_sources = []
        for source_type in self.video_registry.list_video_source_providers():
            provider_class = self.video_registry.get_video_source(source_type)
            if provider_class:
                try:
                    sources = provider_class.detect_sources()
                    all_sources.extend(sources)
                except Exception as e:
                    logger.error(f"Error getting sources for {source_type}: {e}")

        return all_sources

    def get_encoder_provider(self, codec_id: str):
        """
        Get encoder provider for a specific codec.

        Args:
            codec_id: Codec identifier (e.g., 'h264', 'mjpeg')

        Returns:
            Encoder provider instance or None
        """
        if not self.encoder_registry:
            return None

        return self.encoder_registry.get_video_encoder(codec_id)

    def get_available_encoders(self) -> list:
        """
        Get all available video encoders.

        Returns:
            List of encoder dictionaries
        """
        if not self.encoder_registry:
            return []

        return self.encoder_registry.get_available_video_encoders()

    def adapt_codec_to_board(self, requested_codec: str) -> str:
        """
        Adapt codec selection based on board capabilities.

        Args:
            requested_codec: Requested codec ID

        Returns:
            Best available codec ID for the board
        """
        try:
            from app.providers.board import BoardRegistry

            # Get detected board
            board = BoardRegistry().get_detected_board()
            if not board:
                return requested_codec

            # Get board supported codecs
            supported_board_codecs = [enc.value for enc in board.variant.video_encoders]

            # Get available encoders from provider
            available_encoders_list = self.get_available_encoders()
            available_encoders = [e["codec_id"] for e in available_encoders_list if e["available"]]

            if requested_codec in available_encoders:
                # Codec is directly available
                if requested_codec in supported_board_codecs or requested_codec == "mjpeg":
                    return requested_codec

                # Map h264 to available H.264 provider
                if requested_codec == "h264":
                    # Prefer hardware encoder if available
                    if "h264_hardware" in available_encoders:
                        print("   → Using hardware H.264 encoder")
                        return "h264_hardware"

                    # Check if board says x264 but provider is named "h264"
                    if "x264" in supported_board_codecs and "h264" in available_encoders:
                        print("   → Using software H.264 encoder (x264)")
                        return "h264"

                    # Fallback to MJPEG if no H.264
                    if "mjpeg" in available_encoders:
                        print("   ⚠️  H.264 not available, falling back to MJPEG")
                        return "mjpeg"

                # Codec not directly available
                first_available = available_encoders[0] if available_encoders else "none"
                print(f"   ⚠️  {requested_codec} not found, using first available: {first_available}")
                return available_encoders[0] if available_encoders else requested_codec

        except Exception as e:
            logger.warning(f"Failed to adapt codec to board: {e}")
            return requested_codec

    def get_provider_info(self, device_path: str) -> Dict[str, Any]:
        """
        Get comprehensive info about a video source provider.

        Args:
            device_path: Device path

        Returns:
            Dictionary with provider information
        """
        provider = self.get_video_source_provider(device_path)
        if not provider:
            return {}

        try:
            capabilities = provider.get_capabilities()
            return {
                "source_id": provider.source_id,
                "device_name": provider.device_name,
                "display_name": provider.display_name,
                "device_info": provider.device_info,
                "capabilities": capabilities.to_dict() if capabilities else None,
                "compatible_encoders": provider.get_compatible_encoders(),
            }
        except Exception as e:
            logger.error(f"Failed to get provider info: {e}")
            return {}
