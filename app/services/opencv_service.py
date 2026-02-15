"""
OpenCV Video Processing Service
Intercepts video stream and applies computer vision filters in real-time
"""

from __future__ import annotations

import math
import threading
import logging
from typing import Optional, Dict, Any

try:
    import cv2
    import numpy as np

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    np = None

logger = logging.getLogger(__name__)


class OpenCVService:
    """
    Service for processing video frames with OpenCV filters.
    Can be integrated into GStreamer pipeline or as standalone processor.
    """

    def __init__(self):
        self.enabled = False
        self._opencv_available = OPENCV_AVAILABLE
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV (cv2) not installed - video processing disabled")
        self.config = {
            "filter": "none",
            "osd_enabled": False,
            "edgeThreshold1": 100,
            "edgeThreshold2": 200,
            "blurKernel": 15,
            "thresholdValue": 127,
        }
        self._lock = threading.Lock()
        self._telemetry_service = None
        logger.info("OpenCV Service initialized")

    def is_available(self) -> bool:
        """Check if OpenCV is actually available (cv2 installed)"""
        return self._opencv_available

    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable OpenCV processing"""
        if enabled and not self._opencv_available:
            logger.warning("Cannot enable OpenCV - cv2 not installed")
            return False
        with self._lock:
            self.enabled = enabled and self._opencv_available
            logger.info(f"OpenCV processing {'enabled' if self.enabled else 'disabled'}")
        return self.enabled

    def is_enabled(self) -> bool:
        """Check if OpenCV processing is enabled"""
        with self._lock:
            return self.enabled

    def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update OpenCV configuration"""
        with self._lock:
            self.config.update(config)
            logger.info(f"OpenCV config updated: {self.config}")
        return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        with self._lock:
            return self.config.copy()

    def set_telemetry_service(self, telemetry_service):
        """Set telemetry service for OSD data"""
        self._telemetry_service = telemetry_service
        logger.info("Telemetry service linked to OpenCV")

    def _draw_osd(self, frame: np.ndarray, osd_enabled: bool) -> np.ndarray:
        """Draw OSD (On-Screen Display) with telemetry data

        Args:
            frame: Input frame
            osd_enabled: Whether OSD is enabled (passed to avoid re-locking)
        """
        if not OPENCV_AVAILABLE:
            return frame
        if not osd_enabled:
            return frame

        if not self._telemetry_service:
            return frame

        try:
            # Make sure frame is writable
            if not frame.flags.writeable:
                frame = frame.copy()

            # Ensure frame is C-contiguous (required for cv2.putText)
            if not frame.flags["C_CONTIGUOUS"]:
                frame = np.ascontiguousarray(frame)

            # Get telemetry data
            telemetry = self._telemetry_service.get_telemetry()

            # Get climb rate from nested speed data
            speed = telemetry.get("speed", {})
            climb_rate = speed.get("climb_rate", 0.0)

            # Get yaw from nested attitude data (radians -> degrees)
            attitude = telemetry.get("attitude", {})
            yaw_deg = math.degrees(attitude.get("yaw", 0.0))

            # Font settings
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            font_thickness = 2
            text_color = (255, 255, 255)  # White
            shadow_color = (0, 0, 0)  # Black shadow
            shadow_offset = 2

            # Position for text (top-left corner with padding)
            x = 10
            y = 30
            line_spacing = 30

            # Prepare text lines
            lines = [f"Vel. Ascenso: {climb_rate:+.1f} m/s", f"Yaw: {yaw_deg:.0f}\u00b0"]

            # Draw each line with shadow for better visibility
            for i, line in enumerate(lines):
                y_pos = y + (i * line_spacing)

                # Draw shadow
                cv2.putText(
                    frame,
                    line,
                    (x + shadow_offset, y_pos + shadow_offset),
                    font,
                    font_scale,
                    shadow_color,
                    font_thickness + 1,
                    cv2.LINE_AA,
                )

                # Draw text
                cv2.putText(frame, line, (x, y_pos), font, font_scale, text_color, font_thickness, cv2.LINE_AA)

        except Exception as e:
            logger.error(f"Error drawing OSD: {e}", exc_info=True)

        return frame

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Process a single video frame with the configured filter.

        Args:
            frame: Input frame as numpy array (BGR format)

        Returns:
            Processed frame as numpy array (BGR format)
        """
        if not OPENCV_AVAILABLE:
            return frame
        if not self.enabled or frame is None:
            return frame

        with self._lock:
            # Ensure frame is C-contiguous in memory (required for cv2 operations)
            if not frame.flags["C_CONTIGUOUS"]:
                frame = np.ascontiguousarray(frame)

            filter_type = self.config.get("filter", "none")
            osd_enabled = self.config.get("osd_enabled", False)

            if filter_type == "none":
                # Even with no filter, apply OSD if enabled
                return self._draw_osd(frame, osd_enabled)

            try:
                if filter_type == "edges":
                    # Canny edge detection
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    threshold1 = self.config.get("edgeThreshold1", 100)
                    threshold2 = self.config.get("edgeThreshold2", 200)
                    edges = cv2.Canny(gray, threshold1, threshold2)
                    # Convert back to BGR
                    processed = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

                elif filter_type == "blur":
                    # Gaussian blur
                    kernel = self.config.get("blurKernel", 15)
                    # Ensure kernel is odd
                    if kernel % 2 == 0:
                        kernel += 1
                    processed = cv2.GaussianBlur(frame, (kernel, kernel), 0)

                elif filter_type == "grayscale":
                    # Convert to grayscale
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    processed = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

                elif filter_type == "threshold":
                    # Binary threshold
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    threshold_val = self.config.get("thresholdValue", 127)
                    _, thresh = cv2.threshold(gray, threshold_val, 255, cv2.THRESH_BINARY)
                    processed = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

                elif filter_type == "contours":
                    # Find and draw contours
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    processed = frame.copy()
                    cv2.drawContours(processed, contours, -1, (0, 255, 0), 2)

                else:
                    logger.warning(f"Unknown filter type: {filter_type}")
                    processed = frame

                # Apply OSD after filter processing
                processed = self._draw_osd(processed, osd_enabled)

                return processed

            except Exception as e:
                logger.error(f"Error processing frame: {e}")
                # Try to apply OSD even if filter failed
                return self._draw_osd(frame, osd_enabled)

    def build_gstreamer_element(self) -> Optional[str]:
        """
        Build GStreamer element string for appsink/appsrc pipeline.
        This allows inserting OpenCV processing into the GStreamer pipeline.

        Returns:
            GStreamer element string or None if not enabled
        """
        if not self.enabled:
            return None

        # For GStreamer integration, we'd use:
        # videoconvert ! video/x-raw,format=BGR ! appsink + appsrc + videoconvert
        # This is a placeholder - full integration would require GStreamer Python bindings
        return "videoconvert ! video/x-raw,format=BGR"

    def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        with self._lock:
            return {"opencv_enabled": self.enabled, "opencv_version": cv2.__version__, "config": self.config.copy()}


# Global service instance
_opencv_service: Optional[OpenCVService] = None


def init_opencv_service() -> OpenCVService:
    """Initialize the global OpenCV service"""
    global _opencv_service
    if _opencv_service is None:
        _opencv_service = OpenCVService()
    return _opencv_service


def get_opencv_service() -> OpenCVService:
    """Get the global OpenCV service instance"""
    global _opencv_service
    if _opencv_service is None:
        _opencv_service = OpenCVService()
    return _opencv_service
