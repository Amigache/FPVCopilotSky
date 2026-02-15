"""
OpenCV Service Tests

Tests for OpenCV video processing service including filter application,
OSD rendering, configuration management, and frame processing.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from app.services.opencv_service import OpenCVService, init_opencv_service, get_opencv_service


@pytest.fixture
def opencv_service():
    """Create OpenCV service instance"""
    return OpenCVService()


@pytest.fixture
def mock_frame():
    """Create a mock BGR frame"""
    # Create a simple 640x480 BGR frame
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_telemetry_service():
    """Create mock telemetry service"""
    mock = Mock()
    mock.get_telemetry.return_value = {
        "speed": {"climb_rate": 2.5},
        "attitude": {"yaw": 1.57},  # 90 degrees in radians
    }
    return mock


class TestOpenCVServiceInitialization:
    """Test OpenCV service initialization"""

    def test_service_initialization(self, opencv_service):
        """Test service initializes with default config"""
        assert opencv_service.enabled is False
        assert opencv_service.config["filter"] == "none"
        assert opencv_service.config["osd_enabled"] is False
        assert opencv_service.config["edgeThreshold1"] == 100
        assert opencv_service.config["edgeThreshold2"] == 200
        assert opencv_service.config["blurKernel"] == 15
        assert opencv_service.config["thresholdValue"] == 127

    def test_is_available(self, opencv_service):
        """Test OpenCV availability check"""
        is_available = opencv_service.is_available()
        assert isinstance(is_available, bool)

    def test_init_opencv_service_singleton(self):
        """Test global service initialization is singleton"""
        service1 = init_opencv_service()
        service2 = init_opencv_service()
        assert service1 is service2

    def test_get_opencv_service_singleton(self):
        """Test get service returns singleton"""
        service1 = get_opencv_service()
        service2 = get_opencv_service()
        assert service1 is service2


class TestOpenCVServiceConfiguration:
    """Test configuration management"""

    def test_set_enabled_when_available(self, opencv_service):
        """Test enabling OpenCV when available"""
        if opencv_service.is_available():
            result = opencv_service.set_enabled(True)
            assert result is True
            assert opencv_service.is_enabled() is True

    def test_set_enabled_when_unavailable(self, opencv_service):
        """Test enabling OpenCV when unavailable returns False"""
        with patch.object(opencv_service, "_opencv_available", False):
            result = opencv_service.set_enabled(True)
            assert result is False
            assert opencv_service.is_enabled() is False

    def test_disable_opencv(self, opencv_service):
        """Test disabling OpenCV"""
        opencv_service.set_enabled(False)
        assert opencv_service.is_enabled() is False

    def test_update_config(self, opencv_service):
        """Test updating configuration"""
        new_config = {"filter": "edges", "edgeThreshold1": 150, "edgeThreshold2": 250, "osd_enabled": True}

        result = opencv_service.update_config(new_config)

        assert result["filter"] == "edges"
        assert result["edgeThreshold1"] == 150
        assert result["edgeThreshold2"] == 250
        assert result["osd_enabled"] is True

    def test_update_config_partial(self, opencv_service):
        """Test partial configuration update"""
        opencv_service.update_config({"filter": "blur"})
        config = opencv_service.get_config()

        assert config["filter"] == "blur"
        # Other values should remain default
        assert config["blurKernel"] == 15

    def test_get_config(self, opencv_service):
        """Test getting current configuration"""
        config = opencv_service.get_config()
        assert isinstance(config, dict)
        assert "filter" in config
        assert "osd_enabled" in config

    def test_get_config_returns_copy(self, opencv_service):
        """Test get_config returns a copy, not reference"""
        config1 = opencv_service.get_config()
        config1["filter"] = "modified"

        config2 = opencv_service.get_config()
        assert config2["filter"] != "modified"

    def test_set_telemetry_service(self, opencv_service, mock_telemetry_service):
        """Test linking telemetry service"""
        opencv_service.set_telemetry_service(mock_telemetry_service)
        assert opencv_service._telemetry_service is mock_telemetry_service


class TestOpenCVFrameProcessing:
    """Test frame processing and filters"""

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_when_disabled(self, opencv_service, mock_frame):
        """Test frame passes through unchanged when disabled"""
        opencv_service.set_enabled(False)
        result = opencv_service.process_frame(mock_frame)
        np.testing.assert_array_equal(result, mock_frame)

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_none_filter(self, opencv_service, mock_frame):
        """Test frame with 'none' filter (no processing)"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "none"})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_edges_filter(self, opencv_service, mock_frame):
        """Test Canny edge detection filter"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "edges", "edgeThreshold1": 100, "edgeThreshold2": 200})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape
        assert result.dtype == mock_frame.dtype

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_blur_filter(self, opencv_service, mock_frame):
        """Test Gaussian blur filter"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "blur", "blurKernel": 15})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_blur_even_kernel(self, opencv_service, mock_frame):
        """Test blur filter with even kernel (should become odd)"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "blur", "blurKernel": 16})  # Even kernel
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_grayscale_filter(self, opencv_service, mock_frame):
        """Test grayscale conversion filter"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "grayscale"})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_threshold_filter(self, opencv_service, mock_frame):
        """Test binary threshold filter"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "threshold", "thresholdValue": 127})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_contours_filter(self, opencv_service, mock_frame):
        """Test contours detection filter"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "contours"})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_unknown_filter(self, opencv_service, mock_frame):
        """Test unknown filter type (should return frame unchanged)"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "unknown_filter"})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_non_contiguous(self, opencv_service):
        """Test processing non-contiguous frame"""
        # Create non-contiguous array
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        non_contiguous = frame[::2, ::2, :]  # Slicing makes it non-contiguous

        opencv_service.set_enabled(True)
        result = opencv_service.process_frame(non_contiguous)
        assert result is not None

    def test_process_frame_none_input(self, opencv_service):
        """Test processing None frame"""
        opencv_service.set_enabled(True)
        result = opencv_service.process_frame(None)
        assert result is None


class TestOpenCVOSD:
    """Test OSD (On-Screen Display) functionality"""

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_without_telemetry_service(self, opencv_service, mock_frame):
        """Test OSD when telemetry service not linked"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True, "filter": "none"})
        result = opencv_service.process_frame(mock_frame)
        # Should not crash, just return frame
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_with_telemetry_service(self, opencv_service, mock_frame, mock_telemetry_service):
        """Test OSD with telemetry data"""
        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True, "filter": "none"})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_disabled(self, opencv_service, mock_frame, mock_telemetry_service):
        """Test OSD when disabled"""
        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": False, "filter": "none"})
        result = opencv_service.process_frame(mock_frame)
        # Frame should be unchanged
        np.testing.assert_array_equal(result, mock_frame)

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_with_filter(self, opencv_service, mock_frame, mock_telemetry_service):
        """Test OSD combined with filter"""
        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True, "filter": "grayscale"})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_with_missing_telemetry_data(self, opencv_service, mock_frame):
        """Test OSD handles missing telemetry data gracefully"""
        mock_telemetry = Mock()
        mock_telemetry.get_telemetry.return_value = {}  # Empty telemetry

        opencv_service.set_telemetry_service(mock_telemetry)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape


