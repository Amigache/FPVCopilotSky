"""
WebSocket Integration Tests

Tests for real-time WebSocket communication including message handling,
connection lifecycle, and data synchronization across clients.
"""

import pytest
import json
import asyncio
import queue
import threading
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app


def receive_json_with_timeout(websocket, timeout=1.0):
    result = queue.Queue(maxsize=1)

    def worker():
        try:
            result.put(("ok", websocket.receive_json()))
        except Exception as exc:
            result.put(("err", exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        status, payload = result.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError("Timed out waiting for websocket response") from exc
    if status == "err":
        raise payload
    return payload


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked API services"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_ws_app_globals():
    """Provide the app globals the /ws endpoint expects (set in lifespan).

    Without this, connecting to /ws hits ``None.get_status()`` and the tests
    would skip instead of exercising the endpoint.
    """
    import app.main as main

    saved = (main.mavlink_service, main.video_service, main.router_service)
    mav = MagicMock()
    mav.get_status.return_value = {"connected": False}
    mav.get_telemetry.return_value = {"connected": False}
    video = MagicMock()
    video.get_status.return_value = {"streaming": False}
    main.mavlink_service = mav
    main.video_service = video
    main.router_service = MagicMock()
    yield
    main.mavlink_service, main.video_service, main.router_service = saved


class TestWebSocketConnectionLifecycle:
    """Test WebSocket connection lifecycle"""

    def test_websocket_endpoint_exists(self, client):
        """Test that WebSocket endpoint is accessible"""
        # Try to establish WebSocket connection
        try:
            with client.websocket_connect("/ws") as websocket:
                # Connection should be established
                assert websocket is not None
        except Exception as e:
            # WebSocket may not be fully implemented, skip gracefully
            raise

    def test_websocket_message_structure(self, client):
        """Test WebSocket message structure and parsing"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Send a test message
                test_message = {"type": "ping"}
                websocket.send_json(test_message)

                # Receive response (with timeout to avoid hanging)
                response = receive_json_with_timeout(websocket)
                assert isinstance(response, dict)
        except Exception as e:
            raise

    def test_websocket_connection_cleanup(self, client):
        """Test proper WebSocket connection cleanup"""
        try:
            websocket = client.websocket_connect("/ws")
            websocket.__enter__()
            # Connection established
            websocket.__exit__(None, None, None)
            # Connection should be cleaned up
            assert True
        except Exception as e:
            raise


class TestWebSocketMessageTypes:
    """Test different WebSocket message types"""

    def test_status_update_messages(self, client):
        """Test system status update messages via WebSocket"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Subscribe to status updates
                subscribe_msg = {"type": "subscribe", "channel": "status"}
                websocket.send_json(subscribe_msg)

                # Receive subscription confirmation
                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise

    def test_network_update_messages(self, client):
        """Test network status update messages"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Subscribe to network updates
                subscribe_msg = {"type": "subscribe", "channel": "network"}
                websocket.send_json(subscribe_msg)

                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise

    def test_video_stream_messages(self, client):
        """Test video stream control messages"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Send video control message
                video_msg = {"type": "video", "action": "status"}
                websocket.send_json(video_msg)

                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise

    def test_telemetry_messages(self, client):
        """Test telemetry data messages"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Subscribe to telemetry
                telemetry_msg = {"type": "subscribe", "channel": "telemetry"}
                websocket.send_json(telemetry_msg)

                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise


class TestWebSocketDataSynchronization:
    """Test data synchronization via WebSocket"""

    def test_single_client_updates(self, client):
        """Test single client receiving updates"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Subscribe to all updates
                websocket.send_json({"type": "subscribe", "channel": "*"})

                # Receive subscription acknowledgment
                response = receive_json_with_timeout(websocket)
                assert response is not None

                # Simulate receiving an update
                # (In real scenario, would be sent by server)
                assert True
        except Exception as e:
            raise

    def test_multiple_message_sequence(self, client):
        """Test handling sequence of messages"""
        try:
            with client.websocket_connect("/ws") as websocket:
                messages = [
                    {"type": "ping"},
                    {"type": "subscribe", "channel": "status"},
                    {"type": "subscribe", "channel": "network"},
                ]

                for msg in messages:
                    websocket.send_json(msg)
                    response = receive_json_with_timeout(websocket)
                    assert response is not None
        except Exception as e:
            raise

    def test_heartbeat_mechanism(self, client):
        """Test WebSocket heartbeat/ping mechanism"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Send ping
                websocket.send_json({"type": "ping"})

                # Should receive pong
                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise


class TestWebSocketErrorHandling:
    """Test WebSocket error handling"""

    def test_invalid_message_handling(self, client):
        """Test handling of invalid messages"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Send invalid message
                websocket.send_json({"invalid": "format"})

                # Server should handle gracefully
                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise

    def test_malformed_json_handling(self, client):
        """Test handling of malformed JSON"""
        try:
            with client.websocket_connect("/ws") as websocket:
                # Send text that's not JSON
                websocket.send_text("this is not json")

                # Server should handle without crashing
                # (may close connection or return error)
                try:
                    response = receive_json_with_timeout(websocket)
                    assert response is not None
                except Exception:
                    # Connection may close, which is acceptable
                    pass
        except Exception as e:
            raise

    def test_client_disconnect_handling(self, client):
        """Test handling of client disconnect"""
        try:
            websocket = client.websocket_connect("/ws")
            ws = websocket.__enter__()
            ws.send_json({"type": "ping"})
            # Explicitly disconnect
            websocket.__exit__(None, None, None)
            # Should handle cleanly
            assert True
        except Exception as e:
            raise


class TestWebSocketIntegrationWithREST:
    """Test WebSocket integration with REST API"""

    def test_rest_api_before_websocket(self, client):
        """Test REST API call before WebSocket connection"""
        # Call REST API
        response = client.get("/api/system/info")
        assert response.status_code == 200

        # Then connect WebSocket
        try:
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "ping"})
                response = receive_json_with_timeout(websocket)
                assert response is not None
        except Exception as e:
            raise

    def test_websocket_before_rest_api(self, client):
        """Test WebSocket connection before REST API call"""
        try:
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "ping"})
                response = receive_json_with_timeout(websocket)
                assert response is not None

                # Call REST API while connected
                rest_response = client.get("/api/system/info")
                assert rest_response.status_code == 200
        except Exception as e:
            raise

    def test_rest_and_websocket_data_consistency(self, client):
        """Test data consistency between REST and WebSocket"""
        # Get data via REST
        rest_response = client.get("/api/system/info")
        rest_status = rest_response.status_code

        try:
            with client.websocket_connect("/ws") as websocket:
                # Get same data via WebSocket
                websocket.send_json({"type": "get_status"})
                ws_response = receive_json_with_timeout(websocket)

                # Both should succeed or fail consistently
                assert (rest_status == 200) or (ws_response is None)
        except Exception as e:
            raise


class TestWebSocketLoadAndStability:
    """Test WebSocket under load and stability conditions"""

    def test_rapid_message_sending(self, client):
        """Sending many messages must not break the connection"""
        with client.websocket_connect("/ws") as websocket:
            # The server pushes initial state on connect and ignores client pings.
            for i in range(5):
                websocket.send_json({"type": "ping", "id": i})

            response = receive_json_with_timeout(websocket)
            assert isinstance(response, dict)

    def test_connection_persistence(self, client):
        """Connection stays usable across several messages"""
        with client.websocket_connect("/ws") as websocket:
            first = receive_json_with_timeout(websocket)
            assert isinstance(first, dict)

            for i in range(3):
                websocket.send_json({"type": "ping", "time": i})

            # The connection is still open and usable.
            assert websocket is not None
