import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import json

# Assuming your app structure - adjust imports as needed
from app.main import app
from app.api.routes.router import AddOutputRequest, UpdateOutputRequest

client = TestClient(app)


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
        with pytest.raises(ValueError, match="Port must be between"):
            AddOutputRequest(type="udp", host="127.0.0.1", port=1000)

        # Test port too high
        with pytest.raises(ValueError, match="Port must be between"):
            AddOutputRequest(type="udp", host="127.0.0.1", port=70000)

    def test_add_output_request_host_validation(self):
        """Test AddOutputRequest host validation"""
        # Test invalid IP format
        with pytest.raises(ValueError, match="Invalid IP address"):
            AddOutputRequest(type="udp", host="invalid.ip", port=14550)

        # Test valid IP formats
        valid_ips = ["127.0.0.1", "0.0.0.0", "192.168.1.100", "255.255.255.255"]
        for ip in valid_ips:
            request = AddOutputRequest(type="udp", host=ip, port=14550)
            assert request.host == ip

    def test_add_output_request_type_validation(self):
        """Test AddOutputRequest type validation"""
        valid_types = ["tcp_server", "tcp_client", "udp"]

        for output_type in valid_types:
            request = AddOutputRequest(type=output_type, host="127.0.0.1", port=14550)
            assert request.type == output_type


class TestMAVLinkRouterAPI:
    """Test MAVLink Router API endpoints"""

    @patch("app.services.router.RouterService")
    def test_get_outputs_success(self, mock_router_service):
        """Test GET /api/mavlink-router/outputs success"""
        # Mock service response
        mock_service_instance = Mock()
        mock_service_instance.get_outputs.return_value = [
            {"id": "test1", "type": "udp", "host": "127.0.0.1", "port": 14550, "running": True, "clients": 0}
        ]
        mock_router_service.return_value = mock_service_instance

        response = client.get("/api/mavlink-router/outputs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type"] == "udp"
        assert data[0]["port"] == 14550

    @patch("app.services.router.RouterService")
    def test_get_outputs_service_error(self, mock_router_service):
        """Test GET /api/mavlink-router/outputs service error"""
        mock_service_instance = Mock()
        mock_service_instance.get_outputs.side_effect = Exception("Service error")
        mock_router_service.return_value = mock_service_instance

        response = client.get("/api/mavlink-router/outputs")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "Failed to get outputs" in data["error"]

    @patch("app.services.router.RouterService")
    def test_create_output_success(self, mock_router_service):
        """Test POST /api/mavlink-router/outputs success"""
        mock_service_instance = Mock()
        mock_service_instance.add_output.return_value = {
            "success": True,
            "message": "Output created successfully",
            "output_id": "test-id",
        }
        mock_router_service.return_value = mock_service_instance

        payload = {"type": "udp", "host": "192.168.1.100", "port": 5760}

        response = client.post("/api/mavlink-router/outputs", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Output created successfully" in data["message"]

    @patch("app.services.router.RouterService")
    def test_create_output_validation_error(self, mock_router_service):
        """Test POST /api/mavlink-router/outputs validation error"""
        # Invalid data - port out of range
        payload = {"type": "udp", "host": "127.0.0.1", "port": 100}  # Too low

        response = client.post("/api/mavlink-router/outputs", json=payload)

        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

    @patch("app.services.router.RouterService")
    def test_create_output_port_conflict(self, mock_router_service):
        """Test POST /api/mavlink-router/outputs port conflict"""
        mock_service_instance = Mock()
        mock_service_instance.add_output.side_effect = ValueError("Port 14550 is already in use")
        mock_router_service.return_value = mock_service_instance

        payload = {"type": "udp", "host": "127.0.0.1", "port": 14550}

        response = client.post("/api/mavlink-router/outputs", json=payload)

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "Port 14550 is already in use" in data["error"]

    @patch("app.services.router.RouterService")
    def test_delete_output_success(self, mock_router_service):
        """Test DELETE /api/mavlink-router/outputs/{output_id} success"""
        mock_service_instance = Mock()
        mock_service_instance.remove_output.return_value = {"success": True, "message": "Output removed successfully"}
        mock_router_service.return_value = mock_service_instance

        response = client.delete("/api/mavlink-router/outputs/test-id")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @patch("app.services.router.RouterService")
    def test_delete_output_not_found(self, mock_router_service):
        """Test DELETE /api/mavlink-router/outputs/{output_id} not found"""
        mock_service_instance = Mock()
        mock_service_instance.remove_output.side_effect = KeyError("Output not found")
        mock_router_service.return_value = mock_service_instance

        response = client.delete("/api/mavlink-router/outputs/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "Output not found" in data["error"]

    @patch("app.services.router.RouterService")
    def test_restart_output_success(self, mock_router_service):
        """Test POST /api/mavlink-router/outputs/{output_id}/restart success"""
        mock_service_instance = Mock()
        mock_service_instance.restart_output.return_value = {
            "success": True,
            "message": "Output restarted successfully",
        }
        mock_router_service.return_value = mock_service_instance

        response = client.post("/api/mavlink-router/outputs/test-id/restart")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @patch("app.services.router.RouterService")
    def test_get_presets_success(self, mock_router_service):
        """Test GET /api/mavlink-router/presets success"""
        mock_service_instance = Mock()
        mock_service_instance.get_presets.return_value = {
            "success": True,
            "presets": {
                "qgc": {"type": "udp", "host": "255.255.255.255", "port": 14550},
                "missionplanner": {"type": "tcp_client", "host": "127.0.0.1", "port": 5760},
            },
        }
        mock_router_service.return_value = mock_service_instance

        response = client.get("/api/mavlink-router/presets")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "presets" in data
        assert "qgc" in data["presets"]
        assert "missionplanner" in data["presets"]

    @patch("app.services.router.RouterService")
    def test_restart_router_success(self, mock_router_service):
        """Test POST /api/mavlink-router/restart success"""
        mock_service_instance = Mock()
        mock_service_instance.restart_router.return_value = {
            "success": True,
            "message": "Router restarted successfully",
        }
        mock_router_service.return_value = mock_service_instance

        response = client.post("/api/mavlink-router/restart")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestMAVLinkRouterIntegration:
    """Integration tests for MAVLink Router functionality"""

    @patch("app.services.router.RouterService")
    def test_full_output_lifecycle(self, mock_router_service):
        """Test complete output lifecycle: create, get, restart, delete"""
        mock_service_instance = Mock()

        # Mock create output
        mock_service_instance.add_output.return_value = {
            "success": True,
            "message": "Output created",
            "output_id": "test-lifecycle",
        }

        # Mock get outputs
        mock_service_instance.get_outputs.return_value = [
            {"id": "test-lifecycle", "type": "udp", "host": "127.0.0.1", "port": 14550, "running": True, "clients": 0}
        ]

        # Mock restart output
        mock_service_instance.restart_output.return_value = {"success": True, "message": "Output restarted"}

        # Mock delete output
        mock_service_instance.remove_output.return_value = {"success": True, "message": "Output removed"}

        mock_router_service.return_value = mock_service_instance

        # 1. Create output
        create_response = client.post(
            "/api/mavlink-router/outputs", json={"type": "udp", "host": "127.0.0.1", "port": 14550}
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