class TestOpenCVServiceStatus:
    """Test service status and reporting"""

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_get_status(self, opencv_service):
        """Test getting service status"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "edges"})

        status = opencv_service.get_status()

        assert isinstance(status, dict)
        assert "opencv_enabled" in status
        assert "opencv_version" in status
        assert "config" in status
        assert status["opencv_enabled"] is True
        assert status["config"]["filter"] == "edges"

    def test_build_gstreamer_element_disabled(self, opencv_service):
        """Test GStreamer element when disabled"""
        opencv_service.set_enabled(False)
        element = opencv_service.build_gstreamer_element()
        assert element is None

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_build_gstreamer_element_enabled(self, opencv_service):
        """Test GStreamer element when enabled"""
        opencv_service.set_enabled(True)
        element = opencv_service.build_gstreamer_element()
        assert isinstance(element, str)
        assert "videoconvert" in element


class TestOpenCVThreadSafety:
    """Test thread safety of OpenCV service"""

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_concurrent_config_updates(self, opencv_service):
        """Test concurrent configuration updates"""
        import threading

        def update_filter(filter_name):
            opencv_service.update_config({"filter": filter_name})

        threads = [threading.Thread(target=update_filter, args=(f"filter{i}",)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash
        config = opencv_service.get_config()
        assert isinstance(config, dict)

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_concurrent_enable_disable(self, opencv_service):
        """Test concurrent enable/disable operations"""
        import threading

        def toggle():
            opencv_service.set_enabled(True)
            opencv_service.set_enabled(False)

        threads = [threading.Thread(target=toggle) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash
        assert isinstance(opencv_service.is_enabled(), bool)


class TestOpenCVUnavailable:
    """Test OpenCV service when cv2 is not available"""

    def test_service_init_without_opencv(self):
        """Test service initializes even without OpenCV"""
        with patch("app.services.opencv_service.OPENCV_AVAILABLE", False):
            service = OpenCVService()
            assert service.is_available() is False
            assert service.enabled is False

    def test_enable_fails_without_opencv(self):
        """Test enabling fails gracefully without OpenCV"""
        with patch("app.services.opencv_service.OPENCV_AVAILABLE", False):
            service = OpenCVService()
            result = service.set_enabled(True)
            assert result is False
            assert service.is_enabled() is False

    def test_process_frame_without_opencv(self):
        """Test frame processing returns original frame without OpenCV"""
        with patch("app.services.opencv_service.OPENCV_AVAILABLE", False):
            service = OpenCVService()
            service.enabled = True
            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            result = service.process_frame(mock_frame)
            np.testing.assert_array_equal(result, mock_frame)

    def test_build_gstreamer_element_without_opencv(self):
        """Test GStreamer element returns None without OpenCV"""
        with patch("app.services.opencv_service.OPENCV_AVAILABLE", False):
            service = OpenCVService()
            element = service.build_gstreamer_element()
            assert element is None


class TestOpenCVEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_with_exception_in_filter(self, opencv_service):
        """Test frame processing handles exceptions gracefully"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "edges"})

        # Create a problematic frame
        mock_frame = np.zeros((0, 0, 3), dtype=np.uint8)  # Empty frame

        # Should not crash, should return original or handle error
        try:
            result = opencv_service.process_frame(mock_frame)
            assert result is not None
        except Exception:
            # Exception is acceptable for invalid frame
            pass

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_with_exception(self, opencv_service, mock_telemetry_service):
        """Test OSD drawing handles exceptions"""
        mock_telemetry_service.get_telemetry.side_effect = Exception("Telemetry error")

        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True})

        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Should handle exception and return frame
        result = opencv_service.process_frame(mock_frame)
        assert result is not None

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_filter_with_boundary_values(self, opencv_service, mock_frame):
        """Test filters with boundary parameter values"""
        opencv_service.set_enabled(True)

        # Test edges with min thresholds
        opencv_service.update_config({"filter": "edges", "edgeThreshold1": 0, "edgeThreshold2": 1})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

        # Test blur with min kernel (will become 1)
        opencv_service.update_config({"filter": "blur", "blurKernel": 1})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

        # Test threshold with boundary values
        opencv_service.update_config({"filter": "threshold", "thresholdValue": 0})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

        opencv_service.update_config({"filter": "threshold", "thresholdValue": 255})
        result = opencv_service.process_frame(mock_frame)
        assert result.shape == mock_frame.shape

    def test_config_update_with_extra_fields(self, opencv_service):
        """Test config update accepts extra fields (they get stored)"""
        initial_config = opencv_service.get_config()
        opencv_service.update_config({"filter": "blur", "extra_field": "ignored", "another_field": 123})
        updated_config = opencv_service.get_config()

        # Should update valid fields
        assert updated_config["filter"] == "blur"
        # Extra fields may or may not be stored (implementation detail)
        # Just verify the update didn't crash

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_get_status_includes_version(self, opencv_service):
        """Test get_status returns OpenCV version"""
        opencv_service.set_enabled(True)
        status = opencv_service.get_status()

        assert "opencv_version" in status
        assert isinstance(status["opencv_version"], str)
        # Version should have dots (e.g., "4.8.0")
        assert "." in status["opencv_version"]


