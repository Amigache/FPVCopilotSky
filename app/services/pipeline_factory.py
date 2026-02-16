"""
GStreamer Pipeline Factory
Builds specialized pipelines for different streaming modes
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import GStreamer
try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    GSTREAMER_AVAILABLE = True
except (ImportError, ValueError):
    GSTREAMER_AVAILABLE = False
    Gst = None


@dataclass
class PipelineConfig:
    """Configuration container for pipeline building"""

    device_path: str
    width: int = 1920
    height: int = 1080
    fps: int = 30
    bitrate: int = 5000000
    codec: str = "h264"
    format: str = "auto"
    port: int = 8554
    multicast_address: str = "239.1.1.1"
    webrtc_peer_id: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


class PipelineFactory:
    """
    Factory for creating GStreamer pipelines for different use cases.
    Separates pipeline construction logic from service management.
    """

    def __init__(self, provider_manager):
        """
        Initialize the pipeline factory.

        Args:
            provider_manager: VideoProviderManager instance
        """
        self.provider_manager = provider_manager

    def build_webrtc_pipeline(self, config: PipelineConfig) -> Optional[Gst.Pipeline]:
        """
        Build a WebRTC streaming pipeline.

        Args:
            config: Pipeline configuration

        Returns:
            Configured pipeline or None if failed
        """
        try:
            pipeline = Gst.Pipeline.new("webrtc-pipeline")

            # Get video source provider
            provider = self.provider_manager.get_video_source_provider(config.device_path)
            if not provider:
                logger.error(f"No provider found for {config.device_path}")
                return None

            # Source element
            source_bin = self._create_source_bin(provider, config)
            if not source_bin:
                return None

            pipeline.add(source_bin)

            # Encoder
            encoder = self._create_encoder(config.codec, config)
            if not encoder:
                return None

            # RTP payloader
            payloader = self._create_rtp_payloader(config.codec)
            if not payloader:
                return None

            # WebRTC bin
            webrtcbin = Gst.ElementFactory.make("webrtcbin", "webrtc")
            if not webrtcbin:
                logger.error("Failed to create webrtcbin element")
                return None

            # Add elements to pipeline
            pipeline.add(encoder)
            pipeline.add(payloader)
            pipeline.add(webrtcbin)

            # Link elements
            if not source_bin.link(encoder):
                logger.error("Failed to link source to encoder")
                return None

            if not encoder.link(payloader):
                logger.error("Failed to link encoder to payloader")
                return None

            if not payloader.link(webrtcbin):
                logger.error("Failed to link payloader to webrtcbin")
                return None

            logger.info("WebRTC pipeline built successfully")
            return pipeline

        except Exception as e:
            logger.error(f"Failed to build WebRTC pipeline: {e}")
            return None

    def build_udp_pipeline(self, config: PipelineConfig) -> Optional[Gst.Pipeline]:
        """
        Build a UDP streaming pipeline.

        Args:
            config: Pipeline configuration

        Returns:
            Configured pipeline or None if failed
        """
        try:
            pipeline = Gst.Pipeline.new("udp-pipeline")

            # Get video source provider
            provider = self.provider_manager.get_video_source_provider(config.device_path)
            if not provider:
                logger.error(f"No provider found for {config.device_path}")
                return None

            # Source element
            source_bin = self._create_source_bin(provider, config)
            if not source_bin:
                return None

            pipeline.add(source_bin)

            # Encoder
            encoder = self._create_encoder(config.codec, config)
            if not encoder:
                return None

            # RTP payloader
            payloader = self._create_rtp_payloader(config.codec)
            if not payloader:
                return None

            # UDP sink
            udpsink = Gst.ElementFactory.make("udpsink", "udpsink")
            if not udpsink:
                logger.error("Failed to create udpsink element")
                return None

            udpsink.set_property("host", "127.0.0.1")
            udpsink.set_property("port", config.port)

            # Add elements to pipeline
            pipeline.add(encoder)
            pipeline.add(payloader)
            pipeline.add(udpsink)

            # Link elements
            if not source_bin.link(encoder):
                logger.error("Failed to link source to encoder")
                return None

            if not encoder.link(payloader):
                logger.error("Failed to link encoder to payloader")
                return None

            if not payloader.link(udpsink):
                logger.error("Failed to link payloader to udpsink")
                return None

            logger.info("UDP pipeline built successfully")
            return pipeline

        except Exception as e:
            logger.error(f"Failed to build UDP pipeline: {e}")
            return None

    def build_multicast_pipeline(self, config: PipelineConfig) -> Optional[Gst.Pipeline]:
        """
        Build a multicast streaming pipeline.

        Args:
            config: Pipeline configuration

        Returns:
            Configured pipeline or None if failed
        """
        try:
            pipeline = Gst.Pipeline.new("multicast-pipeline")

            # Get video source provider
            provider = self.provider_manager.get_video_source_provider(config.device_path)
            if not provider:
                logger.error(f"No provider found for {config.device_path}")
                return None

            # Source element
            source_bin = self._create_source_bin(provider, config)
            if not source_bin:
                return None

            pipeline.add(source_bin)

            # Encoder
            encoder = self._create_encoder(config.codec, config)
            if not encoder:
                return None

            # RTP payloader
            payloader = self._create_rtp_payloader(config.codec)
            if not payloader:
                return None

            # Multicast UDP sink
            udpsink = Gst.ElementFactory.make("udpsink", "multicast-sink")
            if not udpsink:
                logger.error("Failed to create udpsink element")
                return None

            udpsink.set_property("host", config.multicast_address)
            udpsink.set_property("port", config.port)
            udpsink.set_property("auto-multicast", True)

            # Add elements to pipeline
            pipeline.add(encoder)
            pipeline.add(payloader)
            pipeline.add(udpsink)

            # Link elements
            if not source_bin.link(encoder):
                logger.error("Failed to link source to encoder")
                return None

            if not encoder.link(payloader):
                logger.error("Failed to link encoder to payloader")
                return None

            if not payloader.link(udpsink):
                logger.error("Failed to link payloader to multicast sink")
                return None

            logger.info("Multicast pipeline built successfully")
            return pipeline

        except Exception as e:
            logger.error(f"Failed to build multicast pipeline: {e}")
            return None

    def _create_source_bin(self, provider, config: PipelineConfig) -> Optional[Gst.Element]:
        """
        Create source bin from provider.

        Args:
            provider: VideoSourceProvider instance
            config: Pipeline configuration

        Returns:
            Source bin element or None
        """
        try:
            # Get capabilities and determine format
            capabilities = provider.get_capabilities()
            if not capabilities:
                logger.error("Failed to get source capabilities")
                return None

            # Select appropriate format based on codec
            selected_format = None
            if config.codec == "mjpeg" and "MJPEG" in capabilities.formats:
                selected_format = "MJPEG"
            elif "YUYV" in capabilities.formats:
                selected_format = "YUYV"
            elif capabilities.formats:
                selected_format = capabilities.formats[0]
            else:
                logger.error("No compatible formats found")
                return None

            logger.info(f"Using format: {selected_format} for codec: {config.codec}")

            # Build source pipeline
            source_desc = provider.build_source_pipeline(
                width=config.width, height=config.height, fps=config.fps, format=selected_format
            )

            if not source_desc:
                logger.error("Failed to build source pipeline")
                return None

            # Create bin from description
            source_bin = Gst.parse_bin_from_description(source_desc, True)
            return source_bin

        except Exception as e:
            logger.error(f"Failed to create source bin: {e}")
            return None

    def _create_encoder(self, codec: str, config: PipelineConfig) -> Optional[Gst.Element]:
        """
        Create encoder element.

        Args:
            codec: Codec ID
            config: Pipeline configuration

        Returns:
            Encoder element or None
        """
        try:
            # Adapt codec to board capabilities
            codec = self.provider_manager.adapt_codec_to_board(codec)

            # Get encoder provider
            encoder_provider = self.provider_manager.get_encoder_provider(codec)
            if not encoder_provider:
                logger.error(f"No encoder provider found for codec: {codec}")
                return None

            # Build encoder
            encoder_pipeline = encoder_provider.build_encoder_pipeline(
                width=config.width, height=config.height, fps=config.fps, bitrate=config.bitrate
            )

            if not encoder_pipeline:
                logger.error("Failed to build encoder pipeline")
                return None

            # Create encoder bin
            encoder_bin = Gst.parse_bin_from_description(encoder_pipeline, True)
            return encoder_bin

        except Exception as e:
            logger.error(f"Failed to create encoder: {e}")
            return None

    def _create_rtp_payloader(self, codec: str) -> Optional[Gst.Element]:
        """
        Create appropriate RTP payloader for codec.

        Args:
            codec: Codec ID

        Returns:
            RTP payloader element or None
        """
        try:
            if codec in ["h264", "h264_hardware", "h264_openh264", "h264_passthrough"]:
                payloader = Gst.ElementFactory.make("rtph264pay", "payloader")
            elif codec == "h265":
                payloader = Gst.ElementFactory.make("rtph265pay", "payloader")
            elif codec == "mjpeg":
                payloader = Gst.ElementFactory.make("rtpjpegpay", "payloader")
            elif codec == "vp8":
                payloader = Gst.ElementFactory.make("rtpvp8pay", "payloader")
            elif codec == "vp9":
                payloader = Gst.ElementFactory.make("rtpvp9pay", "payloader")
            else:
                logger.error(f"Unsupported codec for RTP: {codec}")
                return None

            if not payloader:
                logger.error(f"Failed to create RTP payloader for {codec}")
                return None

            return payloader

        except Exception as e:
            logger.error(f"Failed to create RTP payloader: {e}")
            return None
