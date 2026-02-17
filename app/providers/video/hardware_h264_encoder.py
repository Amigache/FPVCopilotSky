"""
Hardware H.264 Encoder Provider
Detects and uses SoC hardware video encoding (V4L2 M2M, meson_venc, etc.)
"""

import subprocess
import glob
import logging
from typing import Dict
from ..base.video_encoder_provider import VideoEncoderProvider

logger = logging.getLogger(__name__)


class HardwareH264Encoder(VideoEncoderProvider):
    """
    Hardware H.264 encoder using V4L2 Memory-to-Memory (M2M) interface.

    Supports:
    - Amlogic SoCs (S905, S922, etc.) via meson_venc
    - Rockchip SoCs (RK3588, RK3399, etc.) via rkmpp
    - Allwinner SoCs (H6, H616, etc.)
    - Other SoCs with V4L2 M2M video encoding

    Benefits:
    - Ultra-low CPU usage (<10%)
    - Lower latency than software encoding
    - Higher resolution/framerate capability
    """

    def __init__(self):
        super().__init__()
        self.codec_id = "h264_hardware"
        self.display_name = "H.264 (Hardware)"
        self.codec_family = "h264"
        self.encoder_type = "hardware"
        self.gst_encoder_element = self._detect_encoder_element()
        self.rtp_payload_type = 96
        self.priority = 100  # Highest priority - hardware is always best
        self.encoder_device = self._detect_encoder_device()
        self._hw_jpegdec_available = self._check_hw_jpegdec()

    def _detect_encoder_device(self) -> str:
        """
        Detect V4L2 M2M encoder device.

        Looks for:
        - /dev/video* with H.264 encoding capability
        - Common names: meson_venc, rk_venc, etc.
        """
        try:
            devices = glob.glob("/dev/video*")

            for device in devices:
                try:
                    # Query device capabilities
                    result = subprocess.run(
                        ["v4l2-ctl", "-d", device, "--info"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )

                    if result.returncode != 0:
                        continue

                    info = result.stdout.lower()

                    # Check if it's an encoder
                    if "video output" in info or "encoder" in info or "codec" in info:
                        # Check capabilities for H.264 encoding
                        caps_result = subprocess.run(
                            ["v4l2-ctl", "-d", device, "--list-formats-out"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )

                        if "h264" in caps_result.stdout.lower() or "h.264" in caps_result.stdout.lower():
                            logger.info(f"Found hardware H.264 encoder: {device}")
                            return device

                except Exception as e:
                    logger.debug(f"Error checking {device}: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Hardware encoder detection failed: {e}")

        return ""

    @staticmethod
    def _check_hw_jpegdec() -> bool:
        """Check if v4l2jpegdec (hardware JPEG decoder) is available."""
        try:
            result = subprocess.run(["gst-inspect-1.0", "v4l2jpegdec"], capture_output=True, timeout=2)
            available = result.returncode == 0
            if available:
                logger.info("Hardware JPEG decoder (v4l2jpegdec) available for HW encoder pipeline")
            return available
        except Exception:
            return False

    def _detect_encoder_element(self) -> str:
        """
        Detect which GStreamer element to use for hardware encoding.

        Priority:
        1. v4l2h264enc - V4L2 M2M H.264 encoder (universal)
        2. mppvideoen - Rockchip MPP encoder
        3. v4l2video11h264enc - Alternative V4L2 encoder
        """
        elements_to_try = ["v4l2h264enc", "mppvideoenc", "v4l2video11h264enc"]

        for element in elements_to_try:
            try:
                result = subprocess.run(["gst-inspect-1.0", element], capture_output=True, timeout=2)
                if result.returncode == 0:
                    logger.info(f"Found hardware encoder element: {element}")
                    return element
            except Exception:
                continue

        return ""

    def is_available(self) -> bool:
        """Check if hardware H.264 encoder is available"""
        # Need both encoder element and encoder device
        if not self.gst_encoder_element:
            logger.debug("No hardware encoder GStreamer element found")
            return False

        if not self.encoder_device:
            logger.debug("No hardware encoder device found")
            return False

        logger.info(f"Hardware H.264 encoder available: {self.gst_encoder_element} on {self.encoder_device}")
        return True

    def get_capabilities(self) -> Dict:
        """Get hardware encoder capabilities"""
        return {
            "codec_id": self.codec_id,
            "display_name": self.display_name,
            "codec_family": self.codec_family,
            "encoder_type": self.encoder_type,
            "available": self.is_available(),
            "supported_resolutions": [
                (640, 480),
                (960, 720),
                (1280, 720),
                (1920, 1080),
                (3840, 2160),  # Some hardware supports 4K
            ],
            "supported_framerates": [15, 24, 25, 30, 60],
            "min_bitrate": 500,
            "max_bitrate": 20000,  # Hardware can handle much higher
            "default_bitrate": 3000,
            "quality_control": False,
            "live_quality_adjust": True,
            "latency_estimate": "ultra-low",  # ~10-30ms
            "cpu_usage": "ultra-low",  # <10%
            "priority": self.priority,
            "device": self.encoder_device,
            "gst_element": self.gst_encoder_element,
            "hw_jpegdec_available": self._hw_jpegdec_available,
            "features": {
                "gop_control": True,
                "b_frames_control": True,
                "hw_jpeg_decode": self._hw_jpegdec_available,
            },
            "description": (
                "Encoding por hardware del SoC. CPU <10%, latencia ultra-baja. "
                f"Device: {self.encoder_device}. "
                f"HW JPEG decode: {'✅' if self._hw_jpegdec_available else '❌'}"
            ),
        }

    def build_pipeline_elements(self, config: Dict) -> Dict:
        """
        Build hardware encoder pipeline elements.

        Source format handling:
        - MJPEG source → jpegdec → videoconvert → HW encoder
        - H.264 source → avdec_h264 → videoconvert → HW encoder
        - Raw source (YUYV, NV12) → videoconvert → HW encoder (no decoder needed)
        """
        try:
            if not self.is_available():
                return {"success": False, "error": "Hardware encoder not available"}

            width = config.get("width", 1920)
            height = config.get("height", 1080)
            framerate = config.get("framerate", 30)
            bitrate = config.get("bitrate", 3000)
            source_format = config.get("source_format", "image/jpeg")
            opencv_enabled = config.get("opencv_enabled", False)

            # GOP size: lower = faster error recovery (good for FPV/4G)
            # Default 30 = one keyframe per second at 30fps
            gop_size = config.get("gop_size", 30)

            elements = []

            # ── Decoder selection based on source format ──
            if "video/x-h264" in source_format:
                logger.info("HW encoder: Source is H.264, using avdec_h264 for decoding")
                elements.append({"name": "decoder", "element": "avdec_h264", "properties": {}})
            elif "image/jpeg" in source_format:
                # Prefer hardware JPEG decoder when available and OpenCV is OFF
                use_hw_jpegdec = self._hw_jpegdec_available and not opencv_enabled
                if use_hw_jpegdec:
                    logger.info("HW encoder: Using v4l2jpegdec (hardware) for MJPEG decoding")
                    elements.append({"name": "decoder", "element": "v4l2jpegdec", "properties": {}})
                else:
                    logger.info("HW encoder: Using jpegdec (software) for MJPEG decoding")
                    elements.append({"name": "decoder", "element": "jpegdec", "properties": {}})
            else:
                # Raw format (YUYV, NV12, etc.) - no decoder needed
                logger.info(f"HW encoder: Source is {source_format}, no decoder needed")

            # ── Build V4L2 M2M extra-controls string ──
            # V4L2 M2M encoders accept configuration via the extra-controls
            # property using the s-type (struct) control format.
            extra_controls_parts = [f"video_bitrate={bitrate * 1000}"]

            # GOP size → video_gop_size (keyframe interval)
            if gop_size and gop_size > 0:
                extra_controls_parts.append(f"video_gop_size={gop_size}")

            # B-frames disabled for low-latency FPV
            extra_controls_parts.append("video_b_frames=0")

            extra_controls_str = "s," + ",".join(extra_controls_parts)

            elements.extend(
                [
                    {"name": "videoconvert", "element": "videoconvert", "properties": {}},
                    {"name": "videoscale", "element": "videoscale", "properties": {}},
                    {
                        "name": "encoder_caps",
                        "element": "capsfilter",
                        "properties": {
                            "caps": f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate}/1"
                        },
                    },
                    {
                        "name": "queue_pre",
                        "element": "queue",
                        "properties": {
                            "max-size-buffers": 2,
                            "max-size-time": 0,
                            "max-size-bytes": 0,
                            "leaky": 2,
                        },
                    },
                    {
                        "name": "encoder",
                        "element": self.gst_encoder_element,
                        "properties": {"extra-controls": extra_controls_str},
                    },
                    {
                        "name": "queue_post",
                        "element": "queue",
                        "properties": {
                            "max-size-buffers": 2,
                            "max-size-time": 0,
                            "max-size-bytes": 0,
                            "leaky": 2,
                        },
                    },
                    {
                        "name": "h264parse",
                        "element": "h264parse",
                        "properties": {"config-interval": -1},  # Send SPS/PPS with every keyframe (FPV friendly)
                    },
                ]
            )

            return {
                "success": True,
                "elements": elements,
                "caps": [],
                "rtp_payload_type": self.rtp_payload_type,
                "rtp_payloader": "rtph264pay",
                "rtp_payloader_properties": {
                    "pt": self.rtp_payload_type,
                    "mtu": 1400,
                    "config-interval": -1,
                },
            }

        except Exception as e:
            logger.error(f"Failed to build hardware encoder pipeline: {e}")
            return {
                "success": False,
                "elements": [],
                "caps": [],
                "rtp_payload_type": 0,
                "rtp_payloader": "",
                "error": str(e),
            }

    def get_live_adjustable_properties(self) -> Dict[str, Dict]:
        """Hardware encoder properties that can be adjusted without pipeline restart"""
        return {
            "bitrate": {
                "element": "encoder",
                "property": "extra-controls",
                "min": 500,
                "max": 20000,
                "default": 3000,
                "description": "Bitrate H.264 hardware en kbps",
                "multiplier": 1000,  # Convert to bps
                "format": "s,video_bitrate={value}",  # V4L2 control format string
            },
            "gop-size": {
                "element": "encoder",
                "property": "extra-controls",
                "min": 1,
                "max": 300,
                "default": 30,
                "description": "Keyframe interval (frames). Menor = mejor recuperación ante pérdida de paquetes",
                "format": "s,video_gop_size={value}",
            },
        }

    def validate_config(self, config: Dict) -> Dict:
        """Validate configuration for hardware encoder"""
        errors = []
        warnings = []

        if not self.is_available():
            errors.append("Hardware encoder not available on this system")
            return {"valid": False, "errors": errors, "warnings": warnings}

        width = config.get("width", 1920)
        height = config.get("height", 1080)
        framerate = config.get("framerate", 30)
        bitrate = config.get("bitrate", 3000)

        # Check resolution
        pixel_count = width * height
        if pixel_count > 3840 * 2160:
            warnings.append("Resolution exceeds 4K, hardware may not support")

        # Check framerate
        if framerate > 60:
            warnings.append("Framerate >60fps may not be supported by hardware")

        # Check bitrate
        if bitrate < 500:
            warnings.append("Bitrate too low, quality may be poor")
        elif bitrate > 20000:
            warnings.append("Bitrate very high, may exceed hardware capability")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}
