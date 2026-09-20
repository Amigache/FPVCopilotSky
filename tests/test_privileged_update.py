"""Tests for the privileged updater integration (C5 stage 1)."""

from unittest.mock import patch

from app.services.system_service import SystemService


class TestPrivilegedUpdateRequest:
    def test_write_update_request(self, tmp_path, monkeypatch):
        monkeypatch.setattr(SystemService, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(SystemService, "UPDATE_REQUEST_FILE", str(tmp_path / "update-request.env"))

        assert SystemService._write_update_request("update", "1.2.3") is True

        content = (tmp_path / "update-request.env").read_text()
        assert "FPV_UPDATE_ACTION=update" in content
        assert "FPV_UPDATE_TARGET=1.2.3" in content

    def test_returns_none_when_unit_not_installed(self):
        with patch.object(SystemService, "_privileged_updater_available", return_value=False):
            assert SystemService._start_privileged_update("update", "1.2.3") is None

    def test_returns_none_when_request_write_fails(self):
        with (
            patch.object(SystemService, "_privileged_updater_available", return_value=True),
            patch.object(SystemService, "_write_update_request", return_value=False),
        ):
            assert SystemService._start_privileged_update("update", "1.2.3") is None

    def test_starts_unit_when_available(self):
        with (
            patch.object(SystemService, "_privileged_updater_available", return_value=True),
            patch.object(SystemService, "_write_update_request", return_value=True),
            patch("app.services.system_service.run_cmd", return_value=("", "", 0)) as mock_run,
        ):
            result = SystemService._start_privileged_update("rollback", "1.2.3")

        assert result is not None
        assert result["success"] is True
        assert result["privileged"] is True
        assert result["updated_to"] == "1.2.3"

        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["sudo", "-n", "systemctl"]
        assert "--no-block" in cmd
        assert "fpvcopilot-update" in cmd

    def test_falls_back_when_systemctl_fails(self):
        with (
            patch.object(SystemService, "_privileged_updater_available", return_value=True),
            patch.object(SystemService, "_write_update_request", return_value=True),
            patch("app.services.system_service.run_cmd", return_value=("", "boom", 1)),
        ):
            assert SystemService._start_privileged_update("update", "1.2.3") is None
