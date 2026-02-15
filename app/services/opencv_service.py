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

    # OSD update rate limit (Hz) - reduces CPU load significantly
    OSD_UPDATE_RATE_HZ = 10
    OSD_UPDATE_INTERVAL = 1.0 / OSD_UPDATE_RATE_HZ

    def __init__(self):
        self.enabled = False
        self._opencv_available = OPENCV_AVAILABLE
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV (cv2) not installed - video processing disabled")
        else:
            # Enable SIMD/NEON optimizations for ARM platforms
            self._configure_opencv_optimizations()
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
        # Track last OSD state for frame skipping optimization
        self._last_osd_hash: int = 0

        # OSD caching system to reduce CPU load
        self._osd_cache: Optional[np.ndarray] = None  # Cached overlay image (BGRA)
        self._osd_cache_size: tuple = (0, 0)  # (height, width) of cached overlay
        self._osd_last_update: float = 0.0  # Timestamp of last OSD update
        self._osd_cached_values: dict = {}  # Cached telemetry values for comparison

        logger.info("OpenCV Service initialized")

    def _configure_opencv_optimizations(self):
        """Configure OpenCV for optimal performance on ARM/x86 platforms."""
        try:
            # Enable optimized code paths (NEON on ARM, SSE/AVX on x86)
            cv2.setUseOptimized(True)
            optimized = cv2.useOptimized()

            # Set thread count based on available cores (leave 1 for main pipeline)
            import os

            cpu_count = os.cpu_count() or 4
            optimal_threads = max(2, min(cpu_count - 1, 4))
            cv2.setNumThreads(optimal_threads)
            actual_threads = cv2.getNumThreads()

            # Log optimization status
            build_info = cv2.getBuildInformation()
            has_neon = "NEON" in build_info
            has_opencl = "OpenCL" in build_info and cv2.ocl.haveOpenCL()

            logger.info(
                f"OpenCV optimizations: optimized={optimized}, "
                f"threads={actual_threads}, NEON={has_neon}, OpenCL={has_opencl}"
            )

            # Enable OpenCL if available (GPU acceleration)
            if has_opencl:
                cv2.ocl.setUseOpenCL(True)
                logger.info("OpenCL GPU acceleration enabled")

        except Exception as e:
            logger.warning(f"Failed to configure OpenCV optimizations: {e}")

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

    def has_osd_changed(self) -> bool:
        """
        Check if OSD data has changed since last frame.
        Used for intelligent frame skipping during congestion.

        Returns True if:
        - OSD is enabled AND telemetry values have changed significantly
        - First frame after enabling OSD

        Returns False if:
        - OSD is disabled
        - Telemetry values are unchanged
        """
        if not self._telemetry_service:
            return False

        with self._lock:
            if not self.config.get("osd_enabled", False):
                return False

        try:
            telemetry = self._telemetry_service.get_telemetry()

            # Create a hash of relevant OSD values
            speed = telemetry.get("speed", {})
            attitude = telemetry.get("attitude", {})

            # Round values to reduce sensitivity (avoid triggering on noise)
            climb_rate = round(speed.get("climb_rate", 0.0), 1)
            yaw = round(attitude.get("yaw", 0.0), 2)

            current_hash = hash((climb_rate, yaw))

            if current_hash != self._last_osd_hash:
                self._last_osd_hash = current_hash
                return True
            return False

        except Exception:
            return False

    def _should_update_osd(self, climb_rate: float, yaw_deg: float, frame_h: int, frame_w: int) -> bool:
        """Check if OSD overlay needs to be regenerated.

        Returns True if:
        - Cache is empty or wrong size
        - Enough time has passed since last update (throttling)
        - Telemetry values have changed significantly
        """
        import time

        now = time.monotonic()

        # Check if cache exists and matches frame size
        if self._osd_cache is None or self._osd_cache_size != (frame_h, frame_w):
            return True

        # Throttle updates to OSD_UPDATE_RATE_HZ
        if now - self._osd_last_update < self.OSD_UPDATE_INTERVAL:
            return False

        # Check if values changed significantly
        cached = self._osd_cached_values
        if not cached:
            return True

        # Only update if values changed enough (reduce noise sensitivity)
        climb_changed = abs(cached.get("climb_rate", 0) - climb_rate) > 0.05
        yaw_changed = abs(cached.get("yaw_deg", 0) - yaw_deg) > 0.5

        return climb_changed or yaw_changed

    def _render_osd_overlay(self, frame_h: int, frame_w: int, climb_rate: float, yaw_deg: float) -> np.ndarray:
        """Render OSD text onto a transparent overlay image (BGRA).

        This is called only when OSD needs to update, not every frame.
        """
        import time

        # Create transparent overlay (BGRA with alpha channel)
        overlay = np.zeros((frame_h, frame_w, 4), dtype=np.uint8)

        # Font settings - use LINE_8 instead of LINE_AA for better performance
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        font_thickness = 2
        text_color_bgra = (255, 255, 255, 255)  # White, opaque
        shadow_color_bgra = (0, 0, 0, 200)  # Black shadow, semi-transparent
        shadow_offset = 2

        # Position for text
        x = 10
        y = 30
        line_spacing = 30

        # Prepare text lines
        lines = [f"Vel. Ascenso: {climb_rate:+.1f} m/s", f"Yaw: {yaw_deg:.0f}\u00b0"]

        # Draw each line with shadow
        for i, line in enumerate(lines):
            y_pos = y + (i * line_spacing)

            # Draw shadow first (LINE_8 is faster than LINE_AA)
            cv2.putText(
                overlay,
                line,
                (x + shadow_offset, y_pos + shadow_offset),
                font,
                font_scale,
                shadow_color_bgra,
                font_thickness + 1,
                cv2.LINE_8,
            )

            # Draw text on top
            cv2.putText(overlay, line, (x, y_pos), font, font_scale, text_color_bgra, font_thickness, cv2.LINE_8)

        # Update cache metadata
        self._osd_last_update = time.monotonic()
        self._osd_cached_values = {"climb_rate": climb_rate, "yaw_deg": yaw_deg}
        self._osd_cache_size = (frame_h, frame_w)

        return overlay

    def _blend_osd_fast(self, frame: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Fast alpha blending of OSD overlay onto frame.

        Uses NumPy vectorized operations instead of per-pixel blending.
        Only blends non-zero pixels from the overlay.
        """
        # Get alpha channel and create mask of non-transparent pixels
        alpha = overlay[:, :, 3]
        mask = alpha > 0

        if not np.any(mask):
            return frame

        # Make frame writable if needed
        if not frame.flags.writeable:
            frame = frame.copy()

        # Extract BGR from overlay
        overlay_bgr = overlay[:, :, :3]

        # Blend only where alpha > 0 (vectorized)
        # Simple blend: frame[mask] = overlay_bgr[mask] works for opaque overlay
        # For semi-transparent: weighted blend
        alpha_f = alpha[mask].astype(np.float32) / 255.0
        alpha_f = alpha_f[:, np.newaxis]  # Shape for broadcasting

        frame[mask] = (
            alpha_f * overlay_bgr[mask].astype(np.float32) + (1.0 - alpha_f) * frame[mask].astype(np.float32)
        ).astype(np.uint8)

        return frame

    def _draw_osd(self, frame: np.ndarray, osd_enabled: bool) -> np.ndarray:
        """Draw OSD (On-Screen Display) with telemetry data.

        Uses cached overlay for performance - only regenerates when telemetry changes.
        Updates at most OSD_UPDATE_RATE_HZ times per second.

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
            frame_h, frame_w = frame.shape[:2]

            # Get telemetry data
            telemetry = self._telemetry_service.get_telemetry()

            # Get climb rate from nested speed data
            speed = telemetry.get("speed", {})
            climb_rate = speed.get("climb_rate", 0.0)

            # Get yaw from nested attitude data (radians -> degrees)
            attitude = telemetry.get("attitude", {})
            yaw_deg = math.degrees(attitude.get("yaw", 0.0))

            # Check if we need to regenerate the OSD overlay
            if self._should_update_osd(climb_rate, yaw_deg, frame_h, frame_w):
                self._osd_cache = self._render_osd_overlay(frame_h, frame_w, climb_rate, yaw_deg)

            # Fast blend cached overlay onto frame
            if self._osd_cache is not None:
                frame = self._blend_osd_fast(frame, self._osd_cache)

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
