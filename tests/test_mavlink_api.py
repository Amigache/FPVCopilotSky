"""
MAVLink API Routes Tests

Tests for /api/mavlink/* endpoints including connect, disconnect,
status, parameters, and preferences.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass


@dataclass
class MockSerialConfig:
    """Mock SerialConfig matching app.services.preferences.SerialConfig"""

    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    auto_connect: bool = False
    last_successful: bool = False


# --- Fixtures ---


@pytest.fixture
def mock_mavlink_service():
    """Mock mavlink_service injected into routes"""
    mock = Mock()
    mock.connected = False
    mock.is_connected.return_value = False
    mock.get_status.return_value = {
        "connected": False,
        "system_id": None,
        "component_id": None,
    }
    mock.connect.return_value = {"success": True, "message": "Connected"}
    mock.disconnect.return_value = {"success": True, "message": "Disconnected"}
    mock.get_parameters_batch.return_value = {
        "parameters": {"RC_PROTOCOLS": 0, "FS_GCS_ENABLE": 1},
        "errors": [],
    }
    mock.set_parameters_batch.return_value = {
        "success": True,
        "results": {"RC_PROTOCOLS": {"success": True, "value": 0}},
    }
    with patch("app.api.routes.mavlink.mavlink_service", mock):
        yield mock


@pytest.fixture
def mock_mavlink_service_connected():
    """Mock mavlink_service in connected state"""
    mock = Mock()
    mock.connected = True
    mock.is_connected.return_value = True
    mock.get_status.return_value = {
        "connected": True,
        "system_id": 1,
        "component_id": 1,
    }
    mock.connect.return_value = {"success": True, "message": "Connected"}
    mock.disconnect.return_value = {"success": True, "message": "Disconnected"}
    mock.get_parameters_batch.return_value = {
        "parameters": {"RC_PROTOCOLS": 0, "FS_GCS_ENABLE": 1},
        "errors": [],
    }
    mock.set_parameters_batch.return_value = {
        "success": True,
        "results": {"RC_PROTOCOLS": {"success": True, "value": 256}},
    }
    with patch("app.api.routes.mavlink.mavlink_service", mock):
        yield mock


@pytest.fixture
def mock_serial_preferences():
    """Mock preferences for serial config"""
    config = MockSerialConfig()

    def get_serial_config():
        return config

    def set_serial_auto_connect(val):
        config.auto_connect = val

    def set_serial_config(**kwargs):
        for k, v in kwargs.items():
            if hasattr(config, k):
                setattr(config, k, v)

    mock_prefs = Mock()
    mock_prefs.get_serial_config = Mock(side_effect=get_serial_config)
    mock_prefs.set_serial_auto_connect = Mock(side_effect=set_serial_auto_connect)
    mock_prefs.set_serial_config = Mock(side_effect=set_serial_config)

    with patch("app.services.preferences.get_preferences", return_value=mock_prefs):
        yield mock_prefs, config


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked API services"""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


