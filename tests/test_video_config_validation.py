"""
VideoConfig & StreamingConfig __post_init__ Validation Tests

Tests the defensive clamping and fallback logic added in Point 5.
These dataclasses are the service-layer safety net: even if bad values
bypass the Pydantic API layer, __post_init__ must keep them within
safe ranges.
"""

import pytest
from app.services.video_config import VideoConfig, StreamingConfig


# ---------------------------------------------------------------------------
# VideoConfig — clamping
# ---------------------------------------------------------------------------
class TestVideoConfigClamping:
    """Verify __post_init__ clamps every numeric field to its safe range."""

    def test_default_values(self):
        cfg = VideoConfig.__new__(VideoConfig)
        # Manually set defaults to avoid auto_detect_camera
        cfg.device = "/dev/video0"
        cfg.width = 960
        cfg.height = 720
        cfg.framerate = 30
        cfg.codec = "mjpeg"
        cfg.quality = 85
        cfg.h264_bitrate = 2000
        cfg.h264_preset = "ultrafast"
        cfg.h264_tune = "zerolatency"
        cfg.gop_size = 2
        cfg.max_latency_ms = 50
        cfg.__post_init__()
        assert cfg.width == 960
        assert cfg.height == 720
        assert cfg.framerate == 30
        assert cfg.quality == 85
        assert cfg.h264_bitrate == 2000
        assert cfg.gop_size == 2

    @pytest.mark.parametrize(
        "field,low,high,min_val,max_val",
        [
            ("width", -10, 99999, 1, 7680),
            ("height", 0, 10000, 1, 4320),
            ("framerate", -1, 500, 1, 120),
            ("quality", -5, 200, 1, 100),
            ("h264_bitrate", 0, 100000, 100, 50000),
            ("gop_size", -1, 999, 1, 300),
        ],
    )
    def test_clamp_below_and_above(self, field, low, high, min_val, max_val):
        """Values outside range are clamped to min/max."""

        def make(val):
            cfg = VideoConfig.__new__(VideoConfig)
            cfg.device = "/dev/video0"
            cfg.width = 960
            cfg.height = 720
            cfg.framerate = 30
            cfg.codec = "mjpeg"
            cfg.quality = 85
            cfg.h264_bitrate = 2000
            cfg.h264_preset = "ultrafast"
            cfg.h264_tune = "zerolatency"
            cfg.gop_size = 2
            cfg.max_latency_ms = 50
            setattr(cfg, field, val)
            cfg.__post_init__()
            return getattr(cfg, field)

        assert make(low) == min_val, f"{field}={low} should clamp to {min_val}"
        assert make(high) == max_val, f"{field}={high} should clamp to {max_val}"

    def test_boundary_values_accepted(self):
        """Exact boundary values should pass through unchanged."""
        cfg = VideoConfig.__new__(VideoConfig)
        cfg.device = "/dev/video0"
        cfg.width = 1
        cfg.height = 4320
        cfg.framerate = 120
        cfg.codec = "h264"
        cfg.quality = 1
        cfg.h264_bitrate = 100
        cfg.h264_preset = "ultrafast"
        cfg.h264_tune = "zerolatency"
        cfg.gop_size = 300
        cfg.max_latency_ms = 50
        cfg.__post_init__()
        assert cfg.width == 1
        assert cfg.height == 4320
        assert cfg.framerate == 120
        assert cfg.quality == 1
        assert cfg.h264_bitrate == 100
        assert cfg.gop_size == 300


class TestVideoConfigCodecValidation:
    """Verify codec whitelist with fallback to 'mjpeg'."""

    @pytest.mark.parametrize(
        "codec",
        [
            "mjpeg",
            "h264",
            "h264_openh264",
            "h264_hardware",
            "h264_v4l2",
        ],
    )
    def test_valid_codecs_accepted(self, codec):
        cfg = VideoConfig.__new__(VideoConfig)
        cfg.device = "/dev/video0"
        cfg.width = 960
        cfg.height = 720
        cfg.framerate = 30
        cfg.codec = codec
        cfg.quality = 85
        cfg.h264_bitrate = 2000
        cfg.h264_preset = "ultrafast"
        cfg.h264_tune = "zerolatency"
        cfg.gop_size = 2
        cfg.max_latency_ms = 50
        cfg.__post_init__()
        assert cfg.codec == codec

    @pytest.mark.parametrize("bad_codec", ["vp9", "av1", "", "H264", "MJPEG", "null"])
    def test_invalid_codecs_fallback_to_mjpeg(self, bad_codec):
        cfg = VideoConfig.__new__(VideoConfig)
        cfg.device = "/dev/video0"
        cfg.width = 960
        cfg.height = 720
        cfg.framerate = 30
        cfg.codec = bad_codec
        cfg.quality = 85
        cfg.h264_bitrate = 2000
        cfg.h264_preset = "ultrafast"
        cfg.h264_tune = "zerolatency"
        cfg.gop_size = 2
        cfg.max_latency_ms = 50
        cfg.__post_init__()
        assert cfg.codec == "mjpeg"


