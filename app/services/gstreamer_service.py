"""
GStreamer Service - Refactored Version
Uses modular components for better maintainability
"""

import asyncio
import logging
from typing import Optional, Dict, Any

# Try to import GStreamer
try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    GSTREAMER_AVAILABLE = True
except (ImportError, ValueError):
    GSTREAMER_AVAILABLE = False
    Gst = None
    GLib = None

from .video_provider_manager import VideoProviderManager  # noqa: E402
from .pipeline_factory import PipelineFactory, PipelineConfig  # noqa: E402
from .streaming_stats import StreamingStatsMonitor  # noqa: E402

logger = logging.getLogger(__name__)

# Initialize GStreamer if available
if GSTREAMER_AVAILABLE:
    Gst.init(None)


class GStreamerService:
    """
    Main GStreamer service using modular architecture.
    Delegates to specialized managers for cleaner code.
    """

    def __init__(self, websocket_manager=None, event_loop=None, webrtc_service=None):
        """
        Initialize the GStreamer service.

        Args:
            websocket_manager: WebSocket manager for broadcasting
            event_loop: Asyncio event loop
            webrtc_service: WebRTC service for signaling
        """
        self.pipeline: Optional[Gst.Pipeline] = None
        self.webrtcbin: Optional[Gst.Element] = None
        self.main_loop: Optional[GLib.MainLoop] = None
        self.stats_broadcast_callback = None

        # External services
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop
        self.webrtc_service = webrtc_service

        # Initialize modular components
        self.provider_manager = VideoProviderManager()
        self.pipeline_factory = PipelineFactory(self.provider_manager)
        self.stats_monitor = StreamingStatsMonitor()

        # Streaming state
        self.is_streaming = False
        self.current_config: Optional[PipelineConfig] = None

    def set_stats_broadcast_callback(self, callback):
        """
        Set callback for broadcasting streaming statistics.

        Args:
            callback: Async function to call with stats updates
        """
        self.stats_broadcast_callback = callback
        self.stats_monitor.set_broadcast_callback(self._wrap_async_callback(callback))

    def _wrap_async_callback(self, async_callback):
        """
        Wrap async callback for use in sync context.

        Args:
            async_callback: Async function

        Returns:
            Sync wrapper function
        """

        def sync_wrapper(stats):
            if async_callback:
                try:
                    asyncio.create_task(async_callback(stats))
                except Exception as e:
                    logger.error(f"Error in stats callback: {e}")

        return sync_wrapper

    def start_webrtc_stream(
        self,
        device_path: str,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bitrate: int = 5000000,
        codec: str = "h264",
        format: str = "auto",
    ) -> bool:
        """
        Start WebRTC streaming.

        Args:
            device_path: Device path (e.g., /dev/video0)
            width: Video width
            height: Video height
            fps: Frames per second
            bitrate: Encoding bitrate
            codec: Video codec
            format: Video format (auto, YUYV, MJPEG)

        Returns:
            True if started successfully
        """
        if self.is_streaming:
            logger.warning("Already streaming, stopping current stream first")
            self.stop_stream()

        try:
            # Create pipeline configuration
            config = PipelineConfig(
                device_path=device_path,
                width=width,
                height=height,
                fps=fps,
                bitrate=bitrate,
                codec=codec,
                format=format,
            )

            # Build WebRTC pipeline
            self.pipeline = self.pipeline_factory.build_webrtc_pipeline(config)
            if not self.pipeline:
                logger.error("Failed to build WebRTC pipeline")
                return False

            # Get webrtcbin element
            self.webrtcbin = self.pipeline.get_by_name("webrtc")
            if not self.webrtcbin:
                logger.error("Failed to get webrtcbin element")
                return False

            # Attach stats monitor
            encoder_name = "encoder"  # Default encoder name in factory
            self.stats_monitor.attach_to_pipeline(self.pipeline, encoder_name)

            # Connect bus signals
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)

            # Start pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Unable to set pipeline to PLAYING state")
                return False

            self.is_streaming = True
            self.current_config = config
            logger.info(f"WebRTC stream started: {device_path} ({width}x{height}@{fps}fps)")
            return True

        except Exception as e:
            logger.error(f"Failed to start WebRTC stream: {e}")
            self.cleanup()
            return False

    def start_udp_stream(
        self,
        device_path: str,
        port: int = 5000,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bitrate: int = 5000000,
        codec: str = "h264",
        format: str = "auto",
    ) -> bool:
        """
        Start UDP streaming.

        Args:
            device_path: Device path
            port: UDP port
            width: Video width
            height: Video height
            fps: Frames per second
            bitrate: Encoding bitrate
            codec: Video codec
            format: Video format

        Returns:
            True if started successfully
        """
        if self.is_streaming:
            logger.warning("Already streaming, stopping current stream first")
            self.stop_stream()

        try:
            # Create pipeline configuration
            config = PipelineConfig(
                device_path=device_path,
                width=width,
                height=height,
                fps=fps,
                bitrate=bitrate,
                codec=codec,
                format=format,
                port=port,
            )

            # Build UDP pipeline
            self.pipeline = self.pipeline_factory.build_udp_pipeline(config)
            if not self.pipeline:
                logger.error("Failed to build UDP pipeline")
                return False

            # Attach stats monitor
            encoder_name = "encoder"
            self.stats_monitor.attach_to_pipeline(self.pipeline, encoder_name)

            # Connect bus signals
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)

            # Start pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Unable to set pipeline to PLAYING state")
                return False

            self.is_streaming = True
            self.current_config = config
            logger.info(f"UDP stream started: {device_path} on port {port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start UDP stream: {e}")
            self.cleanup()
            return False

    def start_multicast_stream(
        self,
        device_path: str,
        multicast_address: str = "239.1.1.1",
        port: int = 5000,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bitrate: int = 5000000,
        codec: str = "h264",
        format: str = "auto",
    ) -> bool:
        """
        Start multicast streaming.

        Args:
            device_path: Device path
            multicast_address: Multicast group address
            port: Multicast port
            width: Video width
            height: Video height
            fps: Frames per second
            bitrate: Encoding bitrate
            codec: Video codec
            format: Video format

        Returns:
            True if started successfully
        """
        if self.is_streaming:
            logger.warning("Already streaming, stopping current stream first")
            self.stop_stream()

        try:
            # Create pipeline configuration
            config = PipelineConfig(
                device_path=device_path,
                width=width,
                height=height,
                fps=fps,
                bitrate=bitrate,
                codec=codec,
                format=format,
                port=port,
                multicast_address=multicast_address,
            )

            # Build multicast pipeline
            self.pipeline = self.pipeline_factory.build_multicast_pipeline(config)
            if not self.pipeline:
                logger.error("Failed to build multicast pipeline")
                return False

            # Attach stats monitor
            encoder_name = "encoder"
            self.stats_monitor.attach_to_pipeline(self.pipeline, encoder_name)

            # Connect bus signals
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)

            # Start pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Unable to set pipeline to PLAYING state")
                return False

            self.is_streaming = True
            self.current_config = config
            logger.info(f"Multicast stream started: {multicast_address}:{port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start multicast stream: {e}")
            self.cleanup()
            return False

    def stop_stream(self):
        """Stop current streaming session"""
        if not self.is_streaming:
            logger.warning("No active stream to stop")
            return

        try:
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)

            self.cleanup()
            self.is_streaming = False
            self.current_config = None
            logger.info("Stream stopped")

        except Exception as e:
            logger.error(f"Error stopping stream: {e}")

    def cleanup(self):
        """Clean up resources"""
        if self.pipeline:
            bus = self.pipeline.get_bus()
            if bus:
                bus.remove_signal_watch()

            self.pipeline = None

        self.webrtcbin = None
        self.stats_monitor.reset_stats()

    def get_stream_info(self) -> Dict[str, Any]:
        """
        Get current stream information.

        Returns:
            Dictionary with stream details
        """
        if not self.is_streaming or not self.current_config:
            return {"streaming": False}

        return {
            "streaming": True,
            "device_path": self.current_config.device_path,
            "width": self.current_config.width,
            "height": self.current_config.height,
            "fps": self.current_config.fps,
            "codec": self.current_config.codec,
            "bitrate": self.current_config.bitrate,
            "stats": self.stats_monitor.get_current_stats(),
        }

    def get_available_sources(self) -> list:
        """
        Get all available video sources.

        Returns:
            List of source dictionaries
        """
        return self.provider_manager.get_available_video_sources()

    def get_available_encoders(self) -> list:
        """
        Get all available encoders.

        Returns:
            List of encoder dictionaries
        """
        return self.provider_manager.get_available_encoders()

    def get_source_info(self, device_path: str) -> Dict[str, Any]:
        """
        Get detailed information about a video source.

        Args:
            device_path: Device path

        Returns:
            Dictionary with source information
        """
        return self.provider_manager.get_provider_info(device_path)

    def _on_bus_message(self, bus, message):
        """
        Handle GStreamer bus messages.

        Args:
            bus: GStreamer bus
            message: Bus message
        """
        msg_type = message.type

        if msg_type == Gst.MessageType.EOS:
            logger.info("End-Of-Stream reached")
            self.stop_stream()

        elif msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"GStreamer error: {err.message}")
            logger.debug(f"Debug info: {debug}")
            self.stop_stream()

        elif msg_type == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"GStreamer warning: {warn.message}")
            logger.debug(f"Debug info: {debug}")

        elif msg_type == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                logger.debug(f"Pipeline state changed: {old_state.value_nick} -> {new_state.value_nick}")

    def on_negotiation_needed(self, webrtcbin):
        """
        Handle WebRTC negotiation needed signal.

        Args:
            webrtcbin: WebRTC bin element
        """
        logger.info("Negotiation needed")
        # WebRTC signaling would be implemented here
        # This is typically handled by the WebSocket signaling server

    def on_ice_candidate(self, webrtcbin, mlineindex, candidate):
        """
        Handle ICE candidate generation.

        Args:
            webrtcbin: WebRTC bin element
            mlineindex: Media line index
            candidate: ICE candidate string
        """
        logger.debug(f"ICE candidate: {candidate}")
        # ICE candidate would be sent to peer through signaling server


# Global singleton instance
_gstreamer_service: Optional[GStreamerService] = None


def get_gstreamer_service() -> Optional[GStreamerService]:
    """Get the global GStreamer service instance"""
    return _gstreamer_service


def init_gstreamer_service(websocket_manager=None, event_loop=None, webrtc_service=None) -> GStreamerService:
    """Initialize the global GStreamer service"""
    global _gstreamer_service
    _gstreamer_service = GStreamerService(websocket_manager, event_loop, webrtc_service)
    return _gstreamer_service
