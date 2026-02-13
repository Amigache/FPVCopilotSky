"""
WebRTC Service Tests

Tests for the WebRTC signaling service including:
- Session creation and management
- SDP offer/answer exchange
- ICE candidate handling
- Peer lifecycle (connect/disconnect)
- Stats tracking
- 4G optimization config
- Log management
- Stale peer cleanup
"""

import pytest
import time
from unittest.mock import MagicMock, patch, AsyncMock

# ── Global fixture to mock aiortc for testing ──────────────────────────────


@pytest.fixture(autouse=True)
def mock_aiortc():
    """
    Mock aiortc availability and classes for all tests.
    This allows tests to run without requiring aiortc to be installed.
    """
    with patch("app.services.webrtc_service.AIORTC_AVAILABLE", True):
        # Create a mock RTCPeerConnection class
        mock_pc_class = MagicMock()

        # Create instance-level mock
        mock_pc_instance = MagicMock()
        mock_pc_class.return_value = mock_pc_instance

        # Mock RTCPeerConnection methods
        mock_pc_instance.connectionState = "new"
        mock_pc_instance.addTrack = MagicMock()
        mock_pc_instance.addTransceiver = MagicMock()
        mock_pc_instance.getSenders = MagicMock(return_value=[])
        mock_pc_instance.setRemoteDescription = AsyncMock(return_value=None)
        mock_pc_instance.createAnswer = AsyncMock(return_value=MagicMock(sdp="answer-sdp"))
        mock_pc_instance.setLocalDescription = AsyncMock(return_value=None)
        mock_pc_instance.addIceCandidate = AsyncMock(return_value=None)
        mock_pc_instance.close = AsyncMock(return_value=None)
        mock_pc_instance.on = MagicMock()

        # Mock localDescription property
        local_desc = MagicMock()
        local_desc.sdp = "local-answer-sdp"
        mock_pc_instance.localDescription = local_desc

        with patch("app.services.webrtc_service.RTCPeerConnection", mock_pc_class):
            # Mock RTCSessionDescription
            mock_rts = MagicMock()
            mock_rts.side_effect = lambda sdp, type: MagicMock(sdp=sdp, type=type)

            with patch("app.services.webrtc_service.RTCSessionDescription", mock_rts):
                # Mock MediaStreamTrack
                with patch("app.services.webrtc_service.MediaStreamTrack", MagicMock()):
                    # Mock av (PyAV) - use create=True since these may not be imported
                    with patch(
                        "app.services.webrtc_service.VideoFrame",
                        MagicMock(),
                        create=True,
                    ):
                        with patch("app.services.webrtc_service.np", MagicMock(), create=True):
                            yield


class TestWebRTCServiceInit:
    """Test WebRTC service initialization"""

    def test_service_creation(self):
        """Test basic service creation"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        assert service.is_active is False
        assert len(service.peers) == 0
        assert service.global_stats["total_peers"] == 0
        assert service.global_stats["active_peers"] == 0

    def test_service_with_websocket_manager(self):
        """Test service creation with websocket manager"""
        from app.services.webrtc_service import WebRTCService

        ws = MagicMock()
        loop = MagicMock()
        service = WebRTCService(websocket_manager=ws, event_loop=loop)
        assert service.websocket_manager is ws
        assert service.event_loop is loop

    def test_activate_and_deactivate(self):
        """Test activating and deactivating service"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.activate()
        assert service.is_active is True

        service.deactivate()
        assert service.is_active is False


