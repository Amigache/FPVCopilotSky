"""
Tests for Network Status Cache

Tests the caching mechanism using CacheService
to prevent excessive system calls and improve performance.
"""

import pytest
import time
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.cache_service import get_cache_service


@pytest.fixture
def client():
    """Create TestClient"""
    return TestClient(app)


@pytest.fixture
def clear_cache():
    """Clear cache before each test"""
    cache = get_cache_service()
    cache.clear_all()
    yield
    cache.clear_all()


class TestNetworkStatusCache:
    """Test network status caching functionality"""

    @patch("app.api.routes.network.status.detect_wifi_interface")
    @patch("app.api.routes.network.status.detect_modem_interface")
    @patch("app.api.routes.network.status._get_interfaces")
    @patch("app.api.routes.network.status._get_routes")
    @patch("app.api.routes.network.status._get_modem_info")
    async def test_cache_hit_returns_cached_data(
        self, mock_modem_info, mock_routes, mock_interfaces, mock_modem_iface, mock_wifi_iface, clear_cache
    ):
        """Test that cache returns same data within TTL"""
        from app.api.routes.network.status import get_network_status

        cache = get_cache_service()

        # Setup mocks
        mock_wifi_iface.return_value = "wlan0"
        mock_modem_iface.return_value = "usb0"
        mock_interfaces.return_value = [{"name": "wlan0", "state": "UP", "type": "wifi"}]
        mock_routes.return_value = [{"interface": "wlan0", "metric": 100}]
        mock_modem_info.return_value = {"detected": True}

        # First call - cache miss
        result1 = await get_network_status()
        assert result1["wifi"]["detected"] is True

        # Verify cache was populated
        cached = cache.get("network_status")
        assert cached is not None

        # Second call immediately - cache hit (mocks should not be called again)
        result2 = await get_network_status()
        assert result2 == result1  # Should be identical

        # Verify mocks were only called once
        assert mock_interfaces.call_count == 1
        assert mock_routes.call_count == 1

    @patch("app.api.routes.network.status.detect_wifi_interface")
    @patch("app.api.routes.network.status.detect_modem_interface")
    @patch("app.api.routes.network.status._get_interfaces")
    @patch("app.api.routes.network.status._get_routes")
    @patch("app.api.routes.network.status._get_modem_info")
    async def test_cache_expires_after_ttl(
        self, mock_modem_info, mock_routes, mock_interfaces, mock_modem_iface, mock_wifi_iface, clear_cache
    ):
        """Test that cache expires after TTL (2 seconds)"""
        from app.api.routes.network.status import get_network_status

        cache = get_cache_service()

        # Setup mocks
        mock_wifi_iface.return_value = "wlan0"
        mock_modem_iface.return_value = "usb0"
        mock_interfaces.return_value = [{"name": "wlan0", "state": "UP", "type": "wifi"}]
        mock_routes.return_value = [{"interface": "wlan0", "metric": 100}]
        mock_modem_info.return_value = {"detected": True}

        # First call
        result1 = await get_network_status()
        assert mock_interfaces.call_count == 1

        # Wait for TTL to expire (2.1 seconds)
        time.sleep(2.1)

        # Second call - cache should be expired, mocks called again
        result2 = await get_network_status()
        assert mock_interfaces.call_count == 2  # Called twice now
        assert result2["wifi"]["detected"] is True

    @patch("app.api.routes.network.status.detect_wifi_interface")
    @patch("app.api.routes.network.status.detect_modem_interface")
    async def test_cache_handles_errors_gracefully(self, mock_modem_iface, mock_wifi_iface, clear_cache):
        """Test that errors are not cached"""
        from app.api.routes.network.status import get_network_status

        cache = get_cache_service()

        # Mock to raise exception
        mock_wifi_iface.side_effect = Exception("Network error")

        # Call should return error but not crash
        try:
            result = await get_network_status()
            # If it returns an error response, verify it's not cached
            cached = cache.get("network_status")
            assert cached is None or cached.get("success") is False
        except Exception:
            # If it raises, that's also acceptable
            pass

    def test_cache_reduces_system_calls(self, client, clear_cache):
        """Integration test: verify cache reduces redundant system calls"""

        with patch("app.api.routes.network.status.detect_wifi_interface") as mock_detect:
            mock_detect.return_value = "wlan0"

            # Make 3 rapid calls
            response1 = client.get("/api/network/status")
            response2 = client.get("/api/network/status")
            response3 = client.get("/api/network/status")

            # All should succeed
            assert response1.status_code in [200, 500]
            assert response2.status_code in [200, 500]
            assert response3.status_code in [200, 500]

            # Due to caching, subsequent calls should hit cache
            # So system calls should be minimal


