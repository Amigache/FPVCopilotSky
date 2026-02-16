"""
VPN API Routes Tests

Tests for /api/vpn/* endpoints including providers, status,
connect, disconnect, logout, peers, and preferences.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestVPNProviders:
    """Tests for GET /api/vpn/providers"""

    def test_get_providers_success(self, client, mock_vpn_registry):
        """Should return list of available VPN providers"""
        response = client.get("/api/vpn/providers")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert data["success"] is True

    def test_get_providers_returns_installed_info(self, client, mock_vpn_registry):
        """Each provider should have name and installed fields"""
        response = client.get("/api/vpn/providers")
        assert response.status_code == 200
        data = response.json()
        for provider in data["providers"]:
            assert "name" in provider
            assert "installed" in provider


class TestVPNStatus:
    """Tests for GET /api/vpn/status"""

    def test_get_status_with_provider(self, client, mock_vpn_get_provider):
        """Should return status for specified provider"""
        provider = mock_vpn_get_provider
        provider.get_status.return_value = {
            "success": True,
            "installed": True,
            "connected": True,
            "authenticated": True,
            "ip_address": "100.64.0.1",
            "hostname": "fpv-test",
            "interface": "tailscale0",
            "peers_count": 3,
        }
        response = client.get("/api/vpn/status?provider=tailscale")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["ip_address"] == "100.64.0.1"

    def test_get_status_disconnected(self, client, mock_vpn_get_provider):
        """Should return disconnected status"""
        provider = mock_vpn_get_provider
        provider.get_status.return_value = {
            "success": True,
            "installed": True,
            "connected": False,
            "authenticated": True,
        }
        response = client.get("/api/vpn/status?provider=tailscale")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_get_status_no_provider_configured(self, client, mock_vpn_no_provider):
        """Should return neutral status when no provider configured"""
        response = client.get("/api/vpn/status")
        # Route catches the 400 and returns neutral status
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["installed"] is False


class TestVPNConnect:
    """Tests for POST /api/vpn/connect"""

    def test_connect_success(self, client, mock_vpn_get_provider):
        """Should connect successfully and return result"""
        provider = mock_vpn_get_provider
        provider.connect.return_value = {
            "success": True,
            "message": "Connected",
            "ip_address": "100.64.0.1",
        }
        response = client.post("/api/vpn/connect", json={"provider": "tailscale"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_connect_needs_auth(self, client, mock_vpn_get_provider):
        """Should return auth_url when authentication is needed"""
        provider = mock_vpn_get_provider
        provider.connect.return_value = {
            "success": False,
            "needs_auth": True,
            "auth_url": "https://login.tailscale.com/test",
        }
        response = client.post("/api/vpn/connect", json={"provider": "tailscale"})
        assert response.status_code == 200
        data = response.json()
        assert data["needs_auth"] is True
        assert "auth_url" in data

    def test_connect_failure_returns_400(self, client, mock_vpn_get_provider):
        """Should return 400 on connection failure"""
        provider = mock_vpn_get_provider
        provider.connect.return_value = {
            "success": False,
            "error": "Connection refused",
        }
        response = client.post("/api/vpn/connect", json={"provider": "tailscale"})
        assert response.status_code == 400

    def test_connect_exception_returns_500(self, client, mock_vpn_get_provider):
        """Should return 500 on unexpected exception"""
        provider = mock_vpn_get_provider
        provider.connect.side_effect = RuntimeError("Unexpected error")
        response = client.post("/api/vpn/connect", json={"provider": "tailscale"})
        assert response.status_code == 500


class TestVPNDisconnect:
    """Tests for POST /api/vpn/disconnect"""

    def test_disconnect_success(self, client, mock_vpn_get_provider):
        """Should disconnect successfully"""
        provider = mock_vpn_get_provider
        provider.disconnect.return_value = {
            "success": True,
            "message": "Disconnected",
        }
        response = client.post("/api/vpn/disconnect", json={"provider": "tailscale"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_disconnect_failure_returns_400(self, client, mock_vpn_get_provider):
        """Should return 400 on disconnect failure"""
        provider = mock_vpn_get_provider
        provider.disconnect.return_value = {
            "success": False,
            "error": "Not connected",
        }
        response = client.post("/api/vpn/disconnect", json={"provider": "tailscale"})
        assert response.status_code == 400


class TestVPNLogout:
    """Tests for POST /api/vpn/logout"""

    def test_logout_success(self, client, mock_vpn_get_provider):
        """Should logout successfully"""
        provider = mock_vpn_get_provider
        provider.logout.return_value = {
            "success": True,
            "message": "Logged out",
        }
        response = client.post("/api/vpn/logout", json={"provider": "tailscale"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_logout_failure_sudo_required(self, client, mock_vpn_get_provider):
        """Should return 400 when sudo is required"""
        provider = mock_vpn_get_provider
        provider.logout.return_value = {
            "success": False,
            "error": "sudo password required",
        }
        response = client.post("/api/vpn/logout", json={"provider": "tailscale"})
        assert response.status_code == 400


class TestVPNPeers:
    """Tests for GET /api/vpn/peers"""

    def test_get_peers_success(self, client, mock_vpn_get_provider):
        """Should return peers list with count"""
        provider = mock_vpn_get_provider
        provider.get_peers.return_value = [
            {"hostname": "peer1", "ip": "100.64.0.2", "online": True},
            {"hostname": "peer2", "ip": "100.64.0.3", "online": False},
        ]
        response = client.get("/api/vpn/peers?provider=tailscale")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["peers"]) == 2
        assert data["count"] == 2

    def test_get_peers_empty(self, client, mock_vpn_get_provider):
        """Should return empty list when no peers"""
        provider = mock_vpn_get_provider
        provider.get_peers.return_value = []
        response = client.get("/api/vpn/peers?provider=tailscale")
        assert response.status_code == 200
        data = response.json()
        assert data["peers"] == []
        assert data["count"] == 0

    def test_get_peers_no_provider_returns_empty(self, client, mock_vpn_no_provider):
        """Should return empty peers when no provider configured"""
        response = client.get("/api/vpn/peers")
        assert response.status_code == 200
        data = response.json()
        assert data["peers"] == []
        assert data["count"] == 0


class TestVPNPreferences:
    """Tests for GET/POST /api/vpn/preferences"""

    def test_get_preferences(self, client, mock_vpn_preferences):
        """Should return VPN preferences"""
        response = client.get("/api/vpn/preferences")
        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data
        assert data["success"] is True

    def test_save_preferences_success(self, client, mock_vpn_preferences):
        """Should save and return VPN preferences"""
        prefs = {
            "provider": "tailscale",
            "enabled": True,
            "auto_connect": True,
            "provider_settings": {},
        }
        response = client.post("/api/vpn/preferences", json=prefs)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["preferences"]["auto_connect"] is True

    def test_save_preferences_with_defaults(self, client, mock_vpn_preferences):
        """Should accept partial preferences with defaults"""
        response = client.post("/api/vpn/preferences", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_save_preferences_persistence(self, client, mock_vpn_preferences):
        """Saved preferences should be retrievable"""
        prefs = {
            "provider": "tailscale",
            "enabled": False,
            "auto_connect": True,
            "provider_settings": {"exit_node": "us-west"},
        }
        save_response = client.post("/api/vpn/preferences", json=prefs)
        assert save_response.status_code == 200

        get_response = client.get("/api/vpn/preferences")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["preferences"]["auto_connect"] is True


class TestVPNProviderResolution:
    """Tests for provider resolution edge cases"""

    def test_unknown_provider_returns_neutral_status(self, client):
        """Should return 200 with neutral status for unavailable provider"""
        with patch("app.api.routes.vpn.get_provider_registry") as mock_registry_fn:
            mock_reg = Mock()
            mock_reg.get_vpn_provider.return_value = None
            mock_registry_fn.return_value = mock_reg
            response = client.get("/api/vpn/status?provider=wireguard")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert data["installed"] is False


# --- Fixtures ---


@pytest.fixture
def mock_vpn_get_provider():
    """
    Mock _get_vpn_provider to return a controllable provider Mock.
    This bypasses registry/preferences lookup entirely.
    """
    provider = Mock()
    provider.is_installed.return_value = True
    provider.get_status.return_value = {
        "success": True,
        "installed": True,
        "connected": False,
        "authenticated": True,
    }
    provider.connect.return_value = {"success": True, "message": "Connected"}
    provider.disconnect.return_value = {"success": True, "message": "Disconnected"}
    provider.logout.return_value = {"success": True, "message": "Logged out"}
    provider.get_peers.return_value = []

    with patch("app.api.routes.vpn._get_vpn_provider", return_value=provider):
        yield provider


@pytest.fixture
def mock_vpn_registry():
    """Mock the provider registry for /providers endpoint"""
    mock_reg = Mock()
    mock_reg.get_available_vpn_providers.return_value = [
        {"name": "tailscale", "installed": True, "description": "Tailscale VPN"},
        {"name": "zerotier", "installed": False, "description": "ZeroTier VPN"},
    ]
    with patch("app.api.routes.vpn.get_provider_registry", return_value=mock_reg):
        yield mock_reg


@pytest.fixture
def mock_vpn_no_provider():
    """
    Mock scenario where _get_vpn_provider raises HTTPException 400
    to simulate no provider configured.
    """
    from fastapi import HTTPException
    from app.i18n import translate

    def raise_no_provider(*args, **kwargs):
        raise HTTPException(
            status_code=400,
            detail=translate("vpn.no_provider_configured", "en"),
        )

    with patch("app.api.routes.vpn._get_vpn_provider", side_effect=raise_no_provider):
        yield


@pytest.fixture
def mock_vpn_preferences():
    """Mock preferences service for VPN preferences endpoint tests"""
    saved_config = {
        "provider": "tailscale",
        "enabled": False,
        "auto_connect": False,
        "provider_settings": {},
    }

    mock_prefs = Mock()

    def get_vpn_config():
        return saved_config.copy()

    def set_vpn_config(config):
        saved_config.update(config)

    mock_prefs.get_vpn_config = Mock(side_effect=get_vpn_config)
    mock_prefs.set_vpn_config = Mock(side_effect=set_vpn_config)

    with patch("app.api.routes.vpn._get_preferences_service", return_value=mock_prefs):
        yield mock_prefs


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked API services"""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)