class TestWebRTCPeerManagement:
    """Test peer session management"""

    def test_create_session(self):
        """Test creating a new peer session"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        result = service.create_offer()

        assert result["success"] is True
        assert "peer_id" in result
        assert "config" in result
        assert "iceServers" in result["config"]
        assert "adaptive_config" in result
        assert service.global_stats["total_peers"] == 1

    def test_create_session_with_custom_id(self):
        """Test creating a session with a custom peer ID"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        result = service.create_offer(peer_id="test-peer-1")

        assert result["success"] is True
        assert result["peer_id"] == "test-peer-1"
        assert "test-peer-1" in service.peers

    @pytest.mark.asyncio
    async def test_handle_offer(self):
        """Test handling SDP offer from client"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")

        result = await service.handle_offer("p1", "v=0\r\nm=video...")
        assert result["success"] is True
        assert service.peers["p1"].remote_sdp == "v=0\r\nm=video..."
        assert service.peers["p1"].state == "connecting"

    @pytest.mark.asyncio
    async def test_handle_offer_unknown_peer(self):
        """Test handling offer for non-existent peer"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        result = await service.handle_offer("unknown", "sdp")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_answer(self):
        """Test handling SDP answer from client"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")
        await service.handle_offer("p1", "offer-sdp")

        # Note: handle_answer is a stub in server-creates-answer flow
        result = service.handle_answer("p1", "answer-sdp")
        assert result["success"] is True
        assert result["peer_id"] == "p1"

    @pytest.mark.asyncio
    async def test_add_ice_candidate(self):
        """Test adding ICE candidate"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")

        candidate = {"candidate": "candidate:1 1 udp ...", "sdpMid": "0"}
        result = await service.add_ice_candidate("p1", candidate)
        assert result["success"] is True
        assert len(service.peers["p1"].ice_candidates_remote) == 1

    def test_get_ice_candidates(self):
        """Test getting pending ICE candidates"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")

        # Initially empty
        result = service.get_ice_candidates("p1")
        assert result["success"] is True
        assert len(result["candidates"]) == 0

    def test_set_peer_connected(self):
        """Test marking peer as connected"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")

        result = service.set_peer_connected("p1")
        assert result["success"] is True
        assert service.peers["p1"].state == "connected"
        assert service.global_stats["active_peers"] == 1

    def test_disconnect_peer(self):
        """Test disconnecting a peer"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")
        service.set_peer_connected("p1")

        result = service.disconnect_peer("p1")
        assert result["success"] is True
        assert "p1" not in service.peers
        assert service.global_stats["active_peers"] == 0

    def test_disconnect_unknown_peer(self):
        """Test disconnecting non-existent peer"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        result = service.disconnect_peer("unknown")
        assert result["success"] is False

    def test_multiple_peers(self):
        """Test managing multiple peers"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")
        service.create_offer(peer_id="p2")
        service.create_offer(peer_id="p3")

        assert service.global_stats["total_peers"] == 3
        assert len(service.peers) == 3

        service.set_peer_connected("p1")
        service.set_peer_connected("p2")
        assert service.global_stats["active_peers"] == 2

        service.disconnect_peer("p1")
        assert service.global_stats["active_peers"] == 1


class TestWebRTCStats:
    """Test stats tracking and reporting"""

    def test_update_peer_stats(self):
        """Test updating peer statistics"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")
        service.set_peer_connected("p1")

        stats = {"rtt_ms": 45, "bitrate_kbps": 1500, "fps": 28}
        result = service.update_peer_stats("p1", stats)
        assert result["success"] is True
        assert service.peers["p1"].stats == stats

    def test_global_stats_calculation(self):
        """Test global stats are recalculated from peers"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")
        service.create_offer(peer_id="p2")
        service.set_peer_connected("p1")
        service.set_peer_connected("p2")

        service.update_peer_stats("p1", {"rtt_ms": 40, "bitrate_kbps": 1400})
        service.update_peer_stats("p2", {"rtt_ms": 60, "bitrate_kbps": 1600})

        assert service.global_stats["avg_rtt_ms"] == 50.0
        assert service.global_stats["avg_bitrate_kbps"] == 1500

    def test_get_status(self):
        """Test comprehensive status report"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")

        status = service.get_status()
        assert "active" in status
        assert "peers" in status
        assert "global_stats" in status
        assert "adaptive_config" in status
        assert "log" in status
        assert len(status["peers"]) == 1
        assert status["peers"][0]["peer_id"] == "p1"