# ---------------------------------------------------------------------------
# StreamingConfig — clamping + validation
# ---------------------------------------------------------------------------
class TestStreamingConfigClamping:
    """Verify __post_init__ clamps ports, TTL and validates mode."""

    def test_default_values(self):
        cfg = StreamingConfig()
        assert cfg.mode == "udp"
        assert cfg.udp_port == 5600
        assert cfg.multicast_port == 5600
        assert cfg.multicast_ttl == 1

    @pytest.mark.parametrize(
        "field,low,high,min_val,max_val",
        [
            ("udp_port", 0, 70000, 1024, 65535),
            ("multicast_port", 100, 99999, 1024, 65535),
            ("multicast_ttl", -1, 500, 1, 255),
        ],
    )
    def test_clamp_ports_and_ttl(self, field, low, high, min_val, max_val):
        def make(val):
            kwargs = {field: val}
            cfg = StreamingConfig(**kwargs)
            return getattr(cfg, field)

        assert make(low) == min_val
        assert make(high) == max_val

    def test_boundary_values_ports(self):
        cfg = StreamingConfig(udp_port=1024, multicast_port=65535, multicast_ttl=255)
        assert cfg.udp_port == 1024
        assert cfg.multicast_port == 65535
        assert cfg.multicast_ttl == 255


class TestStreamingConfigModeValidation:
    """Verify mode whitelist with fallback to 'udp'."""

    @pytest.mark.parametrize("mode", ["udp", "multicast", "rtsp"])
    def test_valid_modes(self, mode):
        cfg = StreamingConfig(mode=mode)
        assert cfg.mode == mode

    @pytest.mark.parametrize("bad_mode", ["hls", "TCP", "", "webrtc"])
    def test_invalid_modes_fallback_to_udp(self, bad_mode):
        cfg = StreamingConfig(mode=bad_mode)
        assert cfg.mode == "udp"


class TestStreamingConfigTransportValidation:
    """Verify rtsp_transport whitelist with fallback to 'tcp'."""

    @pytest.mark.parametrize("transport", ["tcp", "udp"])
    def test_valid_transports(self, transport):
        cfg = StreamingConfig(rtsp_transport=transport)
        assert cfg.rtsp_transport == transport

    @pytest.mark.parametrize("bad", ["TCP", "http", ""])
    def test_invalid_transports_fallback_to_tcp(self, bad):
        cfg = StreamingConfig(rtsp_transport=bad)
        assert cfg.rtsp_transport == "tcp"


class TestStreamingConfigMulticastValidation:
    """Verify multicast_group must be a real multicast address."""

    @pytest.mark.parametrize(
        "ip",
        [
            "224.0.0.1",
            "239.255.255.255",
            "224.0.0.0",
            "239.1.1.1",
        ],
    )
    def test_valid_multicast_groups(self, ip):
        cfg = StreamingConfig(multicast_group=ip)
        assert cfg.multicast_group == ip

    @pytest.mark.parametrize(
        "bad_ip",
        [
            "192.168.1.1",  # unicast
            "10.0.0.1",  # private unicast
            "255.255.255.255",  # broadcast
            "not-an-ip",
            "300.1.1.1",
            "",
        ],
    )
    def test_invalid_multicast_falls_back(self, bad_ip):
        cfg = StreamingConfig(multicast_group=bad_ip)
        assert cfg.multicast_group == "239.1.1.1"


class TestStreamingConfigUdpHostValidation:
    """Verify udp_host must be a valid IPv4 address."""

    @pytest.mark.parametrize(
        "ip",
        [
            "192.168.1.100",
            "10.0.0.1",
            "127.0.0.1",
            "0.0.0.0",
        ],
    )
    def test_valid_hosts(self, ip):
        cfg = StreamingConfig(udp_host=ip)
        assert cfg.udp_host == ip

    @pytest.mark.parametrize(
        "bad_host",
        [
            "not-an-ip",
            "999.999.999.999",
            "abc",
            "",
        ],
    )
    def test_invalid_host_falls_back(self, bad_host):
        cfg = StreamingConfig(udp_host=bad_host)
        assert cfg.udp_host == "127.0.0.1"


class TestStreamingConfigRtspUrlValidation:
    """Verify rtsp_url must start with rtsp://."""

    def test_valid_rtsp_url(self):
        cfg = StreamingConfig(rtsp_url="rtsp://10.0.0.5:8554/live")
        assert cfg.rtsp_url == "rtsp://10.0.0.5:8554/live"

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://localhost:8554/fpv",
            "rtp://localhost:8554/fpv",
            "localhost:8554",
        ],
    )
    def test_invalid_rtsp_url_falls_back(self, bad_url):
        cfg = StreamingConfig(rtsp_url=bad_url)
        assert cfg.rtsp_url == "rtsp://localhost:8554/fpv"

    def test_empty_rtsp_url_preserved(self):
        """Empty string is falsy — __post_init__ doesn't override it."""
        cfg = StreamingConfig(rtsp_url="")
        assert cfg.rtsp_url == ""
