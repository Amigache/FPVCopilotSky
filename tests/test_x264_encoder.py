"""
Test suite for X264 H.264 Encoder Provider

Tests cover:
- Provider initialization and configuration
- Availability checking
- Capability reporting
- Pipeline element building with various configs
- Hardware JPEG decoder detection
- Live adjustable properties
"""

import pytest
from unittest.mock import patch, MagicMock
from app.providers.video.x264_encoder import X264Encoder, _check_v4l2jpegdec


class TestX264EncoderInitialization:
    """Test X264 encoder provider initialization"""

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_initialization_creates_correct_attributes(self, mock_check):
        """Test that encoder initializes with correct attributes"""
        mock_check.return_value = True
        encoder = X264Encoder()

        assert encoder.codec_id == "h264"
        assert encoder.display_name == "H.264 (x264)"
        assert encoder.codec_family == "h264"
        assert encoder.encoder_type == "software"
        assert encoder.gst_encoder_element == "x264enc"
        assert encoder.rtp_payload_type == 96
        assert encoder.priority == 60
        assert encoder._hw_jpegdec_available is True

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_initialization_without_hw_decoder(self, mock_check):
        """Test initialization when hardware JPEG decoder is not available"""
        mock_check.return_value = False
        encoder = X264Encoder()

        assert encoder._hw_jpegdec_available is False


class TestHardwareJPEGDecoderCheck:
    """Test hardware JPEG decoder availability checking"""

    @patch("app.utils.gstreamer.subprocess.run")
    def test_v4l2jpegdec_available(self, mock_run):
        """Test when v4l2jpegdec is available"""
        # Reset caches
        import app.providers.video.x264_encoder as encoder_module
        import app.utils.gstreamer as gst_util

        encoder_module._v4l2jpegdec_available = None
        gst_util._gst_plugin_cache.pop("v4l2jpegdec", None)

        mock_run.return_value = MagicMock(returncode=0)
        result = _check_v4l2jpegdec()

        assert result is True
        mock_run.assert_called_once_with(["gst-inspect-1.0", "v4l2jpegdec"], capture_output=True, timeout=10)

    @patch("app.utils.gstreamer.subprocess.run")
    def test_v4l2jpegdec_not_available(self, mock_run):
        """Test when v4l2jpegdec is not available"""
        # Reset caches
        import app.providers.video.x264_encoder as encoder_module
        import app.utils.gstreamer as gst_util

        encoder_module._v4l2jpegdec_available = None
        gst_util._gst_plugin_cache.pop("v4l2jpegdec", None)

        mock_run.return_value = MagicMock(returncode=1)
        result = _check_v4l2jpegdec()

        assert result is False

    @patch("app.utils.gstreamer.subprocess.run")
    def test_v4l2jpegdec_check_exception(self, mock_run):
        """Test when checking v4l2jpegdec raises an exception"""
        # Reset caches
        import app.providers.video.x264_encoder as encoder_module
        import app.utils.gstreamer as gst_util

        encoder_module._v4l2jpegdec_available = None
        gst_util._gst_plugin_cache.pop("v4l2jpegdec", None)

        mock_run.side_effect = Exception("Command failed")
        result = _check_v4l2jpegdec()

        assert result is False

    @patch("app.utils.gstreamer.subprocess.run")
    def test_v4l2jpegdec_check_cached(self, mock_run):
        """Test that v4l2jpegdec check result is cached"""
        # Set cache
        import app.providers.video.x264_encoder as encoder_module

        encoder_module._v4l2jpegdec_available = True

        result = _check_v4l2jpegdec()

        assert result is True
        mock_run.assert_not_called()  # Should not call subprocess if cached


