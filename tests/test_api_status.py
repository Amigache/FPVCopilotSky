"""
Tests for API Status Endpoints

Basic tests for the status and health check endpoints
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestStatusEndpoints:
    """Test /api/status endpoints"""

    def test_status_endpoint_exists(self):
        """Test that status endpoint is accessible"""
        response = client.get("/api/status")
        assert response.status_code == 200

    def test_status_returns_json(self):
        """Test that status returns valid JSON"""
        response = client.get("/api/status")
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert isinstance(data, dict)

    def test_status_has_required_fields(self):
        """Test that status response has expected structure"""
        response = client.get("/api/status")
        data = response.json()

        # Check for common status fields
        assert "success" in data or "status" in data

    def test_mavlink_status_endpoint(self):
        """Test MAVLink status endpoint"""
        response = client.get("/api/mavlink/status")

        # Should return 200 or 503 depending on connection state
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "connected" in data

    def test_video_sources_endpoint(self):
        """Test video sources listing endpoint"""
        response = client.get("/api/video/sources")

        # Should succeed even with no cameras
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_router_outputs_endpoint(self):
        """Test router outputs listing"""
        response = client.get("/api/mavlink-router/outputs")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestAPIHealthCheck:
    """Test API health and availability"""

    def test_root_endpoint(self):
        """Test root endpoint redirects or returns info"""
        response = client.get("/")

        # Should either redirect or return 200
        assert response.status_code in [200, 307, 404]

    def test_api_docs_accessible(self):
        """Test that API documentation is accessible"""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self):
        """Test OpenAPI schema is available"""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema


class TestAPIErrorHandling:
    """Test API error handling"""

    def test_invalid_endpoint_returns_404(self):
        """Test that invalid endpoints return 404"""
        response = client.get("/api/nonexistent/endpoint")
        assert response.status_code == 404

    def test_invalid_method_returns_405(self):
        """Test that invalid HTTP methods return 405"""
        response = client.post("/api/status")
        # Status is GET only, POST should fail
        assert response.status_code == 405

    def test_malformed_json_returns_422(self):
        """Test that malformed JSON in POST returns 422"""
        response = client.post(
            "/api/mavlink-router/outputs",
            json={"invalid": "data"},  # Missing required fields
        )

        # Should return validation error
        assert response.status_code in [422, 400]


@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for API endpoints"""

    def test_multiple_concurrent_requests(self):
        """Test handling multiple concurrent requests"""
        import concurrent.futures

        def make_request():
            return client.get("/api/status")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed
        assert all(r.status_code == 200 for r in results)

    def test_api_response_times(self):
        """Test that API responses are reasonably fast"""
        import time

        start = time.time()
        response = client.get("/api/status")
        elapsed = time.time() - start

        assert response.status_code == 200
        # Status endpoint should respond in <100ms
        assert elapsed < 0.1, f"Status endpoint too slow: {elapsed:.3f}s"