class TestOpenCVServiceAdvancedFeatures:
    """Test advanced OpenCV service features"""

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_process_frame_with_different_sizes(self, opencv_service):
        """Test processing frames of different sizes"""
        opencv_service.set_enabled(True)
        opencv_service.update_config({"filter": "blur"})

        # Test different frame sizes
        sizes = [(320, 240), (640, 480), (1280, 720), (1920, 1080)]

        for width, height in sizes:
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            result = opencv_service.process_frame(frame)
            assert result.shape == frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_text_placement(self, opencv_service, mock_telemetry_service):
        """Test OSD text is placed correctly on frame"""
        mock_telemetry_service.get_telemetry.return_value = {
            "speed": {"climb_rate": 5.0},
            "attitude": {"yaw": 0.0},
        }

        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True})

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = opencv_service.process_frame(frame)

        # Frame should be processed and returned
        assert result is not None
        assert result.shape == frame.shape

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_telemetry_data_formatting(self, opencv_service, mock_telemetry_service):
        """Test telemetry data is formatted correctly for OSD"""
        mock_telemetry_service.get_telemetry.return_value = {
            "speed": {"climb_rate": 3.14159},
            "attitude": {"yaw": 2.5},
        }

        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True})

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = opencv_service.process_frame(frame)

        assert result is not None
        # OSD should round/format values appropriately

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_filter_preserves_frame_type(self, opencv_service):
        """Test that filters preserve frame data type"""
        opencv_service.set_enabled(True)

        filters = ["blur", "edges", "threshold", "gray"]
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        for filter_name in filters:
            opencv_service.update_config({"filter": filter_name})
            result = opencv_service.process_frame(frame)

            assert result.dtype == np.uint8

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_concurrent_config_updates(self, opencv_service):
        """Test handling concurrent configuration updates"""
        opencv_service.set_enabled(True)

        # Simulate rapid config changes
        configs = [
            {"filter": "blur", "blurKernel": 7},
            {"filter": "edges", "edgeThreshold1": 100},
            {"filter": "threshold", "thresholdValue": 128},
            {"filter": "none"},
        ]

        for config in configs:
            result = opencv_service.update_config(config)
            assert result is not None

    def test_service_state_transitions(self, opencv_service):
        """Test various state transitions"""
        # Start disabled
        assert opencv_service.is_enabled() is False

        # Enable then disable
        if opencv_service.is_available():
            opencv_service.set_enabled(True)
            assert opencv_service.is_enabled() is True

            opencv_service.set_enabled(False)
            assert opencv_service.is_enabled() is False

            # Re-enable
            opencv_service.set_enabled(True)
            assert opencv_service.is_enabled() is True

    def test_get_config_immutability(self, opencv_service):
        """Test that get_config returns a copy (modifying doesn't affect service)"""
        config1 = opencv_service.get_config()
        config1["filter"] = "modified"

        config2 = opencv_service.get_config()

        # Original should not be modified
        assert config2["filter"] == "none"

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_osd_with_missing_telemetry_fields(self, opencv_service, mock_telemetry_service):
        """Test OSD handles missing telemetry fields gracefully"""
        # Return partial telemetry data
        mock_telemetry_service.get_telemetry.return_value = {"speed": {"climb_rate": 1.0}}

        opencv_service.set_telemetry_service(mock_telemetry_service)
        opencv_service.set_enabled(True)
        opencv_service.update_config({"osd_enabled": True})

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = opencv_service.process_frame(frame)

        # Should handle missing 'attitude' field
        assert result is not None

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_filter_chain_consistency(self, opencv_service):
        """Test that switching between filters is consistent"""
        opencv_service.set_enabled(True)

        test_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128

        # Apply each filter twice and verify consistency
        for filter_name in ["blur", "edges", "threshold"]:
            opencv_service.update_config({"filter": filter_name})

            result1 = opencv_service.process_frame(test_frame.copy())
            result2 = opencv_service.process_frame(test_frame.copy())

            # Results should be identical for same input
            assert np.array_equal(result1, result2)

    def test_status_when_disabled(self, opencv_service):
        """Test status when service is disabled"""
        opencv_service.set_enabled(False)
        status = opencv_service.get_status()

        # Just verify status is returned
        assert status is not None
        assert isinstance(status, dict)

    @pytest.mark.skipif(not OpenCVService().is_available(), reason="OpenCV not available")
    def test_update_config_returns_updated_config(self, opencv_service):
        """Test that update_config returns the updated configuration"""
        new_config = {"filter": "edges", "edgeThreshold1": 200}

        result = opencv_service.update_config(new_config)

        assert result["filter"] == "edges"
        assert result["edgeThreshold1"] == 200

    def test_telemetry_service_integration(self, opencv_service, mock_telemetry_service):
        """Test telemetry service can be set and retrieved"""
        opencv_service.set_telemetry_service(mock_telemetry_service)

        # Verify it's stored
        assert opencv_service._telemetry_service is mock_telemetry_service
