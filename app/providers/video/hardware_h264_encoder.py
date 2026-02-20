"""
Hardware H.264 Encoder Provider
Detects and uses SoC hardware video encoding (V4L2 M2M, meson_venc, etc.)
"""

import subprocess
import glob
import os
import logging
from typing import Dict, Optional
from ..base.video_encoder_provider import VideoEncoderProvider

logger = logging.getLogger(__name__)

# Module-level detection cache — populated on first use, shared across all instances.
# Avoids running v4l2-ctl / gst-inspect on every HardwareH264Encoder() instantiation.
_cached_encoder_element: Optional[str] = None  # "" means checked but not found
_cached_encoder_device: Optional[str] = None
_cached_hw_jpegdec: Optional[bool] = None
_detection_done: bool = False


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
        self.rtp_payload_type = 96
        self.priority = 100  # Highest priority - hardware is always best
        # Detection is lazy — populated on first call to is_available() or build_pipeline_elements()
        # This keeps __init__ fast and avoids blocking gst-inspect/v4l2-ctl during startup.
        self._detection_done = False

    # --- Lazy accessor properties -------------------------------------------------

    @property
    def gst_encoder_element(self) -> str:
        self._ensure_detected()
        return _cached_encoder_element or ""

    @gst_encoder_element.setter
    def gst_encoder_element(self, value):
        # Allow parent class to set this; we override via property
        pass

    @property
    def encoder_device(self) -> str:
        self._ensure_detected()
        return _cached_encoder_device or ""

    @encoder_device.setter
    def encoder_device(self, value):
        pass

    @property
    def _hw_jpegdec_available(self) -> bool:
        self._ensure_detected()
        return _cached_hw_jpegdec or False

    @_hw_jpegdec_available.setter
    def _hw_jpegdec_available(self, value):
        pass

    def _ensure_detected(self):
        """Populate module-level cache on first access (runs once per process)."""
        global _cached_encoder_element, _cached_encoder_device, _cached_hw_jpegdec, _detection_done
        if _detection_done:
            return
        _detection_done = True
        _cached_encoder_element = self._detect_encoder_element()
        _cached_encoder_device = self._detect_encoder_device()
        _cached_hw_jpegdec = self._check_hw_jpegdec()
        logger.info(
            f"HardwareH264Encoder detected: element={_cached_encoder_element!r} "
            f"device={_cached_encoder_device!r} hw_jpegdec={_cached_hw_jpegdec}"
        )

    def _detect_encoder_device(self) -> str:
        """
        Detect hardware encoder device.

        For MPP-based elements (mpph264enc): /dev/mpp_service is the device.
        For V4L2 M2M elements: look for /dev/video* with H.264 encoding capability.
        """
        # If MPP element was detected, the device is mpp_service
        if _cached_encoder_element in ("mpph264enc", "mppvideoenc"):
            if os.path.exists("/dev/mpp_service"):
                logger.info("MPP encoder device: /dev/mpp_service")
                return "/dev/mpp_service"
            return ""
        try:
            devices = glob.glob("/dev/video*")

            for device in devices:
                try:
                    # Query device capabilities (tight timeout — detection must not block startup)
                    result = subprocess.run(
                        ["v4l2-ctl", "-d", device, "--info"],
                        capture_output=True,
                        text=True,
                        timeout=1,
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
                            timeout=1,
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
        from app.utils.gstreamer import is_gst_element_available

        return is_gst_element_available("v4l2jpegdec")

    def _detect_encoder_element(self) -> str:
        """
        Detect which GStreamer element to use for hardware encoding.

        Priority:
        1. v4l2h264enc - V4L2 M2M H.264 encoder (universal)
        2. mppvideoen - Rockchip MPP encoder
        3. v4l2video11h264enc - Alternative V4L2 encoder
        """
        from app.utils.gstreamer import is_gst_element_available

        elements_to_try = ["mpph264enc", "mppvideoenc", "v4l2h264enc", "v4l2video11h264enc"]

        for element in elements_to_try:
            if is_gst_element_available(element):
                logger.info(f"Found hardware encoder element: {element}")
                return element

        return ""

    def is_available(self) -> bool:
        """Check if hardware H.264 encoder is available"""
        if not self.gst_encoder_element:
            logger.debug("No hardware encoder GStreamer element found")
            return False

        # MPP-based encoders (mpph264enc / mppvideoenc) use /dev/mpp_service directly —
        # they don't expose a V4L2 M2M device node, so skip the device check.
        is_mpp = self.gst_encoder_element in ("mpph264enc", "mppvideoenc")
        if not is_mpp and not self.encoder_device:
            logger.debug("No hardware encoder V4L2 device found")
            return False

        device_info = self.encoder_device or "/dev/mpp_service (MPP)"
        logger.info(f"Hardware H.264 encoder available: {self.gst_encoder_element} on {device_info}")
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

            # ── Build encoder properties ──
            # mpph264enc (gst-rkmpp): uses bps / gop properties directly
            # v4l2h264enc / mppvideoenc (V4L2 M2M): uses extra-controls string
            enc_element = self.gst_encoder_element
            is_mpp = enc_element in ("mpph264enc", "mppvideoenc")

            if is_mpp:
                # ── Level: match H.264 level cap to the requested resolution ──
                # 4K@30fps needs level 5.0 (50); 1080p@30fps fits in level 4.0 (40)
                pixel_count = width * height
                if pixel_count > 1920 * 1080 or framerate > 30:
                    mpp_level = 50  # 4K@30 or 1080p@60
                else:
                    mpp_level = 40  # 1080p@30 and below

                encoder_props = {
                    # Bitrate control — VBR lets the encoder allocate more bits to
                    # detail-rich frames (sharp edges, grass, FPV motion) without
                    # constantly hitting the CBR ceiling and raising the QP.  This
                    # is the primary reason HW encoding looks "softer" than passthrough
                    # at equal average bitrate: CBR forces the same bit budget even
                    # on a detailed I-frame that needs 3× more bits.
                    "bps": bitrate * 1000,  # target bitrate
                    "bps-max": int(bitrate * 1000 * 1.5),  # 50% burst headroom for I-frames
                    "rc-mode": 0,  # 0 = VBR, 1 = CBR
                    "gop": gop_size,
                    # Level: cap must cover the chosen resolution
                    "level": mpp_level,
                    # Profile: 'high' enables CABAC + 8×8 DCT transform
                    # (better sharpness/detail at same bitrate vs main/baseline)
                    "profile": "high",
                    # header-mode=1 (each-idr): repeat SPS/PPS inside every IDR
                    # at the encoder level, complementing the h264parse setting.
                    "header-mode": 1,
                    # QP ceiling: without this the encoder can use QP=51 on hard
                    # scenes, producing a blurry/gray look.  QP 38 is the usual
                    # "acceptable" ceiling for broadcast H.264.
                    "qp-max": 38,
                    # Prevent over-spending bits on trivially simple frames
                    "qp-min": 20,
                }
                logger.info(
                    f"HW encoder: MPP props bps={bitrate*1000} bps-max={int(bitrate*1000*1.5)} "
                    f"rc=VBR gop={gop_size} profile=high level={mpp_level} qp-max=38"
                )
            else:
                extra_controls_parts = [f"video_bitrate={bitrate * 1000}"]
                if gop_size and gop_size > 0:
                    extra_controls_parts.append(f"video_gop_size={gop_size}")
                extra_controls_parts.append("video_b_frames=0")
                encoder_props = {"extra-controls": "s," + ",".join(extra_controls_parts)}
                logger.info("HW encoder: using V4L2 M2M extra-controls")

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
                        "element": enc_element,
                        "properties": encoder_props,
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
                    "mtu": 1300,  # Conservative MTU: leaves room for DTLS/SRTP overhead
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
        is_mpp = self.gst_encoder_element in ("mpph264enc", "mppvideoenc")

        if is_mpp:
            return {
                "bitrate": {
                    "element": "encoder",
                    "property": "bps",
                    "min": 500,
                    "max": 20000,
                    "default": 3000,
                    "description": "Bitrate H.264 hardware en kbps",
                    "multiplier": 1000,
                },
                "gop-size": {
                    "element": "encoder",
                    "property": "gop",
                    "min": 1,
                    "max": 300,
                    "default": 30,
                    "description": "Keyframe interval (frames)",
                },
            }
        else:
            return {
                "bitrate": {
                    "element": "encoder",
                    "property": "extra-controls",
                    "min": 500,
                    "max": 20000,
                    "default": 3000,
                    "description": "Bitrate H.264 hardware en kbps",
                    "multiplier": 1000,
                    "format": "s,video_bitrate={value}",
                },
                "gop-size": {
                    "element": "encoder",
                    "property": "extra-controls",
                    "min": 1,
                    "max": 300,
                    "default": 30,
                    "description": "Keyframe interval (frames)",
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
