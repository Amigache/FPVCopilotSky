"""Tests for opt-in API authentication (FPV_API_TOKEN)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

PROTECTED = "/api/system/version/current"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_token_by_default(monkeypatch):
    monkeypatch.delenv("FPV_API_TOKEN", raising=False)
    yield


class TestAuthDisabled:
    def test_allows_requests(self, client):
        assert client.get(PROTECTED).status_code == 200

    def test_status_reports_not_required(self, client):
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        assert response.json() == {"auth_required": False, "authenticated": True}


class TestAuthEnabled:
    def test_blocks_without_token(self, client, monkeypatch):
        monkeypatch.setenv("FPV_API_TOKEN", "s3cret")
        response = client.get(PROTECTED)
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_rejects_wrong_token(self, client, monkeypatch):
        monkeypatch.setenv("FPV_API_TOKEN", "s3cret")
        response = client.get(PROTECTED, headers={"Authorization": "Bearer nope"})
        assert response.status_code == 401

    def test_allows_valid_token(self, client, monkeypatch):
        monkeypatch.setenv("FPV_API_TOKEN", "s3cret")
        response = client.get(PROTECTED, headers={"Authorization": "Bearer s3cret"})
        assert response.status_code == 200

    def test_status_is_public_and_reports_state(self, client, monkeypatch):
        monkeypatch.setenv("FPV_API_TOKEN", "s3cret")
        unauthenticated = client.get("/api/auth/status")
        assert unauthenticated.status_code == 200
        assert unauthenticated.json() == {"auth_required": True, "authenticated": False}

        authenticated = client.get("/api/auth/status", headers={"Authorization": "Bearer s3cret"})
        assert authenticated.json() == {"auth_required": True, "authenticated": True}

    def test_websocket_rejected_without_token(self, client, monkeypatch):
        monkeypatch.setenv("FPV_API_TOKEN", "s3cret")
        with pytest.raises(Exception):
            with client.websocket_connect("/ws"):
                pytest.fail("WebSocket connection should have been rejected")
