"""
GStreamer RTSP Server for FPV video streaming
Provides RTSP/RTP streaming compatible with VLC, Mission Planner, and other clients
"""

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer, GLib  # noqa: E402
import threading  # noqa: E402
import logging  # noqa: E402

try:
    import numpy as np  # noqa: E402

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # noqa: E402

logger = logging.getLogger(__name__)


class RTSPServer:
    """
    GStreamer RTSP Server that provides video streaming over RTSP/RTP
    Clients can connect using rtsp://IP:8554/fpv
    """

    def __init__(self, port=8554, mount_point="/fpv"):
        """
        Initialize RTSP server

        Args:
            port: Port to listen on (default 8554)
            mount_point: RTSP mount point path (default /fpv)
        """
        self.port = port
        self.mount_point = mount_point
        self.server = None
        self.mainloop = None
        self.thread = None
        self.running = False
        self._encoder_display_name = None  # Track which encoder was used
        self._opencv_service = None  # OpenCV service for video processing
        self._media_element = None  # Latest shared pipeline (for real stats)

        # Statistics tracking
        self.stats = {"frames_sent": 0, "bytes_sent": 0, "clients_connected": 0}
        self.stats_lock = threading.Lock()

        logger.info("Initializing RTSP server", extra={"port": port, "mount_point": mount_point})

    def set_opencv_service(self, opencv_service):
        """Set OpenCV service for video processing"""
        self._opencv_service = opencv_service
        if opencv_service:
            logger.info("OpenCV service linked to RTSP server")

    def create_pipeline_string(
        self, device="/dev/video0", codec="h264", width=960, height=720, framerate=30, bitrate=2000, quality=85
    ):
        """
        Create GStreamer pipeline launch string for RTSP streaming.
        Uses the provider registry for both source and encoder selection.

        Args:
            device: Camera device path
            codec: Video codec id (e.g. 'h264', 'mjpeg', 'h264_openh264', 'h264_hardware')
            width: Video width
            height: Video height
            framerate: Frame rate
            bitrate: H.264 bitrate in kbps
            quality: JPEG quality (for MJPEG)

        Returns:
            Pipeline launch string
        """
        config = {
            "width": width,
            "height": height,
            "framerate": framerate,
            "bitrate": bitrate,
            "quality": quality,
            "gop_size": 2,
        }

        # --- Source via provider registry ---
        source_str = self._build_source_string(device, config)

        # --- Check if OpenCV processing is enabled ---
        opencv_element = ""
        if self._opencv_service and self._opencv_service.is_enabled():
            filter_type = self._opencv_service.get_config().get("filter", "none")
            if filter_type != "none":
                logger.info(f"OpenCV processing enabled with filter: {filter_type}")
                # NOTE: This is a placeholder. Full OpenCV integration requires
                # appsink/appsrc elements with frame processing callbacks.
                # For now, we mark the pipeline with identity for future implementation.
                opencv_element = "identity name=opencv_marker ! "
                logger.warning(
                    "OpenCV filter configured but RTSP frame processing is not implemented",
                    extra={"filter_type": filter_type, "operation": "create_pipeline_string"},
                )

        # --- Encoder via provider registry ---
        encoder_str, payloader_str = self._build_encoder_string(codec, config)

        pipeline = (
            f"{source_str} ! "
            f"{opencv_element}"
            f"{encoder_str} ! "
            f"identity name=stats_counter silent=true ! "
            f"{payloader_str}"
        )
        return pipeline

    def _build_source_string(self, device: str, config: dict) -> str:
        """
        Build the GStreamer source portion of the pipeline using providers.
        Uses the registry's cached discovery to avoid redundant subprocess calls.
        Falls back to basic v4l2src + MJPEG if provider is unavailable.
        """
        width = config["width"]
        height = config["height"]
        framerate = config["framerate"]

        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()

            # Find which source provider handles this device (using cache)
            for source_type in registry.list_video_source_providers():
                sp = registry.get_video_source(source_type)
                if not sp or not sp.is_available():
                    continue
                for src in registry.discover_sources_cached(source_type):
                    if src.get("device") == device:
                        result = sp.build_source_element(src["source_id"], config)
                        if result.get("success"):
                            el = result["source_element"]
                            props = " ".join(
                                f"{k}={v}"
                                for k, v in el.get("properties", {}).items()
                                if k != "device" and not isinstance(v, bool)
                            )
                            bool_props = " ".join(
                                f"{k}={'true' if v else 'false'}"
                                for k, v in el.get("properties", {}).items()
                                if isinstance(v, bool)
                            )
                            all_props = " ".join(filter(None, [props, bool_props]))
                            source_part = f"{el['element']} {all_props}".strip()

                            # Add device property for v4l2src / libcamerasrc
                            if el["element"] == "v4l2src":
                                source_part = f"v4l2src device={device} {all_props}".strip()
                            elif el["element"] == "libcamerasrc":
                                cam_name = el.get("properties", {}).get("camera-name", "0")
                                source_part = f"libcamerasrc camera-name={cam_name} do-timestamp=true"

                            caps = result.get("caps_filter", "")
                            if caps:
                                source_part += f" ! {caps}"

                            # Add post-processing elements (e.g. jpegdec)
                            for post_el in result.get("post_elements", []):
                                pe_props = " ".join(f"{k}={v}" for k, v in post_el.get("properties", {}).items())
                                source_part += f" ! {post_el['element']} {pe_props}".strip()

                            logger.info(f"RTSP source from provider: {sp.display_name}")
                            return source_part
        except Exception as e:
            logger.warning(f"Provider source lookup failed, using fallback: {e}")

        # Fallback: basic v4l2src with MJPEG
        logger.info("RTSP using fallback v4l2src + MJPEG source")
        return (
            f"v4l2src device={device} do-timestamp=true ! "
            f"image/jpeg,width={width},height={height},framerate={framerate}/1 ! "
            f"jpegdec ! videoconvert"
        )

    def _build_encoder_string(self, codec: str, config: dict) -> tuple:
        """
        Build the GStreamer encoder + RTP payloader portion using providers.
        Returns (encoder_string, payloader_string).
        Falls back to x264enc if provider is unavailable.
        """
        framerate = config["framerate"]
        bitrate = config["bitrate"]
        quality = config["quality"]

        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            provider = registry.get_video_encoder(codec)

            if provider and provider.is_available():
                result = provider.build_pipeline_elements(config)
                if result.get("success"):
                    # Build encoder elements string
                    parts = []
                    for el in result.get("elements", []):
                        el_str = el["element"]
                        for k, v in el.get("properties", {}).items():
                            if isinstance(v, bool):
                                el_str += f" {k}={'true' if v else 'false'}"
                            else:
                                el_str += f" {k}={v}"
                        parts.append(el_str)
                    for cap in result.get("caps", []):
                        parts.append(cap)

                    encoder_str = " ! ".join(parts) if parts else "videoconvert"
                    payloader = result.get("rtp_payloader", "rtph264pay")

                    # Add payloader properties for RTSP compatibility
                    if "h264" in payloader:
                        payloader_str = f"{payloader} name=pay0 pt=96 config-interval=1 aggregate-mode=zero-latency"
                    elif "jpeg" in payloader:
                        payloader_str = f"{payloader} name=pay0 pt=26"
                    else:
                        payloader_str = f"{payloader} name=pay0 pt=96"

                    self._encoder_display_name = provider.display_name
                    logger.info(f"RTSP encoder from provider: {provider.display_name}")
                    return encoder_str, payloader_str
        except Exception as e:
            logger.warning(f"Provider encoder lookup failed, using fallback: {e}")

        # Fallback: x264enc software encoder
        self._encoder_display_name = "x264enc (fallback)"
        logger.info("RTSP using fallback x264enc encoder")
        if codec == "mjpeg":
            return (f"jpegenc quality={quality}", "rtpjpegpay name=pay0 pt=26")
        return (
            f"videoconvert ! x264enc tune=zerolatency bitrate={bitrate} speed-preset=ultrafast "
            f"key-int-max={framerate * 2} threads=2 ! video/x-h264,profile=baseline",
            "rtph264pay name=pay0 pt=96 config-interval=1 aggregate-mode=zero-latency",
        )

    def start(self, device="/dev/video0", codec="h264", width=960, height=720, framerate=30, bitrate=2000, quality=85):
        """
        Start the RTSP server in a separate thread

        Args:
            device: V4L2 camera device
            codec: Video codec
            width: Video width
            height: Video height
            framerate: Frame rate
            bitrate: H.264 bitrate in kbps
            quality: JPEG quality
        """
        if self.running:
            logger.warning("RTSP server already running")
            return

        logger.info(
            "Starting RTSP server",
            extra={
                "device": device,
                "codec": codec,
                "width": width,
                "height": height,
                "framerate": framerate,
                "bitrate": bitrate,
                "quality": quality,
            },
        )

        # Create server
        self.server = GstRtspServer.RTSPServer()
        self.server.set_service(str(self.port))

        # Connect to client-connected signal to track clients
        self.server.connect("client-connected", self._on_client_connected)

        # Create factory with pipeline
        factory = GstRtspServer.RTSPMediaFactory()
        pipeline_str = self.create_pipeline_string(device, codec, width, height, framerate, bitrate, quality)
        factory.set_launch(f"( {pipeline_str} )")
        factory.set_shared(True)  # Share pipeline with multiple clients

        # Capture the shared media pipeline so we can read real stats counters
        factory.connect("media-configure", self._on_media_configure)

        logger.info("RTSP pipeline created", extra={"pipeline": pipeline_str})

        # Mount factory
        mounts = self.server.get_mount_points()
        mounts.add_factory(self.mount_point, factory)

        # Attach server to default main context
        self.server.attach(None)

        # Create main loop in separate thread
        self.mainloop = GLib.MainLoop()
        self.thread = threading.Thread(target=self._run_mainloop, daemon=True)
        self.thread.start()

        self.running = True
        logger.info(
            "RTSP server started",
            extra={
                "port": self.port,
                "mount_point": self.mount_point,
                "url_template": f"rtsp://IP:{self.port}{self.mount_point}",
            },
        )

    def _run_mainloop(self):
        """Run GLib main loop in dedicated thread"""
        try:
            self.mainloop.run()
        except Exception as e:
            logger.error(f"RTSP Server main loop error: {e}")

    def _on_client_connected(self, server, client):
        """Callback when a client connects to the RTSP server"""
        with self.stats_lock:
            self.stats["clients_connected"] += 1

        # Connect to client closed signal to track disconnections
        client.connect("closed", self._on_client_closed)

        logger.info("RTSP client connected", extra={"total_clients": self.stats["clients_connected"]})

    def _on_client_closed(self, client):
        """Callback when a client disconnects"""
        with self.stats_lock:
            self.stats["clients_connected"] = max(0, self.stats["clients_connected"] - 1)

        logger.info("RTSP client disconnected", extra={"total_clients": self.stats["clients_connected"]})

    def stop(self):
        """Stop the RTSP server"""
        if not self.running:
            return

        logger.info("Stopping RTSP server")

        # Close all active client sessions before stopping
        if self.server:
            try:
                session_pool = self.server.get_session_pool()
                if session_pool:
                    # Collect session IDs first (can't modify during iteration)
                    session_ids = []

                    def collect_session_id(session_id, session):
                        session_ids.append(session_id)
                        return True

                    session_pool.filter(collect_session_id, None)

                    # Remove all sessions (closes connections)
                    for session_id in session_ids:
                        logger.info("Closing RTSP session", extra={"session_id": session_id})
                        session_pool.remove(session_id)

                    if session_ids:
                        logger.info("Closed RTSP client sessions", extra={"count": len(session_ids)})
                        # Brief pause to allow connections to close gracefully
                        import time

                        time.sleep(0.2)
            except Exception as e:
                logger.warning(f"Error closing RTSP sessions: {e}")

        if self.mainloop:
            self.mainloop.quit()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

        # Reset stats
        with self.stats_lock:
            self.stats["clients_connected"] = 0

        self.running = False
        self.server = None
        self.mainloop = None
        self.thread = None

        logger.info("RTSP server stopped")

    def is_running(self):
        """Check if server is running"""
        return self.running

    def _on_media_configure(self, factory, media):
        """Remember the latest shared pipeline element (runs in the RTSP loop)."""
        try:
            element = media.get_element()
        except Exception as e:
            logger.debug(f"Could not get RTSP media element: {e}")
            element = None
        with self.stats_lock:
            self._media_element = element

    def get_counter_stats(self):
        """Return real (frames, bytes) from the pipeline's ``stats_counter``.

        The RTSP pipeline includes ``identity name=stats_counter``; reading its
        ``stats`` property is a cheap C-level query. Returns ``None`` when the
        media is not configured yet or the element is missing.
        """
        with self.stats_lock:
            element = self._media_element
        if not element:
            return None
        try:
            counter = element.get_by_name("stats_counter")
            if not counter:
                return None
            stats = counter.get_property("stats")
            if stats is None:
                return None
            ok_frames, frames = stats.get_uint64("num-buffers")
            ok_bytes, nbytes = stats.get_uint64("num-bytes")
            if not (ok_frames and ok_bytes):
                return None
            return int(frames), int(nbytes)
        except Exception as e:
            logger.debug(f"Could not read RTSP stats counter: {e}")
            return None

    def _find_encoder_element(self, pipeline, encoder_property):
        """Find the encoder element in the shared RTSP pipeline.

        RTSP builds its pipeline from a launch string, so element names are
        auto-generated; we locate the encoder by the property it exposes.
        """
        try:
            it = pipeline.iterate_elements()
            while True:
                result, element = it.next()
                if result != Gst.IteratorResult.OK or element is None:
                    return None
                if element.find_property(encoder_property) is None:
                    continue
                factory = element.get_factory()
                fname = factory.get_name() if factory else ""
                if "enc" in fname or "264" in fname:
                    return element
        except Exception as e:
            logger.debug(f"Encoder element scan failed: {e}")
        return None

    def update_live_property(self, property_name: str, value, codec_id=None):
        """Apply a provider-defined live property change to the RTSP pipeline."""
        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            provider = registry.get_video_encoder(codec_id or "")
            if not provider:
                return {"success": False, "message": f"No encoder provider for '{codec_id}'"}

            adjustable = provider.get_live_adjustable_properties()
            if property_name not in adjustable:
                allowed = ", ".join(adjustable.keys()) if adjustable else "none"
                return {
                    "success": False,
                    "message": f"Cannot change '{property_name}' live with {codec_id}. Allowed: {allowed}",
                }

            prop_info = adjustable[property_name]
            encoder_property = prop_info["property"]
            value = max(prop_info["min"], min(prop_info["max"], int(value)))
            actual_value = value * prop_info.get("multiplier", 1)

            with self.stats_lock:
                element = self._media_element
            if not element:
                return {"success": False, "message": "RTSP pipeline not active"}

            encoder = self._find_encoder_element(element, encoder_property)
            if not encoder:
                return {"success": False, "message": f"Encoder with '{encoder_property}' not found in RTSP pipeline"}

            encoder.set_property(encoder_property, actual_value)
            logger.info(
                "Applied RTSP live update",
                extra={"property": encoder_property, "value": value, "provider": provider.display_name},
            )
            return {
                "success": True,
                "message": f"{prop_info['description']}: {value}",
                "property": property_name,
                "value": value,
            }
        except Exception as e:
            logger.error(f"Failed to update RTSP property: {e}")
            return {"success": False, "message": f"Failed to update RTSP property: {e}"}

    def get_stats(self):
        """Get streaming statistics with real-time client count"""
        with self.stats_lock:
            stats = dict(self.stats)

        # Update client count from server session pool if server is running
        if self.server and self.running:
            try:
                session_pool = self.server.get_session_pool()
                if session_pool:
                    # Get number of active sessions
                    n_sessions = session_pool.get_n_sessions()
                    stats["clients_connected"] = n_sessions
            except Exception as e:
                logger.debug(f"Could not get session count: {e}")

        return stats

    def get_url(self, ip="localhost"):
        """Get RTSP URL for clients"""
        return f"rtsp://{ip}:{self.port}{self.mount_point}"
