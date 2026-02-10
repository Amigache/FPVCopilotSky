"""
WebRTC Video Adapter

Bridges GStreamer pipeline appsink output to WebRTC service.
Captures encoded frames from the GStreamer pipeline and feeds them
into the WebRTC peer connections.
"""

import threading
import time

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    GSTREAMER_AVAILABLE = True
except (ImportError, ValueError):
    GSTREAMER_AVAILABLE = False
    Gst = None


class WebRTCVideoAdapter:
    """
    Adapter between GStreamer appsink and WebRTC service.

    Captures video frames from a GStreamer appsink element and
    provides them to connected WebRTC peers. Implements frame
    dropping and rate limiting for 4G optimization.
    """

    def __init__(self, webrtc_service):
        self.webrtc_service = webrtc_service
        self._pipeline = None
        self._appsink = None
        self._running = False
        self._frame_count = 0
        self._bytes_count = 0
        self._lock = threading.Lock()
        self._last_frame_time = 0

        # Frame rate limiting for 4G (drop frames if too fast)
        self._target_interval = 1.0 / 30  # 30fps target
        self._drop_count = 0

    def attach_to_pipeline(self, pipeline, appsink_name: str = "webrtc_appsink"):
        """
        Attach to a GStreamer pipeline's appsink element.

        Args:
            pipeline: GStreamer pipeline containing the appsink
            appsink_name: Name of the appsink element
        """
        if not GSTREAMER_AVAILABLE:
            print("⚠️ GStreamer not available for WebRTC adapter")
            return

        self._pipeline = pipeline
        self._appsink = pipeline.get_by_name(appsink_name)

        if not self._appsink:
            print(f"⚠️ appsink '{appsink_name}' not found in pipeline")
            return

        # Connect new-sample signal
        self._appsink.connect("new-sample", self._on_new_sample)
        self._running = True
        self._frame_count = 0
        self._bytes_count = 0

        print(f"✅ WebRTC adapter attached to {appsink_name}")

    def _on_new_sample(self, appsink):
        """Handle new video frame from GStreamer appsink"""
        if not self._running:
            return Gst.FlowReturn.OK

        try:
            sample = appsink.emit("pull-sample")
            if not sample:
                return Gst.FlowReturn.OK

            buffer = sample.get_buffer()
            if not buffer:
                return Gst.FlowReturn.OK

            # Rate limiting for 4G
            now = time.time()
            elapsed = now - self._last_frame_time
            if elapsed < self._target_interval * 0.8:  # Allow 20% tolerance
                self._drop_count += 1
                return Gst.FlowReturn.OK

            self._last_frame_time = now

            with self._lock:
                self._frame_count += 1
                self._bytes_count += buffer.get_size()

            # Update service stats
            if self.webrtc_service:
                self.webrtc_service.global_stats["total_frames_sent"] = self._frame_count
                self.webrtc_service.global_stats["total_bytes_sent"] = self._bytes_count

        except Exception as e:
            print(f"⚠️ WebRTC adapter frame error: {e}")

        return Gst.FlowReturn.OK

    def get_stats(self):
        """Get adapter statistics"""
        with self._lock:
            return {
                "frames_captured": self._frame_count,
                "bytes_captured": self._bytes_count,
                "frames_dropped": self._drop_count,
                "running": self._running,
            }

    def set_target_fps(self, fps: int):
        """Update target frame rate for rate limiting"""
        fps = max(1, min(60, fps))
        self._target_interval = 1.0 / fps

    def detach(self):
        """Detach from pipeline and stop capturing"""
        self._running = False
        self._appsink = None
        self._pipeline = None
        print("✅ WebRTC adapter detached")
