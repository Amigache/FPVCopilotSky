"""
Tests for System Logs Cache

Tests the caching mechanism using CacheService for system log retrieval
to prevent excessive journalctl/tail commands and improve performance.
"""

import pytest
import time
from unittest.mock import patch, Mock
from app.services.system_service import SystemService
from app.services.cache_service import get_cache_service


@pytest.fixture
def clear_cache():
    """Clear cache before each test"""
    cache = get_cache_service()
    cache.clear_all()
    yield
    cache.clear_all()


class TestBackendLogsCache:
    """Test backend logs caching (journalctl)"""

    @patch("subprocess.run")
    def test_cache_hit_returns_cached_logs(self, mock_run, clear_cache):
        """Test that cache returns same logs within TTL"""
        cache = get_cache_service()

        # Mock journalctl output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Mock backend log line 1\nMock backend log line 2"
        mock_run.return_value = mock_result

        # First call - cache miss
        logs1 = SystemService.get_backend_logs(100)
        assert "Mock backend log line 1" in logs1
        assert mock_run.call_count == 1

        # Verify cache was populated
        cached = cache.get("logs_backend")
        assert cached is not None

        # Second call immediately - cache hit
        logs2 = SystemService.get_backend_logs(100)
        assert logs2 == logs1
        assert mock_run.call_count == 1  # Not called again (cache hit)

    @patch("subprocess.run")
    def test_cache_expires_after_ttl(self, mock_run, clear_cache):
        """Test that cache expires after TTL (2 seconds)"""
        # Mock journalctl output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Log line"
        mock_run.return_value = mock_result

        # First call
        logs1 = SystemService.get_backend_logs(100)
        first_call_count = mock_run.call_count

        # Wait for cache to expire (2.1 seconds)
        time.sleep(2.1)

        # Second call - cache expired, should fetch again
        logs2 = SystemService.get_backend_logs(100)
        second_call_count = mock_run.call_count

        assert second_call_count > first_call_count  # Called again

    @patch("subprocess.run")
    def test_cache_timeout_handling(self, mock_run, clear_cache):
        """Test that timeout exceptions are handled gracefully"""
        # Mock timeout
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired("journalctl", 3)

        # Should return error message, not crash
        logs = SystemService.get_backend_logs(100)
        assert "timed out" in logs.lower()

    @patch("subprocess.run")
    def test_cache_error_handling(self, mock_run, clear_cache):
        """Test that errors are handled and returned as strings"""
        # Mock error
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"
        mock_run.return_value = mock_result

        # Should return error message
        logs = SystemService.get_backend_logs(100)
        assert "error" in logs.lower() or "permission denied" in logs.lower()


class TestFrontendLogsCache:
    """Test frontend logs caching (nginx logs)"""

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_cache_hit_returns_cached_logs(self, mock_run, mock_exists, clear_cache):
        """Test that cache returns same logs within TTL"""
        cache = get_cache_service()

        # Mock file existence and tail output
        mock_exists.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Nginx log line"
        mock_run.return_value = mock_result

        # First call - cache miss
        logs1 = SystemService.get_frontend_logs(100)
        first_call_count = mock_run.call_count

        # Verify cache was populated
        cached = cache.get("logs_frontend")
        assert cached is not None

        # Second call immediately - cache hit
        logs2 = SystemService.get_frontend_logs(100)
        assert logs2 == logs1
        assert mock_run.call_count == first_call_count  # Not called again

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_cache_combines_error_and_access_logs(self, mock_run, mock_exists, clear_cache):
        """Test that frontend combines nginx error and access logs"""
        # Mock file existence
        mock_exists.return_value = True

        # Mock tail output for both error and access logs
        error_result = Mock()
        error_result.returncode = 0
        error_result.stdout = "Error log content"

        access_result = Mock()
        access_result.returncode = 0
        access_result.stdout = "Access log content"

        # tail is called twice: once for error log, once for access log
        mock_run.side_effect = [error_result, access_result]

        logs = SystemService.get_frontend_logs(100)

        # Should contain both
        assert "Error Log" in logs
        assert "Access Log" in logs
        assert "Error log content" in logs
        assert "Access log content" in logs

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_cache_handles_missing_log_files(self, mock_run, mock_exists, clear_cache):
        """Test that missing log files are handled gracefully"""
        # Mock files don't exist
        mock_exists.return_value = False

        logs = SystemService.get_frontend_logs(100)
        assert "No frontend logs available" in logs


class TestLogsCachePerformance:
    """Test that cache improves performance"""

    @patch("subprocess.run")
    def test_multiple_rapid_calls_use_cache(self, mock_run, clear_cache):
        """Test that multiple rapid calls benefit from cache"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Logs"
        mock_run.return_value = mock_result

        # Make 10 rapid calls
        for _ in range(10):
            SystemService.get_backend_logs(100)

        # journalctl should be called only once (first time)
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_backend_and_frontend_have_separate_caches(self, mock_exists, mock_run, clear_cache):
        """Test that backend and frontend logs have independent caches"""
        cache = get_cache_service()

        mock_exists.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Logs"
        mock_run.return_value = mock_result

        # Get backend logs
        backend_logs = SystemService.get_backend_logs(100)
        backend_cached = cache.get("logs_backend")

        # Get frontend logs
        frontend_logs = SystemService.get_frontend_logs(100)
        frontend_cached = cache.get("logs_frontend")

        # Both should be cached independently
        assert backend_cached is not None
        assert frontend_cached is not None


class TestLogsRoutesUsingCache:
    """Integration tests for logs endpoints using cache"""

    @patch("app.api.routes.system.SystemService.get_backend_logs")
    def test_backend_logs_endpoint_uses_cache(self, mock_get_logs, clear_cache):
        """Test that /api/system/logs/backend uses cached service"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        mock_get_logs.return_value = "Cached backend logs"

        response = client.get("/api/system/logs/backend?lines=100")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_get_logs.assert_called_once()

    @patch("app.api.routes.system.SystemService.get_frontend_logs")
    def test_frontend_logs_endpoint_uses_cache(self, mock_get_logs, clear_cache):
        """Test that /api/system/logs/frontend uses cached service"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        mock_get_logs.return_value = "Cached frontend logs"

        response = client.get("/api/system/logs/frontend?lines=100")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_get_logs.assert_called_once()