class TestWebRTC4GOptimization:
    """Test 4G optimization configuration"""

    def test_default_adaptive_config(self):
        """Test default adaptive config values"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        config = service.adaptive_config
        assert config["max_bitrate"] == 2500
        assert config["min_bitrate"] == 300
        assert config["target_bitrate"] == 1500
        assert config["adaptation_enabled"] is True
        assert config["congestion_control"] is True

    def test_get_4g_optimized_config(self):
        """Test getting 4G-optimized WebRTC config"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        config = service.get_4g_optimized_config()

        assert "video" in config
        assert "ice" in config
        assert "sdp" in config
        assert "network" in config

        # Check video constraints
        assert config["video"]["maxBitrate"] == 1500 * 1000  # in bps
        assert config["video"]["degradationPreference"] == "maintain-framerate"

        # Check ICE config
        assert config["ice"]["bundlePolicy"] == "max-bundle"
        assert config["ice"]["rtcpMuxPolicy"] == "require"

        # Check network optimizations
        assert config["network"]["nackEnabled"] is True
        assert config["network"]["transportCc"] is True

    def test_update_adaptive_config(self):
        """Test updating adaptive config"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        result = service.update_adaptive_config(
            {
                "target_bitrate": 2000,
                "max_framerate": 24,
            }
        )

        assert result["success"] is True
        assert service.adaptive_config["target_bitrate"] == 2000
        assert service.adaptive_config["max_framerate"] == 24

    def test_update_adaptive_config_ignores_unknown(self):
        """Test that unknown config keys are ignored"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        result = service.update_adaptive_config(
            {
                "unknown_key": 999,
                "target_bitrate": 1800,
            }
        )

        assert result["success"] is True
        assert service.adaptive_config["target_bitrate"] == 1800
        assert "unknown_key" not in service.adaptive_config


class TestWebRTCLog:
    """Test event logging"""

    def test_logs_generated(self):
        """Test that operations generate log entries"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.create_offer(peer_id="p1")
        service.set_peer_connected("p1")
        service.disconnect_peer("p1")

        logs = service.get_logs()
        assert len(logs) >= 3
        assert any("created" in log["message"] for log in logs)
        assert any("connected" in log["message"] for log in logs)
        assert any("disconnected" in log["message"] for log in logs)

    def test_log_ring_buffer(self):
        """Test log buffer doesn't grow unbounded"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service._log_max_size = 10

        for i in range(20):
            service._add_log("info", f"msg {i}")

        logs = service.get_logs()
        assert len(logs) <= 10

    def test_log_entry_format(self):
        """Test log entries have correct format"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service._add_log("warning", "Test warning")

        logs = service.get_logs()
        assert len(logs) == 1
        assert logs[0]["level"] == "warning"
        assert logs[0]["message"] == "Test warning"
        assert "timestamp" in logs[0]

    def test_get_logs_with_limit(self):
        """Test getting limited number of logs"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        for i in range(50):
            service._add_log("info", f"msg {i}")

        logs = service.get_logs(limit=5)
        assert len(logs) == 5


class TestWebRTCGlobalSingleton:
    """Test global singleton pattern"""

    def test_init_and_get(self):
        """Test init and get global service"""
        from app.services.webrtc_service import init_webrtc_service, get_webrtc_service

        service = init_webrtc_service()
        assert service is not None
        assert get_webrtc_service() is service

    def test_shutdown(self):
        """Test service shutdown"""
        from app.services.webrtc_service import WebRTCService

        service = WebRTCService()
        service.activate()
        service.create_offer(peer_id="p1")

        service.shutdown()
        assert service.is_active is False
        assert len(service.peers) == 0


class TestStreamingConfigWebRTC:
    """Test StreamingConfig with WebRTC mode"""

    def test_webrtc_mode_valid(self):
        """Test that 'webrtc' is a valid streaming mode"""
        from app.services.video_config import StreamingConfig

        config = StreamingConfig(mode="webrtc")
        assert config.mode == "webrtc"

    def test_webrtc_mode_preserves_other_defaults(self):
        """Test that WebRTC mode doesn't affect other defaults"""
        from app.services.video_config import StreamingConfig

        config = StreamingConfig(mode="webrtc")
        assert config.udp_port == 5600  # UDP defaults preserved
        assert config.multicast_group == "239.1.1.1"
        assert config.enabled is True

    def test_invalid_mode_falls_back(self):
        """Test invalid mode still falls back to UDP"""
        from app.services.video_config import StreamingConfig

        config = StreamingConfig(mode="invalid")
        assert config.mode == "udp"