class TestX264EncoderAvailability:
    """Test X264 encoder availability checking"""

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    @patch("app.utils.gstreamer.subprocess.run")
    def test_is_available_when_x264enc_exists(self, mock_run, mock_check):
        """Test is_available returns True when x264enc is available"""
        import app.utils.gstreamer as gst_util

        gst_util._gst_plugin_cache.pop("x264enc", None)

        mock_check.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        encoder = X264Encoder()
        result = encoder.is_available()

        assert result is True
        mock_run.assert_called_once_with(["gst-inspect-1.0", "x264enc"], capture_output=True, timeout=10)

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    @patch("app.utils.gstreamer.subprocess.run")
    def test_is_available_when_x264enc_missing(self, mock_run, mock_check):
        """Test is_available returns False when x264enc is not available"""
        import app.utils.gstreamer as gst_util

        gst_util._gst_plugin_cache.pop("x264enc", None)

        mock_check.return_value = True
        mock_run.return_value = MagicMock(returncode=1)

        encoder = X264Encoder()
        result = encoder.is_available()

        assert result is False

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    @patch("app.utils.gstreamer.subprocess.run")
    def test_is_available_handles_exception(self, mock_run, mock_check):
        """Test is_available handles exceptions gracefully"""
        import app.utils.gstreamer as gst_util

        gst_util._gst_plugin_cache.pop("x264enc", None)

        mock_check.return_value = True
        mock_run.side_effect = Exception("Command failed")

        encoder = X264Encoder()
        result = encoder.is_available()

        assert result is False


class TestX264EncoderCapabilities:
    """Test X264 encoder capabilities reporting"""

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    @patch("app.utils.gstreamer.subprocess.run")
    def test_get_capabilities_returns_correct_data(self, mock_run, mock_check):
        """Test that get_capabilities returns correct encoder information"""
        import app.utils.gstreamer as gst_util

        gst_util._gst_plugin_cache.pop("x264enc", None)

        mock_check.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        encoder = X264Encoder()
        caps = encoder.get_capabilities()

        assert caps["codec_id"] == "h264"
        assert caps["display_name"] == "H.264 (x264)"
        assert caps["codec_family"] == "h264"
        assert caps["encoder_type"] == "software"
        assert caps["available"] is True
        assert caps["hw_jpegdec_available"] is True
        assert caps["supported_resolutions"] == [
            (640, 480),
            (960, 720),
            (1280, 720),
            (1920, 1080),
        ]
        assert caps["supported_framerates"] == [15, 24, 25, 30, 60]
        assert caps["min_bitrate"] == 100
        assert caps["max_bitrate"] == 10000
        assert caps["default_bitrate"] == 2000
        assert caps["quality_control"] is False
        assert caps["live_quality_adjust"] is True
        assert caps["latency_estimate"] == "medium"
        assert caps["cpu_usage"] == "medium-high"
        assert caps["priority"] == 60
        assert "description" in caps

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    @patch("app.utils.gstreamer.subprocess.run")
    def test_get_capabilities_when_not_available(self, mock_run, mock_check):
        """Test capabilities when encoder is not available"""
        import app.utils.gstreamer as gst_util

        gst_util._gst_plugin_cache.pop("x264enc", None)

        mock_check.return_value = False
        mock_run.return_value = MagicMock(returncode=1)

        encoder = X264Encoder()
        caps = encoder.get_capabilities()

        assert caps["available"] is False
        assert caps["hw_jpegdec_available"] is False


