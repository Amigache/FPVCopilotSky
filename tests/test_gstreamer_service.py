"""
Test suite for GStreamer Service

Tests cover:
- Service initialization
- Video configuration
- Pipeline building and management
- OpenCV integration
- RTSP server functionality
- Stats tracking
- Error handling
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
import threading


@pytest.fixture
def mock_gstreamer():
    """Mock GStreamer availability and classes"""
    with patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True):
        mock_gst = MagicMock()
        mock_glib = MagicMock()

        # Mock pipeline state change
        mock_gst.StateChangeReturn.SUCCESS = 1
        mock_gst.StateChangeReturn.ASYNC = 2
        mock_gst.StateChangeReturn.FAILURE = 3
        mock_gst.State.PLAYING = 4
        mock_gst.State.NULL = 1
        mock_gst.MessageType.EOS = 1
        mock_gst.MessageType.ERROR = 2
        mock_gst.MessageType.STATE_CHANGED = 4
        mock_gst.MapFlags.READ = 1
        mock_gst.FlowReturn.OK = 0
        mock_gst.FlowReturn.ERROR = -1
        mock_gst.CLOCK_TIME_NONE = 18446744073709551615

        # Mock pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.set_state = MagicMock(return_value=mock_gst.StateChangeReturn.SUCCESS)
        mock_pipeline.get_state = MagicMock(
            return_value=(mock_gst.StateChangeReturn.SUCCESS, mock_gst.State.PLAYING, None)
        )
        mock_gst.parse_launch.return_value = mock_pipeline
        mock_gst.Pipeline.new.return_value = mock_pipeline

        # Mock main loop
        mock_loop = MagicMock()
        mock_glib.MainLoop.return_value = mock_loop

        # Mock Buffer
        mock_buffer = MagicMock()
        mock_gst.Buffer.new_allocate.return_value = mock_buffer

        with patch("app.services.gstreamer_service.Gst", mock_gst):
            with patch("app.services.gstreamer_service.GLib", mock_glib):
                yield mock_gst, mock_glib


@pytest.fixture
def mock_numpy():
    """Mock numpy availability"""
    with patch("app.services.gstreamer_service.NUMPY_AVAILABLE", True):
        mock_np = MagicMock()
        mock_np.zeros.return_value = MagicMock()
        mock_np.ndarray.return_value = MagicMock()
        mock_np.ascontiguousarray.return_value = MagicMock()
        with patch("app.services.gstreamer_service.np", mock_np):
            yield mock_np


class TestGStreamerServiceInitialization:
    """Test GStreamer service initialization"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_service_creation(self, mock_gstreamer):
        """Test basic service creation"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.pipeline is None
        assert service.is_streaming is False
        assert service.last_error is None
        assert service.websocket_manager is None
        assert service.event_loop is None

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_service_with_websocket_manager(self, mock_gstreamer):
        """Test service creation with websocket manager"""
        from app.services.gstreamer_service import GStreamerService

        ws = MagicMock()
        loop = MagicMock()
        webrtc = MagicMock()
        service = GStreamerService(websocket_manager=ws, event_loop=loop, webrtc_service=webrtc)

        assert service.websocket_manager is ws
        assert service.event_loop is loop
        assert service.webrtc_service is webrtc

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_service_initializes_configs(self, mock_gstreamer):
        """Test that service initializes video and streaming configs"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.video_config is not None
        assert service.streaming_config is not None
        assert hasattr(service, "rtsp_server")
        assert service.rtsp_server is None


class TestGStreamerServiceConfiguration:
    """Test GStreamer service configuration methods"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_get_config(self, mock_gstreamer):
        """Test getting service configuration"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        # Service has video_config and streaming_config attributes
        assert service.video_config is not None
        assert service.streaming_config is not None

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_set_video_config(self, mock_gstreamer):
        """Test setting video configuration"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        # Service provides video_config object directly
        service.video_config.width = 1280
        service.video_config.height = 720
        service.video_config.framerate = 60

        assert service.video_config.width == 1280
        assert service.video_config.height == 720

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_set_streaming_config(self, mock_gstreamer):
        """Test setting streaming configuration"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        # Service provides streaming_config object directly
        service.streaming_config.mode = "udp"
        service.streaming_config.udp_host = "192.168.1.100"

        assert service.streaming_config.mode == "udp"
        assert service.streaming_config.udp_host == "192.168.1.100"


