"""
WebRTC API Route Tests

Tests for WebRTC signaling API endpoints including:
- Session creation
- SDP offer/answer exchange
- ICE candidate management
- Connection lifecycle
- Stats update
- Adaptive config
- 4G config
- Log retrieval
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

# Import the same module object that main.py uses (via sys.path manipulation)
# main.py does: from api.routes import webrtc as webrtc_routes
# which registers as 'api.routes.webrtc' in sys.modules
import api.routes.webrtc as webrtc_routes


@pytest.fixture
def mock_webrtc_service():
    """Provide a mock WebRTC service for route testing"""
    mock = Mock()

    # Status (sync)
    mock.get_status.return_value = {
        "active": True,
        "peers": [],
        "global_stats": {
            "total_peers": 0,
            "active_peers": 0,
            "avg_rtt_ms": 0,
            "avg_bitrate_kbps": 0,
        },
        "adaptive_config": {
            "max_bitrate": 2500,
            "min_bitrate": 300,
            "target_bitrate": 1500,
        },
        "log": [],
    }

    # Session creation (async)
    mock.create_peer_connection = AsyncMock(
        return_value={
            "success": True,
            "peer_id": "abc123",
            "config": {
                "iceServers": [{"urls": "stun:stun.l.google.com:19302"}],
                "sdpSemantics": "unified-plan",
            },
            "adaptive_config": {"target_bitrate": 1500},
        }
    )

    # Offer/answer (handle_offer is async, handle_answer is sync)
    mock.handle_offer = AsyncMock(
        return_value={
            "success": True,
            "peer_id": "abc123",
            "sdp": "answer-sdp",
            "type": "answer",
        }
    )
    mock.handle_answer.return_value = {"success": True, "peer_id": "abc123"}

    # ICE (add_ice_candidate is async, get_ice_candidates is sync)
    mock.add_ice_candidate = AsyncMock(return_value={"success": True})
    mock.get_ice_candidates.return_value = {"success": True, "candidates": []}

    # Connection (sync)
    mock.set_peer_connected.return_value = {"success": True}
    mock.disconnect_peer.return_value = {"success": True}

    # Stats (sync)
    mock.update_peer_stats.return_value = {"success": True}

    # Logs (sync)
    mock.get_logs.return_value = [{"timestamp": 1700000000.0, "level": "info", "message": "Service started"}]

    # 4G config (sync)
    mock.get_4g_optimized_config.return_value = {
        "video": {"maxBitrate": 1500000},
        "ice": {"bundlePolicy": "max-bundle"},
    }

    # Adaptive config (sync)
    mock.update_adaptive_config.return_value = {
        "success": True,
        "config": {"target_bitrate": 2000},
    }

    return mock


@pytest.fixture
def client(mock_api_services, mock_webrtc_service):
    """Create TestClient with WebRTC service injected"""
    # Override the conftest default mock with our detailed mock
    webrtc_routes._webrtc_service = mock_webrtc_service
    yield TestClient(app)


class TestWebRTCStatusEndpoint:
    """Test GET /api/webrtc/status"""

    def test_get_status_success(self, client, mock_webrtc_service):
        response = client.get("/api/webrtc/status")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "peers" in data
        assert "global_stats" in data
        mock_webrtc_service.get_status.assert_called_once()

    def test_get_status_no_service(self, mock_api_services):
        """Test 503 when service not initialized"""
        webrtc_routes.set_webrtc_service(None)
        c = TestClient(app)
        response = c.get("/api/webrtc/status")
        assert response.status_code == 503


class TestWebRTCSessionEndpoint:
    """Test POST /api/webrtc/session"""

    def test_create_session(self, client, mock_webrtc_service):
        response = client.post("/api/webrtc/session", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "peer_id" in data
        assert "config" in data

    def test_create_session_with_peer_id(self, client, mock_webrtc_service):
        response = client.post("/api/webrtc/session", json={"peer_id": "custom-id"})
        assert response.status_code == 200
        mock_webrtc_service.create_peer_connection.assert_called_with("custom-id")

    def test_create_session_failure(self, client, mock_webrtc_service):
        mock_webrtc_service.create_peer_connection = AsyncMock(
            return_value={
                "success": False,
                "error": "Max peers reached",
            }
        )
        response = client.post("/api/webrtc/session", json={})
        assert response.status_code == 400


class TestWebRTCSDPEndpoints:
    """Test SDP offer/answer endpoints"""

    def test_handle_offer(self, client, mock_webrtc_service):
        response = client.post(
            "/api/webrtc/offer",
            json={"peer_id": "abc", "sdp": "v=0\r\n...", "type": "offer"},
        )
        assert response.status_code == 200
        mock_webrtc_service.handle_offer.assert_called_with("abc", "v=0\r\n...")

    def test_handle_offer_unknown_peer(self, client, mock_webrtc_service):
        mock_webrtc_service.handle_offer.return_value = {
            "success": False,
            "error": "Peer not found",
        }
        response = client.post(
            "/api/webrtc/offer",
            json={"peer_id": "unknown", "sdp": "v=0\r\n...", "type": "offer"},
        )
        assert response.status_code == 400

    def test_handle_answer(self, client, mock_webrtc_service):
        response = client.post(
            "/api/webrtc/answer",
            json={"peer_id": "abc", "sdp": "v=0\r\n...", "type": "answer"},
        )
        assert response.status_code == 200
        mock_webrtc_service.handle_answer.assert_called_with("abc", "v=0\r\n...")

    def test_invalid_sdp_type(self, client):
        """Type field must be 'offer' or 'answer'"""
        response = client.post(
            "/api/webrtc/offer",
            json={"peer_id": "abc", "sdp": "...", "type": "invalid"},
        )
        assert response.status_code == 422  # Pydantic validation


class TestWebRTCICEEndpoints:
    """Test ICE candidate endpoints"""

    def test_add_ice_candidate(self, client, mock_webrtc_service):
        response = client.post(
            "/api/webrtc/ice-candidate",
            json={
                "peer_id": "abc",
                "candidate": {"candidate": "candidate:1...", "sdpMid": "0"},
            },
        )
        assert response.status_code == 200
        mock_webrtc_service.add_ice_candidate.assert_called_once()

    def test_get_ice_candidates(self, client, mock_webrtc_service):
        response = client.get("/api/webrtc/ice-candidates/abc123")
        assert response.status_code == 200
        data = response.json()
        assert "candidates" in data


class TestWebRTCConnectionEndpoints:
    """Test connect/disconnect endpoints"""

    def test_set_connected(self, client, mock_webrtc_service):
        response = client.post("/api/webrtc/connected", json={"peer_id": "abc123"})
        assert response.status_code == 200
        mock_webrtc_service.set_peer_connected.assert_called_with("abc123")

    def test_set_connected_no_peer_id(self, client):
        response = client.post("/api/webrtc/connected", json={})
        assert response.status_code == 400

    def test_disconnect_peer(self, client, mock_webrtc_service):
        response = client.post("/api/webrtc/disconnect", json={"peer_id": "abc123"})
        assert response.status_code == 200
        mock_webrtc_service.disconnect_peer.assert_called_with("abc123")

    def test_disconnect_no_peer_id(self, client):
        response = client.post("/api/webrtc/disconnect", json={})
        assert response.status_code == 400

    def test_disconnect_failure(self, client, mock_webrtc_service):
        mock_webrtc_service.disconnect_peer.return_value = {
            "success": False,
            "error": "Peer not found",
        }
        response = client.post("/api/webrtc/disconnect", json={"peer_id": "ghost"})
        assert response.status_code == 400


class TestWebRTCStatsEndpoint:
    """Test stats update endpoint"""

    def test_update_stats(self, client, mock_webrtc_service):
        response = client.post(
            "/api/webrtc/stats",
            json={"peer_id": "abc", "stats": {"rtt_ms": 45, "bitrate_kbps": 1500}},
        )
        assert response.status_code == 200
        mock_webrtc_service.update_peer_stats.assert_called_with("abc", {"rtt_ms": 45, "bitrate_kbps": 1500})


class TestWebRTCLogsEndpoint:
    """Test log retrieval endpoint"""

    def test_get_logs(self, client, mock_webrtc_service):
        response = client.get("/api/webrtc/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert len(data["logs"]) == 1
        mock_webrtc_service.get_logs.assert_called_with(100)

    def test_get_logs_with_limit(self, client, mock_webrtc_service):
        response = client.get("/api/webrtc/logs?limit=10")
        assert response.status_code == 200
        mock_webrtc_service.get_logs.assert_called_with(10)


class TestWebRTC4GConfigEndpoint:
    """Test 4G optimization config endpoints"""

    def test_get_4g_config(self, client, mock_webrtc_service):
        response = client.get("/api/webrtc/4g-config")
        assert response.status_code == 200
        data = response.json()
        assert "video" in data
        assert "ice" in data

    def test_update_adaptive_config(self, client, mock_webrtc_service):
        response = client.post(
            "/api/webrtc/adaptive-config",
            json={"target_bitrate": 2000, "max_framerate": 24},
        )
        assert response.status_code == 200
        mock_webrtc_service.update_adaptive_config.assert_called_once()

    def test_update_adaptive_config_validation(self, client):
        """Bitrate must be within valid range"""
        response = client.post(
            "/api/webrtc/adaptive-config",
            json={"max_bitrate": 50},  # Below minimum (100)
        )
        assert response.status_code == 422

    def test_update_adaptive_config_empty(self, client):
        """Empty config should be rejected"""
        response = client.post("/api/webrtc/adaptive-config", json={})
        assert response.status_code == 400
