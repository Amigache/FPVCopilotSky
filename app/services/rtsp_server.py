"""
GStreamer RTSP Server for FPV video streaming
Provides RTSP/RTP streaming compatible with VLC, Mission Planner, and other clients
"""

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GstRtspServer, GLib  # noqa: E402
import threading  # noqa: E402
import logging  # noqa: E402

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

        # Statistics tracking
        self.stats = {"frames_sent": 0, "bytes_sent": 0, "clients_connected": 0}
        self.stats_lock = threading.Lock()

        print(f"📡 Initializing RTSP Server on port {port}, mount point: {mount_point}")

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

        # --- Encoder via provider registry ---
        encoder_str, payloader_str = self._build_encoder_string(codec, config)

        pipeline = (
            f"{source_str} ! " f"{encoder_str} ! " f"identity name=stats_counter silent=true ! " f"{payloader_str}"
        )
        return pipeline

    def _build_source_string(self, device: str, config: dict) -> str:
        """
        Build the GStreamer source portion of the pipeline using providers.
        Falls back to basic v4l2src + MJPEG if provider is unavailable.
        """
        width = config["width"]
        height = config["height"]
        framerate = config["framerate"]

        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()

            # Find which source provider handles this device
            for source_type in registry.list_video_source_providers():
                sp = registry.get_video_source(source_type)
                if not sp or not sp.is_available():
                    continue
                for src in sp.discover_sources():
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
            print("⚠️ RTSP Server already running")
            return

        print("🚀 Starting RTSP Server...")

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

        print(f"   📹 Pipeline: {pipeline_str}")

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
        print(f"✅ RTSP Server started on port {self.port}")
        print(f"   📺 Connect with: rtsp://IP:{self.port}{self.mount_point}")

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

        print(f"📊 RTSP client connected. Total: {self.stats['clients_connected']}")

    def _on_client_closed(self, client):
        """Callback when a client disconnects"""
        with self.stats_lock:
            self.stats["clients_connected"] = max(0, self.stats["clients_connected"] - 1)

        print(f"⏹️  RTSP client disconnected. Total: {self.stats['clients_connected']}")

    def stop(self):
        """Stop the RTSP server"""
        if not self.running:
            return

        print("⏹️ Stopping RTSP Server...")

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
                        print(f"   Closing RTSP session: {session_id}")
                        session_pool.remove(session_id)

                    if session_ids:
                        print(f"   Closed {len(session_ids)} RTSP client session(s)")
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

        print("✅ RTSP Server stopped")

    def is_running(self):
        """Check if server is running"""
        return self.running

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
