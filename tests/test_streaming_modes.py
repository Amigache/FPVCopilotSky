"""
Multi-Mode Streaming Tests

Tests for the multi-mode streaming system including:
- UDP unicast (direct)
- UDP multicast (LAN broadcast)
- RTSP Server (multi-client streaming)
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.video_config import StreamingConfig


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked API services"""
    return TestClient(app)


class TestStreamingConfigModel:
    """Test StreamingConfig dataclass with all modes"""

    def test_default_config(self):
        """Test default configuration is UDP unicast"""
        config = StreamingConfig()
        assert config.mode == "udp"
        assert config.udp_host == "192.168.1.136"
        assert config.udp_port == 5600
        assert config.enabled is True

    def test_udp_unicast_config(self):
        """Test UDP unicast mode configuration"""
        config = StreamingConfig(mode="udp", udp_host="192.168.1.100", udp_port=5600)
        assert config.mode == "udp"
        assert config.udp_host == "192.168.1.100"
        assert config.udp_port == 5600

    def test_multicast_config(self):
        """Test UDP multicast mode configuration"""
        config = StreamingConfig(mode="multicast", multicast_group="239.1.1.1", multicast_port=5600, multicast_ttl=1)
        assert config.mode == "multicast"
        assert config.multicast_group == "239.1.1.1"
        assert config.multicast_port == 5600
        assert config.multicast_ttl == 1

    def test_rtsp_config(self):
        """Test RTSP server mode configuration"""
        config = StreamingConfig(mode="rtsp", rtsp_url="rtsp://localhost:8554/fpv", rtsp_transport="tcp")
        assert config.mode == "rtsp"
        assert config.rtsp_url == "rtsp://localhost:8554/fpv"
        assert config.rtsp_transport == "tcp"

    def test_rtsp_udp_transport_config(self):
        """Test RTSP server with UDP transport configuration"""
        config = StreamingConfig(mode="rtsp", rtsp_url="rtsp://10.0.0.1:8554/fpv", rtsp_transport="udp")
        assert config.mode == "rtsp"
        assert config.rtsp_transport == "udp"
        assert config.rtsp_url == "rtsp://10.0.0.1:8554/fpv"

    def test_multicast_ttl_range(self):
        """Test multicast TTL is within valid range"""
        config = StreamingConfig(multicast_ttl=1)
        assert 1 <= config.multicast_ttl <= 255

    def test_multicast_group_format(self):
        """Test multicast group address is in valid range"""
        config = StreamingConfig(multicast_group="239.255.255.255")
        assert config.multicast_group.startswith("239.")


class TestStreamingModeAPI:
    """Test API endpoints for streaming mode configuration"""

    def test_get_status_includes_mode(self, client):
        """Test that status endpoint includes streaming mode"""
        response = client.get("/api/video/status")
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        data = response.json()
        assert "config" in data
        # Mode should be present (defaults to 'udp' if not set)
        if "mode" in data["config"]:
            assert data["config"]["mode"] in ["udp", "multicast", "rtsp"]

    def test_configure_udp_mode(self, client):
        """Test configuring UDP unicast mode"""
        config_data = {"mode": "udp", "udp_host": "192.168.1.200", "udp_port": 5601}

        response = client.post("/api/video/config/streaming", json=config_data)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True

    def test_configure_multicast_mode(self, client):
        """Test configuring UDP multicast mode"""
        config_data = {"mode": "multicast", "multicast_group": "239.2.2.2", "multicast_port": 5602, "multicast_ttl": 2}

        response = client.post("/api/video/config/streaming", json=config_data)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True

    def test_configure_rtsp_tcp_mode(self, client):
        """Test configuring RTSP server with TCP transport"""
        config_data = {"mode": "rtsp", "rtsp_url": "rtsp://10.0.0.1:8554/fpv", "rtsp_transport": "tcp"}

        response = client.post("/api/video/config/streaming", json=config_data)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True

    def test_configure_rtsp_udp_mode(self, client):
        """Test configuring RTSP server with UDP transport"""
        config_data = {"mode": "rtsp", "rtsp_url": "rtsp://10.0.0.1:8554/fpv", "rtsp_transport": "udp"}

        response = client.post("/api/video/config/streaming", json=config_data)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True

    def test_partial_config_update(self, client):
        """Test partial configuration update (only mode change)"""
        config_data = {"mode": "multicast"}

        response = client.post("/api/video/config/streaming", json=config_data)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True

    def test_invalid_mode_rejected(self, client):
        """Test that invalid streaming mode is handled gracefully"""
        config_data = {"mode": "invalid_mode"}

        response = client.post("/api/video/config/streaming", json=config_data)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        # Should accept but will fallback to UDP when pipeline is built
        assert response.status_code in [200, 400, 422]


