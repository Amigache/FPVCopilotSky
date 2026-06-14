import pytest
from fastapi import HTTPException

from app.api.routes.network import status as network_status
from app.api.routes.network.common import PriorityModeRequest


@pytest.mark.asyncio
async def test_set_priority_mode_rejects_invalid_mode():
    with pytest.raises(HTTPException) as excinfo:
        await network_status.set_priority_mode(PriorityModeRequest(mode="invalid"))

    assert excinfo.value.status_code == 400
    assert "Mode must be" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_set_priority_mode_sanitizes_internal_errors(monkeypatch):
    async def _raise_error():
        raise RuntimeError("secret failure")

    monkeypatch.setattr(network_status, "detect_wifi_interface", _raise_error)

    with pytest.raises(HTTPException) as excinfo:
        await network_status.set_priority_mode(PriorityModeRequest(mode="wifi"))

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Failed to set network priority"


@pytest.mark.asyncio
async def test_get_network_dashboard_sanitizes_internal_errors(monkeypatch):
    async def _raise_error():
        raise RuntimeError("db timeout")

    monkeypatch.setattr(network_status, "get_network_status", _raise_error)

    with pytest.raises(HTTPException) as excinfo:
        await network_status.get_dashboard()

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Failed to get network dashboard data"