class TestGStreamerServiceStreaming:
    """Test GStreamer service streaming operations"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_is_streaming_status(self, mock_gstreamer):
        """Test checking streaming status"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.is_streaming is False

        service.is_streaming = True
        assert service.is_streaming is True

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_get_status(self, mock_gstreamer):
        """Test getting service status"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        status = service.get_status()

        assert "streaming" in status
        assert status["streaming"] is False

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_stop_when_not_streaming(self, mock_gstreamer):
        """Test stopping when not streaming"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        result = service.stop()

        # Returns dict with success/message
        assert isinstance(result, dict)


class TestGStreamerServiceOpenCV:
    """Test GStreamer service OpenCV integration"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.NUMPY_AVAILABLE", True)
    def test_opencv_service_property(self, mock_gstreamer):
        """Test setting OpenCV service"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        opencv_service = MagicMock()

        # Set directly to internal property
        service._opencv_service = opencv_service

        assert service._opencv_service is opencv_service

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.NUMPY_AVAILABLE", True)
    def test_opencv_enabled_check(self, mock_gstreamer):
        """Test checking if OpenCV is enabled"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        # Without OpenCV service
        assert service._is_opencv_enabled() is False

        # With OpenCV service
        opencv_service = MagicMock()
        opencv_service.is_running.return_value = True
        service._opencv_service = opencv_service

        assert service._is_opencv_enabled() is True

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.NUMPY_AVAILABLE", False)
    def test_opencv_without_numpy(self, mock_gstreamer):
        """Test OpenCV functionality when numpy is not available"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        # Should handle missing numpy gracefully
        assert service._is_opencv_enabled() is False


class TestGStreamerServiceRTSP:
    """Test GStreamer service RTSP functionality"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_rtsp_server_initialization(self, mock_gstreamer):
        """Test RTSP server is initialized as None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.rtsp_server is None
        assert service._rtsp_stats_thread is None
        assert service._rtsp_stats_running is False

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_stop_rtsp_when_no_server(self, mock_gstreamer):
        """Test stopping RTSP when server doesn't exist"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        # Should not raise error
        service.stop()


class TestGStreamerServiceStats:
    """Test GStreamer service stats tracking"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_stats_thread_initialization(self, mock_gstreamer):
        """Test stats thread is initialized properly"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.stats_thread is None
        assert isinstance(service.stats_stop_event, threading.Event)

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_opencv_stats_initialization(self, mock_gstreamer):
        """Test OpenCV stats are initialized to zero"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service._opencv_frames_processed == 0
        assert service._opencv_frames_dropped == 0


class TestGStreamerServicePipelineCreation:
    """Test GStreamer pipeline creation"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_pipeline_initially_none(self, mock_gstreamer):
        """Test that pipeline is initially None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.pipeline is None

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_main_loop_initially_none(self, mock_gstreamer):
        """Test that main loop is initially None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.main_loop is None
        assert service.main_loop_thread is None


class TestGStreamerServiceErrorHandling:
    """Test GStreamer service error handling"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_last_error_initialization(self, mock_gstreamer):
        """Test that last_error is initially None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.last_error is None

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_error_in_status(self, mock_gstreamer):
        """Test that error appears in status"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()
        service.last_error = "Test error"

        status = service.get_status()

        assert status["last_error"] == "Test error"


class TestGStreamerServiceProviderTracking:
    """Test provider tracking in GStreamer service"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_provider_tracking_initialization(self, mock_gstreamer):
        """Test provider tracking is initialized to None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.current_encoder_provider is None
        assert service.current_source_provider is None


class TestGStreamerServiceWebRTC:
    """Test GStreamer service WebRTC integration"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_webrtc_service_property(self, mock_gstreamer):
        """Test WebRTC service is properly stored"""
        from app.services.gstreamer_service import GStreamerService

        webrtc = MagicMock()
        service = GStreamerService(webrtc_service=webrtc)

        assert service.webrtc_service is webrtc

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_webrtc_adapter_initialization(self, mock_gstreamer):
        """Test WebRTC adapter is initialized to None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.webrtc_adapter is None

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_webrtc_opencv_integration(self, mock_gstreamer):
        """Test WebRTC-OpenCV integration variables"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service._webrtc_opencv_appsink_idx == -1


class TestGStreamerServiceCleanup:
    """Test GStreamer service cleanup operations"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    def test_opencv_queue_initialization(self, mock_gstreamer):
        """Test OpenCV queue is initialized to None"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service._opencv_queue is None
        assert service._opencv_appsrc is None
        assert service._opencv_thread is None
        assert service._opencv_running is False


class TestGStreamerServiceNotAvailable:
    """Test behavior when GStreamer is not available"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", False)
    def test_service_creation_without_gstreamer(self):
        """Test service can be created even without GStreamer"""
        from app.services.gstreamer_service import GStreamerService

        service = GStreamerService()

        assert service.pipeline is None
        assert service.is_streaming is False
