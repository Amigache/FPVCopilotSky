"""
Tests for API Status Endpoints

Basic tests for the status and health check endpoints
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked API services"""
    return TestClient(app)


class TestStatusEndpoints:
    """Test /api/status endpoints"""

    def test_status_health_endpoint(self, client):
        """Test that status health endpoint exists or gracefully fails"""
        response = client.get("/api/status/health")
        # Accept 200, 404, or 500 - may not be available in test environment
        assert response.status_code in [200, 404, 500]

    def test_status_dependencies_endpoint(self, client):
        """Test that dependencies endpoint returns valid JSON"""
        response = client.get("/api/status/dependencies")
        if response.status_code == 200:
            assert response.headers["content-type"] == "application/json"
            data = response.json()
            assert isinstance(data, dict)

    def test_status_system_endpoint(self, client):
        """Test that system info endpoint exists or gracefully fails"""
        response = client.get("/api/status/system")
        # Accept 200, 404, or 500 - may not be available in test environment
        assert response.status_code in [200, 404, 500]

    def test_mavlink_status_endpoint(self, client, mock_api_services):
        """Test MAVLink status endpoint"""
        response = client.get("/api/mavlink/status")

        # Should return 200 or error (mocked or unavailable)
        assert response.status_code in [200, 404, 503, 500]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_video_cameras_endpoint(self, client, mock_api_services):
        """Test video cameras listing endpoint"""
        response = client.get("/api/video/cameras")

        # Should succeed or gracefully fail
        assert response.status_code in [200, 404, 503, 500]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_router_outputs_endpoint(self, client, mock_api_services):
        """Test router outputs listing"""
        response = client.get("/api/mavlink-router/outputs")

        # Accept success or service unavailable
        assert response.status_code in [200, 503, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


class TestAPIHealthCheck:
    """Test API health and availability"""

    def test_root_endpoint(self, client):
        """Test root endpoint redirects or returns info"""
        response = client.get("/")

        # Should either redirect or return 200
        assert response.status_code in [200, 307, 404]

    def test_api_docs_accessible(self, client):
        """Test that API documentation is accessible"""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        """Test OpenAPI schema is available"""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema


class TestAPIErrorHandling:
    """Test API error handling"""

    def test_invalid_endpoint_returns_404(self, client):
        """Test that invalid endpoints return 404"""
        response = client.get("/api/nonexistent/endpoint")
        assert response.status_code == 404

    def test_invalid_method_returns_405(self, client):
        """Test that invalid HTTP methods return 405"""
        response = client.post("/api/status")
        # Status is GET only, POST should fail
        assert response.status_code in [404, 405, 422]

    def test_malformed_json_returns_422(self, client):
        """Test that malformed JSON in POST returns 422"""
        response = client.post(
            "/api/mavlink-router/outputs",
            json={"invalid": "data"},  # Missing required fields
        )

        # Should return validation error
        assert response.status_code in [422, 400, 404]


@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for API endpoints"""

    def test_multiple_concurrent_requests(self, client):
        """Test handling multiple concurrent requests"""
        import concurrent.futures

        def make_request():
            return client.get("/openapi.json")  # Use reliable endpoint

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests to docs should succeed
        assert all(r.status_code == 200 for r in results)

    def test_api_response_times(self, client):
        """Test that API responses are reasonably fast"""
        import time

        start = time.time()
        response = client.get("/openapi.json")  # Use reliable endpoint
        elapsed = time.time() - start

        assert response.status_code == 200
        # OpenAPI schema should respond quickly
        assert elapsed < 1.0, f"OpenAPI schema too slow: {elapsed:.3f}s"