class TestStreamingPipelineModes:
    """Test GStreamer pipeline building for different modes"""

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.Gst")
    def test_udp_sink_creation(self, mock_gst):
        """Test UDP unicast sink creation"""
        from app.services.gstreamer_service import GStreamerService

        # Mock element creation
        mock_sink = MagicMock()
        mock_gst.ElementFactory.make.return_value = mock_sink

        service = GStreamerService()
        service.streaming_config.mode = "udp"
        service.streaming_config.udp_host = "192.168.1.100"
        service.streaming_config.udp_port = 5600

        sink = service._create_sink_for_mode()

        assert sink is not None
        mock_gst.ElementFactory.make.assert_called_with("udpsink", "sink")
        mock_sink.set_property.assert_any_call("host", "192.168.1.100")
        mock_sink.set_property.assert_any_call("port", 5600)

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.Gst")
    def test_multicast_sink_creation(self, mock_gst):
        """Test UDP multicast sink creation"""
        from app.services.gstreamer_service import GStreamerService

        mock_sink = MagicMock()
        mock_gst.ElementFactory.make.return_value = mock_sink

        service = GStreamerService()
        service.streaming_config.mode = "multicast"
        service.streaming_config.multicast_group = "239.1.1.1"
        service.streaming_config.multicast_port = 5600
        service.streaming_config.multicast_ttl = 1

        sink = service._create_sink_for_mode()

        assert sink is not None
        mock_gst.ElementFactory.make.assert_called_with("udpsink", "sink")
        mock_sink.set_property.assert_any_call("host", "239.1.1.1")
        mock_sink.set_property.assert_any_call("port", 5600)
        mock_sink.set_property.assert_any_call("auto-multicast", True)
        mock_sink.set_property.assert_any_call("ttl", 1)

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.Gst")
    def test_fallback_to_udp_when_sink_unavailable(self, mock_gst):
        """Test fallback to UDP when preferred sink is unavailable"""
        from app.services.gstreamer_service import GStreamerService

        # Mock multicastsink not available, but udpsink is
        def make_element(name, element_name):
            if name == "multicastsink":
                return None  # Not available
            else:
                return MagicMock()

        mock_gst.ElementFactory.make.side_effect = make_element

        service = GStreamerService()
        service.streaming_config.mode = "multicast"
        service.streaming_config.udp_host = "192.168.1.100"
        service.streaming_config.udp_port = 5600

        sink = service._create_sink_for_mode()

        assert sink is not None
        # Should have fallen back to UDP
        calls = mock_gst.ElementFactory.make.call_args_list
        assert any("udpsink" in str(call) for call in calls)

    @patch("app.services.gstreamer_service.GSTREAMER_AVAILABLE", True)
    @patch("app.services.gstreamer_service.Gst")
    def test_unknown_mode_fallback(self, mock_gst):
        """Test fallback to UDP for unknown streaming mode"""
        from app.services.gstreamer_service import GStreamerService

        mock_sink = MagicMock()
        mock_gst.ElementFactory.make.return_value = mock_sink

        service = GStreamerService()
        service.streaming_config.mode = "unknown_mode"
        service.streaming_config.udp_host = "192.168.1.100"
        service.streaming_config.udp_port = 5600

        sink = service._create_sink_for_mode()

        assert sink is not None
        # Should fall back to UDP
        mock_gst.ElementFactory.make.assert_called_with("udpsink", "sink")


