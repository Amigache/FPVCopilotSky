"""Tests for video Pydantic models and validators"""

import pytest
from pydantic import ValidationError

from app.api.models.video_models import (
    LivePropertyRequest,
    StreamingConfigRequest,
    VideoConfigRequest,
)


class TestVideoConfigRequest:
    """Tests for VideoConfigRequest model"""

    def test_valid_video_config(self):
        """Test creating a valid video config request"""
        config = VideoConfigRequest(
            device="/dev/video0",
            width=1920,
            height=1080,
            framerate=30,
        )
        assert config.device == "/dev/video0"
        assert config.width == 1920
        assert config.height == 1080
        assert config.framerate == 30

    def test_width_range_validation(self):
        """Test width field validation"""
        # Valid range: 1-7680
        VideoConfigRequest(width=1)
        VideoConfigRequest(width=7680)

        # Out of range
        with pytest.raises(ValidationError):
            VideoConfigRequest(width=0)
        with pytest.raises(ValidationError):
            VideoConfigRequest(width=8000)

    def test_height_range_validation(self):
        """Test height field validation"""
        # Valid range: 1-4320
        VideoConfigRequest(height=1)
        VideoConfigRequest(height=4320)

        # Out of range
        with pytest.raises(ValidationError):
            VideoConfigRequest(height=0)
        with pytest.raises(ValidationError):
            VideoConfigRequest(height=5000)

    def test_framerate_range_validation(self):
        """Test framerate field validation"""
        # Valid range: 1-120
        VideoConfigRequest(framerate=1)
        VideoConfigRequest(framerate=120)

        # Out of range
        with pytest.raises(ValidationError):
            VideoConfigRequest(framerate=0)
        with pytest.raises(ValidationError):
            VideoConfigRequest(framerate=121)

    def test_quality_range_validation(self):
        """Test quality field validation"""
        # Valid range: 1-100
        VideoConfigRequest(quality=1)
        VideoConfigRequest(quality=100)

        # Out of range
        with pytest.raises(ValidationError):
            VideoConfigRequest(quality=0)
        with pytest.raises(ValidationError):
            VideoConfigRequest(quality=101)

    def test_h264_bitrate_range_validation(self):
        """Test h264_bitrate field validation"""
        # Valid range: 100-50000
        VideoConfigRequest(h264_bitrate=100)
        VideoConfigRequest(h264_bitrate=50000)

        # Out of range
        with pytest.raises(ValidationError):
            VideoConfigRequest(h264_bitrate=50)
        with pytest.raises(ValidationError):
            VideoConfigRequest(h264_bitrate=60000)

    def test_gop_size_range_validation(self):
        """Test gop_size field validation"""
        # Valid range: 1-300
        VideoConfigRequest(gop_size=1)
        VideoConfigRequest(gop_size=300)

        # Out of range
        with pytest.raises(ValidationError):
            VideoConfigRequest(gop_size=0)
        with pytest.raises(ValidationError):
            VideoConfigRequest(gop_size=301)

    def test_codec_validation_with_known_codecs(self):
        """Test that known codecs are always accepted"""
        known_codecs = [
            "mjpeg",
            "h264",
            "h264_openh264",
            "h264_hardware",
            "h264_v4l2",
            "h264_passthrough",
        ]
        for codec in known_codecs:
            config = VideoConfigRequest(codec=codec)
            assert config.codec == codec

    def test_none_values_allowed(self):
        """Test that all fields can be None"""
        config = VideoConfigRequest()
        assert config.device is None
        assert config.width is None
        assert config.codec is None


class TestLivePropertyRequest:
    """Tests for LivePropertyRequest model"""

    def test_valid_property_update(self):
        """Test creating a valid live property request"""
        req = LivePropertyRequest(property="quality", value=50)
        assert req.property == "quality"
        assert req.value == 50

    def test_valid_properties(self):
        """Test all valid property names"""
        valid_properties = ["quality", "bitrate", "h264_bitrate", "gop-size", "gop_size"]
        for prop in valid_properties:
            req = LivePropertyRequest(property=prop, value=50)
            assert req.property == prop

    def test_invalid_property(self):
        """Test that invalid property names are rejected"""
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="invalid_property", value=50)

    def test_value_range_validation(self):
        """Test value field range validation"""
        # Valid range: 1-50000
        LivePropertyRequest(property="quality", value=1)
        LivePropertyRequest(property="quality", value=50000)

        # Out of range
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="quality", value=0)
        with pytest.raises(ValidationError):
            LivePropertyRequest(property="quality", value=50001)


