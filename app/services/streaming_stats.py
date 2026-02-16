"""
Streaming Statistics Monitor
Handles GStreamer pipeline probes and statistics broadcasting
"""

import logging
import time
from typing import Optional, Callable

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


class StreamingStatsMonitor:
    """
    Independent statistics monitor for GStreamer pipelines.
    Tracks FPS, bitrate, and other streaming metrics.
    """

    def __init__(self, broadcast_callback: Optional[Callable] = None):
        """
        Initialize the stats monitor.

        Args:
            broadcast_callback: Function to call with updated stats
        """
        self.broadcast_callback = broadcast_callback
        self.last_time = time.time()
        self.frame_count = 0
        self.byte_count = 0
        self.current_stats = {
            "fps": 0.0,
            "bitrate": 0.0,
            "frames_total": 0,
            "bytes_total": 0,
        }

    def create_probe_callback(self):
        """
        Create a GStreamer probe callback for monitoring pipeline data.

        Returns:
            Callable probe function
        """

        def probe_callback(pad, info):
            """GStreamer probe callback"""
            try:
                buffer = info.get_buffer()
                if buffer:
                    self.frame_count += 1
                    self.byte_count += buffer.get_size()

                    current_time = time.time()
                    time_diff = current_time - self.last_time

                    # Update stats every second
                    if time_diff >= 1.0:
                        fps = self.frame_count / time_diff
                        bitrate = (self.byte_count * 8) / (time_diff * 1000)  # kbps

                        self.current_stats = {
                            "fps": round(fps, 2),
                            "bitrate": round(bitrate, 2),
                            "frames_total": self.current_stats["frames_total"] + self.frame_count,
                            "bytes_total": self.current_stats["bytes_total"] + self.byte_count,
                        }

                        # Broadcast stats if callback is set
                        if self.broadcast_callback:
                            try:
                                self.broadcast_callback(self.current_stats)
                            except Exception as e:
                                logger.error(f"Error broadcasting stats: {e}")

                        # Reset counters
                        self.frame_count = 0
                        self.byte_count = 0
                        self.last_time = current_time

            except Exception as e:
                logger.error(f"Error in probe callback: {e}")

            return Gst.PadProbeReturn.OK

        return probe_callback

    def attach_to_element(self, element, pad_name: str = "src"):
        """
        Attach stats probe to a pipeline element.

        Args:
            element: GStreamer element
            pad_name: Pad name to attach to (default: 'src')

        Returns:
            Probe ID or None if failed
        """
        try:
            pad = element.get_static_pad(pad_name)
            if not pad:
                logger.error(f"Failed to get pad '{pad_name}' from element")
                return None

            probe_id = pad.add_probe(Gst.PadProbeType.BUFFER, self.create_probe_callback())
            logger.info(f"Attached stats probe to {element.get_name()}:{pad_name}")
            return probe_id

        except Exception as e:
            logger.error(f"Failed to attach stats probe: {e}")
            return None

    def attach_to_pipeline(self, pipeline, element_name: str, pad_name: str = "src"):
        """
        Attach stats probe to a named element in a pipeline.

        Args:
            pipeline: GStreamer pipeline
            element_name: Name of element to monitor
            pad_name: Pad name (default: 'src')

        Returns:
            Probe ID or None if failed
        """
        try:
            element = pipeline.get_by_name(element_name)
            if not element:
                logger.error(f"Element '{element_name}' not found in pipeline")
                return None

            return self.attach_to_element(element, pad_name)

        except Exception as e:
            logger.error(f"Failed to attach stats probe to pipeline: {e}")
            return None

    def get_current_stats(self) -> dict:
        """
        Get current statistics snapshot.

        Returns:
            Dictionary with current stats
        """
        return self.current_stats.copy()

    def reset_stats(self):
        """Reset all statistics counters"""
        self.frame_count = 0
        self.byte_count = 0
        self.last_time = time.time()
        self.current_stats = {
            "fps": 0.0,
            "bitrate": 0.0,
            "frames_total": 0,
            "bytes_total": 0,
        }
        logger.info("Statistics reset")

    def set_broadcast_callback(self, callback: Callable):
        """
        Set or update the broadcast callback.

        Args:
            callback: Function to call with updated stats
        """
        self.broadcast_callback = callback
