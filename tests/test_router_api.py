import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import json
from pydantic import ValidationError

# Assuming your app structure - adjust imports as needed
from app.main import app
from app.api.routes.router import AddOutputRequest, UpdateOutputRequest, set_router_service


@pytest.fixture
def mock_router_service():
    """Create a mock router service for testing"""
    mock_service = Mock()
    # Set default return values for common methods
    mock_service.get_status.return_value = {"outputs": []}
    mock_service.outputs = {}
    set_router_service(mock_service)
    yield mock_service
    # Cleanup: reset service after test
    set_router_service(None)


@pytest.fixture
def client(mock_router_service):
    """Create test client with mocked router service"""
    return TestClient(app)


class TestMAVLinkRouterModels:
    """Test Pydantic models for MAVLink Router API"""

    def test_add_output_request_valid_data(self):
        """Test AddOutputRequest with valid data"""
        valid_data = {"type": "udp", "host": "127.0.0.1", "port": 14550}

        request = AddOutputRequest(**valid_data)

        assert request.type == "udp"
        assert request.host == "127.0.0.1"
        assert request.port == 14550

    def test_add_output_request_port_validation(self):
        """Test AddOutputRequest port validation"""
        # Test port too low
        with pytest.raises(ValidationError, match="greater than or equal to"):
            AddOutputRequest(type="udp", host="127.0.0.1", port=1000)

        # Test port too high
        with pytest.raises(ValidationError, match="less than or equal to"):
            AddOutputRequest(type="udp", host="127.0.0.1", port=70000)

    def test_add_output_request_host_validation(self):
        """Test AddOutputRequest host validation (accepts both IPs and hostnames)"""
        # Test valid IP formats
        valid_ips = ["127.0.0.1", "0.0.0.0", "192.168.1.100", "255.255.255.255"]
        for ip in valid_ips:
            request = AddOutputRequest(type="udp", host=ip, port=14550)
            assert request.host == ip

        # Test valid hostnames/DNS
        valid_hosts = ["localhost", "my-drone.local", "vpn.example.com"]
        for host in valid_hosts:
            request = AddOutputRequest(type="udp", host=host, port=14550)
            assert request.host == host

    def test_add_output_request_type_validation(self):
        """Test AddOutputRequest type validation"""
        valid_types = ["tcp_server", "tcp_client", "udp"]

        for output_type in valid_types:
            request = AddOutputRequest(type=output_type, host="127.0.0.1", port=14550)
            assert request.type == output_type