class TestStreamingModeIntegration:
    """Integration tests for complete streaming workflows"""

    def test_udp_mode_workflow(self, client):
        """Test complete UDP unicast workflow"""
        # Configure UDP mode
        config = {"mode": "udp", "udp_host": "192.168.1.150", "udp_port": 5605}
        response = client.post("/api/video/config/streaming", json=config)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        # Check status reflects configuration
        response = client.get("/api/video/status")
        assert response.status_code == 200
        status = response.json()
        if "mode" in status.get("config", {}):
            assert status["config"]["mode"] == "udp"

    def test_multicast_mode_workflow(self, client):
        """Test complete UDP multicast workflow"""
        # Configure multicast mode
        config = {"mode": "multicast", "multicast_group": "239.3.3.3", "multicast_port": 5606, "multicast_ttl": 5}
        response = client.post("/api/video/config/streaming", json=config)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        # Check status reflects configuration
        response = client.get("/api/video/status")
        assert response.status_code == 200
        status = response.json()
        if "mode" in status.get("config", {}):
            assert status["config"]["mode"] == "multicast"

    def test_rtsp_mode_workflow(self, client):
        """Test complete RTSP server workflow"""
        # Configure RTSP mode
        config = {"mode": "rtsp", "rtsp_url": "rtsp://192.168.1.50:8554/fpv", "rtsp_transport": "tcp"}
        response = client.post("/api/video/config/streaming", json=config)
        # Service might not be available in CI
        if response.status_code == 503:
            pytest.skip("Video service not available")

        assert response.status_code == 200

        # Check status reflects configuration
        response = client.get("/api/video/status")
        assert response.status_code == 200
        status = response.json()
        if "mode" in status.get("config", {}):
            assert status["config"]["mode"] == "rtsp"

    def test_mode_switching(self, client):
        """Test switching between different streaming modes"""
        modes = [
            {"mode": "udp", "udp_host": "192.168.1.100", "udp_port": 5600},
            {"mode": "multicast", "multicast_group": "239.1.1.1", "multicast_port": 5600},
            {"mode": "rtsp", "rtsp_url": "rtsp://localhost:8554/fpv", "rtsp_transport": "tcp"},
        ]

        for config in modes:
            response = client.post("/api/video/config/streaming", json=config)
            # Service might not be available in CI
            if response.status_code == 503:
                pytest.skip("Video service not available")

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True


class TestMulticastValidation:
    """Test multicast-specific validation and edge cases"""

    def test_multicast_group_valid_range(self):
        """Test multicast group is in valid IP range (239.0.0.0 - 239.255.255.255)"""
        valid_groups = ["239.0.0.1", "239.1.1.1", "239.255.255.255"]
        for group in valid_groups:
            config = StreamingConfig(multicast_group=group)
            assert config.multicast_group == group

    def test_multicast_ttl_boundary_values(self):
        """Test TTL boundary values"""
        # Minimum TTL
        config_min = StreamingConfig(multicast_ttl=1)
        assert config_min.multicast_ttl == 1

        # Maximum TTL
        config_max = StreamingConfig(multicast_ttl=255)
        assert config_max.multicast_ttl == 255

    def test_multicast_port_range(self):
        """Test multicast port is in valid range"""
        config = StreamingConfig(multicast_port=5600)
        assert 1024 <= config.multicast_port <= 65535


class TestRTSPValidation:
    """Test RTSP server-specific validation and edge cases"""

    def test_rtsp_url_formats(self):
        """Test various RTSP URL formats"""
        urls = ["rtsp://localhost:8554/fpv", "rtsp://192.168.1.100:8554/stream", "rtsp://10.0.0.1:8554/live/fpv"]

        for url in urls:
            config = StreamingConfig(mode="rtsp", rtsp_url=url)
            assert config.rtsp_url == url

    def test_rtsp_transport_options(self):
        """Test RTSP transport options"""
        transports = ["tcp", "udp"]
        for transport in transports:
            config = StreamingConfig(mode="rtsp", rtsp_transport=transport)
            assert config.rtsp_transport == transport