class TestStreamingConfigRequest:
    """Tests for StreamingConfigRequest model"""

    def test_valid_udp_unicast_config(self):
        """Test valid UDP unicast configuration"""
        config = StreamingConfigRequest(
            mode="udp",
            udp_host="192.168.1.100",
            udp_port=5600,
        )
        assert config.mode == "udp"
        assert config.udp_host == "192.168.1.100"
        assert config.udp_port == 5600

    def test_valid_udp_port_range(self):
        """Test UDP port range validation"""
        # Valid range: 1024-65535
        StreamingConfigRequest(udp_port=1024)
        StreamingConfigRequest(udp_port=65535)

        # Out of range
        with pytest.raises(ValidationError):
            StreamingConfigRequest(udp_port=1023)
        with pytest.raises(ValidationError):
            StreamingConfigRequest(udp_port=65536)

    def test_invalid_udp_host(self):
        """Test that invalid IP addresses are rejected"""
        with pytest.raises(ValidationError):
            StreamingConfigRequest(udp_host="invalid-ip")
        with pytest.raises(ValidationError):
            StreamingConfigRequest(udp_host="256.256.256.256")

    def test_valid_multicast_group(self):
        """Test valid multicast group addresses"""
        config = StreamingConfigRequest(
            mode="multicast",
            multicast_group="224.0.0.1",
            multicast_port=5600,
            multicast_ttl=32,
        )
        assert config.multicast_group == "224.0.0.1"

    def test_invalid_multicast_group(self):
        """Test that non-multicast addresses are rejected"""
        # Valid multicast range: 224.0.0.0 - 239.255.255.255
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_group="192.168.1.1")  # Unicast address
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_group="255.255.255.255")  # Broadcast

    def test_multicast_ttl_range_validation(self):
        """Test multicast TTL range validation"""
        # Valid range: 1-255
        StreamingConfigRequest(multicast_ttl=1)
        StreamingConfigRequest(multicast_ttl=255)

        # Out of range
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_ttl=0)
        with pytest.raises(ValidationError):
            StreamingConfigRequest(multicast_ttl=256)

    def test_valid_rtsp_url(self):
        """Test valid RTSP URL"""
        config = StreamingConfigRequest(
            mode="rtsp",
            rtsp_url="rtsp://192.168.1.100:8554/fpv",
        )
        assert config.rtsp_url == "rtsp://192.168.1.100:8554/fpv"

    def test_invalid_rtsp_url(self):
        """Test that non-RTSP URLs are rejected"""
        with pytest.raises(ValidationError):
            StreamingConfigRequest(rtsp_url="http://example.com")
        with pytest.raises(ValidationError):
            StreamingConfigRequest(rtsp_url="://no-scheme.com")

    def test_empty_rtsp_url_becomes_none(self):
        """Test that empty RTSP URL becomes None"""
        config = StreamingConfigRequest(rtsp_url="")
        assert config.rtsp_url is None

    def test_valid_rtsp_transport(self):
        """Test valid RTSP transport modes"""
        config1 = StreamingConfigRequest(rtsp_transport="tcp")
        assert config1.rtsp_transport == "tcp"

        config2 = StreamingConfigRequest(rtsp_transport="udp")
        assert config2.rtsp_transport == "udp"

    def test_valid_modes(self):
        """Test all valid streaming modes"""
        valid_modes = ["udp", "multicast", "rtsp", "webrtc"]
        for mode in valid_modes:
            config = StreamingConfigRequest(mode=mode)
            assert config.mode == mode

    def test_none_values_allowed(self):
        """Test that all fields can be None"""
        config = StreamingConfigRequest()
        assert config.mode is None
        assert config.udp_host is None
        assert config.rtsp_url is None
