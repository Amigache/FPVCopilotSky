"""
Experimental API Routes Tests

Tests for experimental features API endpoints including OpenCV
configuration, toggle, and status management.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


class TestExperimentalRouteModule:
    """Test experimental route module"""

    def test_experimental_route_can_import(self):
        """Test that experimental route can be imported"""
        from app.api.routes import experimental

        assert hasattr(experimental, "router"), "Experimental module should have router"

    def test_experimental_has_endpoints(self):
        """Test that experimental router has expected endpoints"""
        from app.api.routes import experimental

        # Get routes from router
        routes = [route.path for route in experimental.router.routes]

        # Routes have full prefix
        assert "/api/experimental/config" in routes or any("/config" in r for r in routes)
        assert "/api/experimental/toggle" in routes or any("/toggle" in r for r in routes)
        assert "/api/experimental/status" in routes or any("/status" in r for r in routes)


class TestExperimentalEndpointsExist:
    """Test experimental endpoints exist and respond"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test client"""
        from app.main import app

        self.client = TestClient(app)

    def test_get_config_endpoint_exists(self):
        """Test GET /api/experimental/config endpoint exists"""
        response = self.client.get("/api/experimental/config")
        # Should return 200 or 503 (not 404)
        assert response.status_code in [200, 503]

    def test_post_config_endpoint_exists(self):
        """Test POST /api/experimental/config endpoint exists"""
        response = self.client.post("/api/experimental/config", json={"filter": "edges"})
        # Should return 200, 503, or 422 (not 404)
        assert response.status_code in [200, 422, 503]

    def test_post_toggle_endpoint_exists(self):
        """Test POST /api/experimental/toggle endpoint exists"""
        response = self.client.post("/api/experimental/toggle", json={"enabled": True})
        # Should return 200 or 503 (not 404)
        assert response.status_code in [200, 503]

    def test_get_status_endpoint_exists(self):
        """Test GET /api/experimental/status endpoint exists"""
        response = self.client.get("/api/experimental/status")
        # Should always return 200 (even if service not init, returns success=False)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data


class TestExperimentalRequestValidation:
    """Test request validation"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test client"""
        from app.main import app

        self.client = TestClient(app)

    def test_toggle_requires_enabled_field(self):
        """Test toggle endpoint requires enabled field"""
        response = self.client.post("/api/experimental/toggle", json={})
        assert response.status_code == 422  # Validation error

    def test_toggle_enabled_must_be_boolean(self):
        """Test enabled field must be boolean"""
        response = self.client.post("/api/experimental/toggle", json={"enabled": "not_a_boolean"})
        assert response.status_code == 422  # Validation error

    def test_config_with_invalid_types(self):
        """Test config validates types"""
        response = self.client.post("/api/experimental/config", json={"edgeThreshold1": "not_an_int"})
        assert response.status_code == 422  # Validation error


class TestExperimentalServiceFunctions:
    """Test experimental service functions directly"""

    def test_set_opencv_service(self):
        """Test setting OpenCV service"""
        from app.api.routes import experimental

        mock_service = Mock()
        experimental.set_opencv_service(mock_service)
        assert experimental._opencv_service is mock_service

    def test_set_opencv_service_to_none(self):
        """Test setting service to None"""
        from app.api.routes import experimental

        experimental.set_opencv_service(None)
        assert experimental._opencv_service is None