class TestMAVLinkConnect:
    """Tests for POST /api/mavlink/connect"""

    def test_connect_success(self, client, mock_mavlink_service):
        """Should connect with port and baudrate"""
        response = client.post(
            "/api/mavlink/connect",
            json={"port": "/dev/ttyUSB0", "baudrate": 115200},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_mavlink_service.connect.assert_called_once_with("/dev/ttyUSB0", 115200)

    def test_connect_failure(self, client, mock_mavlink_service):
        """Should return 400 on connection failure"""
        mock_mavlink_service.connect.return_value = {
            "success": False,
            "message": "Port busy",
        }
        response = client.post(
            "/api/mavlink/connect",
            json={"port": "/dev/ttyUSB0", "baudrate": 115200},
        )
        assert response.status_code == 400

    def test_connect_default_baudrate(self, client, mock_mavlink_service):
        """Should use default baudrate 115200 when not specified"""
        response = client.post(
            "/api/mavlink/connect",
            json={"port": "/dev/ttyUSB0"},
        )
        assert response.status_code == 200
        mock_mavlink_service.connect.assert_called_once_with("/dev/ttyUSB0", 115200)

    def test_connect_no_service_returns_500(self, client):
        """Should return 500 when mavlink_service not initialized"""
        with patch("app.api.routes.mavlink.mavlink_service", None):
            response = client.post(
                "/api/mavlink/connect",
                json={"port": "/dev/ttyUSB0", "baudrate": 115200},
            )
            assert response.status_code == 500

    def test_connect_missing_port_returns_422(self, client, mock_mavlink_service):
        """Should return 422 when port is missing"""
        response = client.post("/api/mavlink/connect", json={})
        assert response.status_code == 422


class TestMAVLinkDisconnect:
    """Tests for POST /api/mavlink/disconnect"""

    def test_disconnect_success(self, client, mock_mavlink_service):
        """Should disconnect successfully"""
        response = client.post("/api/mavlink/disconnect")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_disconnect_not_connected(self, client, mock_mavlink_service):
        """Should handle disconnect when not connected"""
        mock_mavlink_service.disconnect.return_value = {
            "success": False,
            "message": "Not connected",
        }
        mock_mavlink_service.connected = False
        response = client.post("/api/mavlink/disconnect")
        # The route returns the result from the service
        data = response.json()
        assert isinstance(data, dict)


class TestMAVLinkStatus:
    """Tests for GET /api/mavlink/status"""

    def test_get_status_disconnected(self, client, mock_mavlink_service):
        """Should return disconnected status"""
        response = client.get("/api/mavlink/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_get_status_connected(self, client, mock_mavlink_service_connected):
        """Should return connected status with system info"""
        response = client.get("/api/mavlink/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["system_id"] == 1


class TestMAVLinkParameters:
    """Tests for parameter batch endpoints"""

    def test_batch_get_connected(self, client, mock_mavlink_service_connected):
        """Should return parameters when connected"""
        response = client.post(
            "/api/mavlink/params/batch/get",
            json={"params": ["RC_PROTOCOLS", "FS_GCS_ENABLE"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "parameters" in data
        assert data["parameters"]["RC_PROTOCOLS"] == 0

    def test_batch_get_not_connected(self, client, mock_mavlink_service):
        """Should return 400 when not connected"""
        mock_mavlink_service.connected = False
        response = client.post(
            "/api/mavlink/params/batch/get",
            json={"params": ["RC_PROTOCOLS"]},
        )
        assert response.status_code == 400

    def test_batch_set_connected(self, client, mock_mavlink_service_connected):
        """Should set parameters when connected"""
        response = client.post(
            "/api/mavlink/params/batch/set",
            json={"params": {"RC_PROTOCOLS": 256}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_batch_set_not_connected(self, client, mock_mavlink_service):
        """Should return 400 when not connected"""
        mock_mavlink_service.connected = False
        response = client.post(
            "/api/mavlink/params/batch/set",
            json={"params": {"RC_PROTOCOLS": 256}},
        )
        assert response.status_code == 400


class TestMAVLinkPreferences:
    """Tests for GET/POST /api/mavlink/preferences"""

    def test_get_preferences_returns_port_and_baudrate(self, client, mock_serial_preferences):
        """GET /preferences should return port, baudrate, and auto_connect"""
        response = client.get("/api/mavlink/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        prefs = data["preferences"]
        assert "port" in prefs
        assert "baudrate" in prefs
        assert "auto_connect" in prefs
        assert prefs["port"] == "/dev/ttyUSB0"
        assert prefs["baudrate"] == 115200

    def test_get_preferences_auto_connect_default(self, client, mock_serial_preferences):
        """GET /preferences should return auto_connect=false by default"""
        response = client.get("/api/mavlink/preferences")
        data = response.json()
        assert data["preferences"]["auto_connect"] is False

    def test_save_preferences_auto_connect(self, client, mock_serial_preferences):
        """POST /preferences should save auto_connect"""
        response = client.post(
            "/api/mavlink/preferences",
            json={"auto_connect": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["preferences"]["auto_connect"] is True

    def test_save_preferences_toggle_off(self, client, mock_serial_preferences):
        """POST /preferences should toggle auto_connect off"""
        # First enable
        client.post("/api/mavlink/preferences", json={"auto_connect": True})
        # Then disable
        response = client.post(
            "/api/mavlink/preferences",
            json={"auto_connect": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"]["auto_connect"] is False


class TestGCSOnlyEndpointsRemoved:
    """Verify dead GCS_ONLY endpoints have been removed"""

    def test_gcs_only_get_returns_404(self, client, mock_mavlink_service_connected):
        """GET /params/gcs-only should return 404 (removed)"""
        response = client.get("/api/mavlink/params/gcs-only")
        assert response.status_code in (404, 405)

    def test_gcs_only_apply_returns_404(self, client, mock_mavlink_service_connected):
        """POST /params/gcs-only/apply should return 404 (removed)"""
        response = client.post("/api/mavlink/params/gcs-only/apply", json={})
        assert response.status_code in (404, 405)