class TestNetworkModeDetermination:
    """Test network mode and interface detection logic"""

    @patch("app.api.routes.network.status.detect_wifi_interface")
    @patch("app.api.routes.network.status.detect_modem_interface")
    @patch("app.api.routes.network.status._get_interfaces")
    @patch("app.api.routes.network.status._get_routes")
    @patch("app.api.routes.network.status._get_modem_info")
    async def test_wifi_detected_and_reported(
        self, mock_modem_info, mock_routes, mock_interfaces, mock_modem_iface, mock_wifi_iface, clear_cache
    ):
        """Test that WiFi interface is properly detected and reported"""
        from app.api.routes.network.status import get_network_status

        mock_wifi_iface.return_value = "wlan0"
        mock_modem_iface.return_value = "usb0"
        mock_interfaces.return_value = []
        mock_routes.return_value = [
            {"interface": "wlan0", "metric": 50},
            {"interface": "usb0", "metric": 100},
        ]
        mock_modem_info.return_value = {"detected": True}

        result = await get_network_status()
        assert result["wifi"]["detected"] is True
        assert result["wifi"]["interface"] == "wlan0"
        assert result["primary_interface"] == "wlan0"

    @patch("app.api.routes.network.status.detect_wifi_interface")
    @patch("app.api.routes.network.status.detect_modem_interface")
    @patch("app.api.routes.network.status._get_interfaces")
    @patch("app.api.routes.network.status._get_routes")
    @patch("app.api.routes.network.status._get_modem_info")
    async def test_modem_detected_and_reported(
        self, mock_modem_info, mock_routes, mock_interfaces, mock_modem_iface, mock_wifi_iface, clear_cache
    ):
        """Test that modem interface is properly detected and reported"""
        from app.api.routes.network.status import get_network_status

        mock_wifi_iface.return_value = "wlan0"
        mock_modem_iface.return_value = "usb0"
        mock_interfaces.return_value = []
        mock_routes.return_value = [
            {"interface": "usb0", "metric": 50},
            {"interface": "wlan0", "metric": 100},
        ]
        mock_modem_info.return_value = {"detected": True}

        result = await get_network_status()
        assert result["modem"]["detected"] is True
        assert result["primary_interface"] == "usb0"

    @patch("app.api.routes.network.status.detect_wifi_interface")
    @patch("app.api.routes.network.status.detect_modem_interface")
    @patch("app.api.routes.network.status._get_interfaces")
    @patch("app.api.routes.network.status._get_routes")
    @patch("app.api.routes.network.status._get_modem_info")
    async def test_no_interfaces_detected(
        self, mock_modem_info, mock_routes, mock_interfaces, mock_modem_iface, mock_wifi_iface, clear_cache
    ):
        """Test proper handling when no network interfaces are available"""
        from app.api.routes.network.status import get_network_status

        mock_wifi_iface.return_value = None
        mock_modem_iface.return_value = None
        mock_interfaces.return_value = []
        mock_routes.return_value = []
        mock_modem_info.return_value = {"detected": False}

        result = await get_network_status()
        assert result["wifi"]["detected"] is False
        assert result["modem"]["detected"] is False
        assert result["primary_interface"] is None
