"""
Video API Routes — Pydantic Validation Tests

Tests the Pydantic Field validators and field_validators on the three
request models: VideoConfigRequest, StreamingConfigRequest, LivePropertyRequest.
These are the API-boundary layer of defense added in Point 5.

Note: We test models directly rather than through TestClient because the
app startup initializes hardware services that aren't available in CI.
Direct model testing is actually more precise — it validates that
Pydantic catches invalid data before it ever reaches a route handler.
"""

import pytest
from pydantic import ValidationError
from app.api.routes.video import (
    VideoConfigRequest,
    StreamingConfigRequest,
    LivePropertyRequest,
)


# ---------------------------------------------------------------------------
# VideoConfigRequest — validates POST /api/video/config/video payloads
# ---------------------------------------------------------------------------
class TestVideoConfigValidation:
    """VideoConfigRequest rejects out-of-range values with ValidationError."""

    def test_valid_video_config(self):
        req = VideoConfigRequest(
            width=1920,
            height=1080,
            framerate=30,
            codec="mjpeg",
            quality=85,
        )
        assert req.width == 1920
        assert req.codec == "mjpeg"

    def test_valid_h264_config(self):
        req = VideoConfigRequest(codec="h264", h264_bitrate=3000, gop_size=5)
        assert req.codec == "h264"
        assert req.h264_bitrate == 3000

    def test_all_none_is_valid(self):
        """All fields are optional — empty model is valid."""
        req = VideoConfigRequest()
        assert req.width is None

    # --- Out-of-range numerics → ValidationError ---
    @pytest.mark.parametrize(
        "field,bad_val",
        [
            ("width", 0),
            ("width", 8000),
            ("height", -1),
            ("height", 5000),
            ("framerate", 0),
            ("framerate", 200),
            ("quality", 0),
            ("quality", 101),
            ("h264_bitrate", 50),
            ("h264_bitrate", 60000),
            ("gop_size", 0),
            ("gop_size", 301),
        ],
    )
    def test_out_of_range_rejected(self, field, bad_val):
        with pytest.raises(ValidationError):
            VideoConfigRequest(**{field: bad_val})

    # --- Boundary values accepted ---
    @pytest.mark.parametrize(
        "field,val",
        [
            ("width", 1),
            ("width", 7680),
            ("height", 1),
            ("height", 4320),
            ("framerate", 1),
            ("framerate", 120),
            ("quality", 1),
            ("quality", 100),
            ("h264_bitrate", 100),
            ("h264_bitrate", 50000),
            ("gop_size", 1),
            ("gop_size", 300),
        ],
    )
    def test_boundary_values_accepted(self, field, val):
        req = VideoConfigRequest(**{field: val})
        assert getattr(req, field) == val

    # --- Codec whitelist ---
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
        req = VideoConfigRequest(codec=codec)
        assert req.codec == codec

    @pytest.mark.parametrize("bad_codec", ["vp9", "av1", "unknown", "H264"])
    def test_invalid_codec_rejected(self, bad_codec):
        with pytest.raises(ValidationError):
            VideoConfigRequest(codec=bad_codec)


# ---------------------------------------------------------------------------
# LivePropertyRequest — validates POST /api/video/live-update payloads
# ---------------------------------------------------------------------------
class TestLivePropertyValidation:
    """LivePropertyRequest uses Literal for property and Field for value."""

    @pytest.mark.parametrize(
        "prop",
        [
            "quality",
            "bitrate",
            "h264_bitrate",
            "gop-size",
            "gop_size",
        ],
    )
    def test_valid_properties_accepted(self, prop):
        req = LivePropertyRequest(property=prop, value=500)
        assert req.property == prop

    def test_invalid_property_rejected(self):
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="unknown_prop", value=100)

    def test_value_below_min_rejected(self):
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="quality", value=0)

    def test_value_above_max_rejected(self):
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="quality", value=50001)

    def test_missing_property_rejected(self):
        with pytest.raises(ValidationError):
            LivePropertyRequest(value=50)

    def test_missing_value_rejected(self):
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="quality")

    def test_boundary_value_1_accepted(self):
        req = LivePropertyRequest(property="quality", value=1)
        assert req.value == 1

    def test_boundary_value_50000_accepted(self):
        req = LivePropertyRequest(property="bitrate", value=50000)
        assert req.value == 50000


# ---------------------------------------------------------------------------
# StreamingConfigRequest — validates POST /api/video/config/streaming payloads
# ---------------------------------------------------------------------------
class TestStreamingConfigValidation:
    """StreamingConfigRequest validates mode, ports, IPs, URLs."""

    def test_valid_udp_config(self):
        req = StreamingConfigRequest(
            mode="udp",
            udp_host="192.168.1.100",
            udp_port=5600,
        )
        assert req.mode == "udp"
        assert req.udp_host == "192.168.1.100"

    def test_valid_multicast_config(self):
        req = StreamingConfigRequest(
            mode="multicast",
            multicast_group="239.1.1.1",
            multicast_port=5600,
            multicast_ttl=1,
        )
        assert req.mode == "multicast"

    def test_valid_rtsp_config(self):
        req = StreamingConfigRequest(
            mode="rtsp",
            rtsp_url="rtsp://10.0.0.5:8554/fpv",
            rtsp_transport="tcp",
        )
        assert req.mode == "rtsp"

    # --- Invalid mode ---
    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(mode="hls")

    # --- Port ranges ---
    @pytest.mark.parametrize("field", ["udp_port", "multicast_port"])
    def test_port_below_min_rejected(self, field):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(**{field: 1023})

    @pytest.mark.parametrize("field", ["udp_port", "multicast_port"])
    def test_port_above_max_rejected(self, field):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(**{field: 65536})

    @pytest.mark.parametrize("field", ["udp_port", "multicast_port"])
    def test_port_boundaries_accepted(self, field):
        for port in [1024, 65535]:
            req = StreamingConfigRequest(**{field: port})
            assert getattr(req, field) == port

    # --- TTL ---
    def test_ttl_below_min(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_ttl=0)

    def test_ttl_above_max(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_ttl=256)

    def test_ttl_boundaries(self):
        for ttl in [1, 255]:
            req = StreamingConfigRequest(multicast_ttl=ttl)
            assert req.multicast_ttl == ttl

    # --- IP validation ---
    def test_invalid_udp_host_rejected(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(udp_host="not-an-ip")

    def test_valid_udp_host(self):
        req = StreamingConfigRequest(udp_host="10.0.0.5")
        assert req.udp_host == "10.0.0.5"

    def test_non_multicast_group_rejected(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_group="192.168.1.1")

    def test_invalid_multicast_group_rejected(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_group="abc")

    def test_valid_multicast_group(self):
        req = StreamingConfigRequest(multicast_group="224.0.0.1")
        assert req.multicast_group == "224.0.0.1"

    # --- RTSP URL ---
    def test_invalid_rtsp_url_rejected(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(rtsp_url="http://not-rtsp")

    def test_valid_rtsp_url(self):
        req = StreamingConfigRequest(rtsp_url="rtsp://host:8554/path")
        assert req.rtsp_url == "rtsp://host:8554/path"

    # --- Transport ---
    def test_invalid_transport_rejected(self):
        with pytest.raises(ValidationError):
            StreamingConfigRequest(rtsp_transport="http")

    @pytest.mark.parametrize("transport", ["tcp", "udp"])
    def test_valid_transports(self, transport):
        req = StreamingConfigRequest(rtsp_transport=transport)
        assert req.rtsp_transport == transport