class TestX264PipelineBuilding:
    """Test X264 pipeline element building"""

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_with_default_config(self, mock_check):
        """Test building pipeline with default configuration"""
        mock_check.return_value = False
        encoder = X264Encoder()

        config = {}
        result = encoder.build_pipeline_elements(config)

        assert result["success"] is True
        assert result["rtp_payload_type"] == 96
        assert result["rtp_payloader"] == "rtph264pay"
        assert len(result["elements"]) == 8  # Updated to 8 elements
        assert result["rtp_payloader_properties"]["pt"] == 96
        assert result["rtp_payloader_properties"]["mtu"] == 1400

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_with_custom_config(self, mock_check):
        """Test building pipeline with custom configuration"""
        mock_check.return_value = False
        encoder = X264Encoder()

        config = {"width": 1280, "height": 720, "framerate": 60, "bitrate": 5000}
        result = encoder.build_pipeline_elements(config)

        assert result["success"] is True
        # Find encoder element
        encoder_elem = next(e for e in result["elements"] if e["name"] == "encoder")
        assert encoder_elem["properties"]["bitrate"] == 5000

        # Find caps element
        caps_elem = next(e for e in result["elements"] if e["name"] == "encoder_caps")
        assert "width=1280" in caps_elem["properties"]["caps"]
        assert "height=720" in caps_elem["properties"]["caps"]
        assert "framerate=60/1" in caps_elem["properties"]["caps"]

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_with_hw_decoder(self, mock_check):
        """Test pipeline uses hardware JPEG decoder when available"""
        mock_check.return_value = True
        encoder = X264Encoder()

        config = {"opencv_enabled": False}
        result = encoder.build_pipeline_elements(config)

        assert result["success"] is True
        decoder_elem = next(e for e in result["elements"] if e["name"] == "decoder")
        assert decoder_elem["element"] == "v4l2jpegdec"

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_with_opencv_enabled(self, mock_check):
        """Test pipeline uses software decoder when OpenCV is enabled"""
        mock_check.return_value = True
        encoder = X264Encoder()

        config = {"opencv_enabled": True}
        result = encoder.build_pipeline_elements(config)

        assert result["success"] is True
        decoder_elem = next(e for e in result["elements"] if e["name"] == "decoder")
        assert decoder_elem["element"] == "jpegdec"

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_without_hw_decoder(self, mock_check):
        """Test pipeline uses software decoder when HW decoder is not available"""
        mock_check.return_value = False
        encoder = X264Encoder()

        config = {"opencv_enabled": False}
        result = encoder.build_pipeline_elements(config)

        assert result["success"] is True
        decoder_elem = next(e for e in result["elements"] if e["name"] == "decoder")
        assert decoder_elem["element"] == "jpegdec"

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_handles_exceptions(self, mock_check):
        """Test pipeline building handles exceptions gracefully"""
        mock_check.return_value = True
        encoder = X264Encoder()

        # Force an error by providing invalid config type
        config = None
        result = encoder.build_pipeline_elements(config)

        assert result["success"] is False
        assert "error" in result
        assert result["elements"] == []

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_element_structure(self, mock_check):
        """Test that all required pipeline elements are present"""
        mock_check.return_value = False
        encoder = X264Encoder()

        config = {}
        result = encoder.build_pipeline_elements(config)

        element_names = [e["name"] for e in result["elements"]]
        assert "decoder" in element_names
        assert "videoconvert" in element_names
        assert "videoscale" in element_names
        assert "encoder_caps" in element_names
        assert "queue_pre" in element_names
        assert "encoder" in element_names
        assert "queue_post" in element_names
        assert "h264parse" in element_names

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_build_pipeline_encoder_properties(self, mock_check):
        """Test that encoder element has correct x264-specific properties"""
        mock_check.return_value = False
        encoder = X264Encoder()

        config = {"bitrate": 3000}
        result = encoder.build_pipeline_elements(config)

        encoder_elem = next(e for e in result["elements"] if e["name"] == "encoder")
        props = encoder_elem["properties"]

        assert props["bitrate"] == 3000
        assert props["speed-preset"] == "ultrafast"
        assert props["tune"] == 0x00000004  # zerolatency
        assert props["bframes"] == 0
        assert props["threads"] == 4
        assert props["sliced-threads"] is True
        assert props["rc-lookahead"] == 0


class TestX264LiveAdjustableProperties:
    """Test live adjustable properties for X264 encoder"""

    @patch("app.providers.video.x264_encoder._check_v4l2jpegdec")
    def test_get_live_adjustable_properties(self, mock_check):
        """Test that bitrate can be adjusted live"""
        mock_check.return_value = True
        encoder = X264Encoder()

        props = encoder.get_live_adjustable_properties()

        assert "bitrate" in props
        assert props["bitrate"]["element"] == "encoder"
        assert props["bitrate"]["property"] == "bitrate"
        assert props["bitrate"]["min"] == 100
        assert props["bitrate"]["max"] == 10000
        assert props["bitrate"]["default"] == 2000
        assert "description" in props["bitrate"]