class TestMAVLinkRouterAPI:
    """Test MAVLink Router API endpoints"""

    def test_get_outputs_success(self, client, mock_router_service):
        """Test GET /api/mavlink-router/outputs success"""
        # Mock service response
        mock_router_service.get_status.return_value = {
            "outputs": [
                {"id": "test1", "type": "udp", "host": "127.0.0.1", "port": 14550, "running": True, "clients": 0}
            ]
        }

        response = client.get("/api/mavlink-router/outputs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type"] == "udp"
        assert data[0]["port"] == 14550

    def test_get_outputs_service_error(self, client, mock_router_service):
        """Test GET /api/mavlink-router/outputs service error"""
        mock_router_service.get_status.side_effect = Exception("Service error")

        response = client.get("/api/mavlink-router/outputs")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "Failed to get outputs" in data["error"]

    def test_create_output_success(self, client, mock_router_service):
        """Test POST /api/mavlink-router/outputs success"""
        # Mock get_status for conflict check (returns empty outputs)
        mock_router_service.get_status.return_value = {"outputs": []}
        # Mock add_output to return success
        mock_router_service.add_output.return_value = (True, "Output created successfully")

        payload = {"type": "udp", "host": "192.168.1.100", "port": 5760}

        response = client.post("/api/mavlink-router/outputs", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_create_output_validation_error(self, client, mock_router_service):
        """Test POST /api/mavlink-router/outputs validation error"""
        # Invalid data - port out of range
        payload = {"type": "udp", "host": "127.0.0.1", "port": 100}  # Too low

        response = client.post("/api/mavlink-router/outputs", json=payload)

        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

    def test_create_output_port_conflict(self, client, mock_router_service):
        """Test POST /api/mavlink-router/outputs port conflict"""
        # Mock get_status to return existing output with same host:port
        mock_router_service.get_status.return_value = {"outputs": [{"host": "127.0.0.1", "port": 14550, "type": "udp"}]}

        payload = {"type": "udp", "host": "127.0.0.1", "port": 14550}

        response = client.post("/api/mavlink-router/outputs", json=payload)

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "already in use" in data["error"]

    def test_delete_output_success(self, client, mock_router_service):
        """Test DELETE /api/mavlink-router/outputs/{output_id} success"""
        # Mock outputs to contain the test output
        mock_router_service.outputs = {"test-id": Mock()}
        # Mock remove_output to return success
        mock_router_service.remove_output.return_value = (True, "Output removed successfully")

        response = client.delete("/api/mavlink-router/outputs/test-id")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_delete_output_not_found(self, client, mock_router_service):
        """Test DELETE /api/mavlink-router/outputs/{output_id} not found"""
        # Mock outputs as empty dict (output doesn't exist)
        mock_router_service.outputs = {}

        response = client.delete("/api/mavlink-router/outputs/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_restart_output_success(self, client, mock_router_service):
        """Test POST /api/mavlink-router/outputs/{output_id}/restart success"""
        # Mock outputs to contain the test output
        mock_router_service.outputs = {"test-id": Mock()}
        # Mock restart_output to return success
        mock_router_service.restart_output.return_value = (True, "Output restarted successfully")

        response = client.post("/api/mavlink-router/outputs/test-id/restart")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_get_presets_success(self, client):
        """Test GET /api/mavlink-router/presets success (no mocking needed - returns static data)"""
        response = client.get("/api/mavlink-router/presets")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "presets" in data
        assert "qgc" in data["presets"]
        assert "missionplanner" in data["presets"]

    def test_restart_router_success(self, client, mock_router_service):
        """Test POST /api/mavlink-router/restart success"""
        # Mock restart to return success
        mock_router_service.restart.return_value = (True, "Router restarted successfully")

        response = client.post("/api/mavlink-router/restart")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestMAVLinkRouterIntegration:
    """Integration tests for MAVLink Router functionality"""

    def test_full_output_lifecycle(self, client, mock_router_service):
        """Test complete output lifecycle: create, get, restart, delete"""

        # Mock get_status for conflict check and get operations
        mock_router_service.get_status.return_value = {
            "outputs": [
                {
                    "id": "test-lifecycle",
                    "type": "udp",
                    "host": "127.0.0.1",
                    "port": 14550,
                    "running": True,
                    "clients": 0,
                }
            ]
        }

        # Mock add_output to return success
        mock_router_service.add_output.return_value = (True, "Output created")

        # Mock outputs dict for restart and delete checks
        mock_router_service.outputs = {"test-lifecycle": Mock()}

        # Mock restart_output to return success
        mock_router_service.restart_output.return_value = (True, "Output restarted")

        # Mock remove_output to return success
        mock_router_service.remove_output.return_value = (True, "Output removed")

        # 1. Create output
        create_response = client.post(
            "/api/mavlink-router/outputs", json={"type": "udp", "host": "127.0.0.1", "port": 14551}
        )
        assert create_response.status_code == 200

        # 2. Get outputs
        get_response = client.get("/api/mavlink-router/outputs")
        assert get_response.status_code == 200
        outputs = get_response.json()
        assert len(outputs) == 1

        # 3. Restart output
        restart_response = client.post("/api/mavlink-router/outputs/test-lifecycle/restart")
        assert restart_response.status_code == 200

        # 4. Delete output
        delete_response = client.delete("/api/mavlink-router/outputs/test-lifecycle")
        assert delete_response.status_code == 200
