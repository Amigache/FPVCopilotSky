"""Regression tests for SystemService command-layer migration."""

from unittest.mock import patch

from app.services.cache_service import get_cache_service
from app.services.system_service import SystemService


def _clear_logs_cache():
    cache = get_cache_service()
    cache.clear_all()


class TestSystemServiceCmdRegression:
    def setup_method(self):
        _clear_logs_cache()

    def teardown_method(self):
        _clear_logs_cache()

    @patch("app.services.system_service.run_cmd")
    def test_get_backend_logs_success(self, mock_run_cmd):
        mock_run_cmd.return_value = ("line1\nline2", "", 0)

        logs = SystemService.get_backend_logs(20)

        assert "line1" in logs
        mock_run_cmd.assert_called_once()

    @patch("app.services.system_service.run_cmd")
    def test_get_backend_logs_error_text_passthrough(self, mock_run_cmd):
        mock_run_cmd.return_value = ("", "permission denied", 1)

        logs = SystemService.get_backend_logs(20)

        assert "Error fetching logs" in logs
        assert "permission denied" in logs

    @patch("app.services.system_service.os.path.exists", return_value=True)
    @patch("app.services.system_service.run_cmd")
    def test_get_frontend_logs_combines_error_and_access(self, mock_run_cmd, _mock_exists):
        # First call: nginx error log; second call: nginx access log
        mock_run_cmd.side_effect = [
            ("err-line", "", 0),
            ("acc-line", "", 0),
        ]

        logs = SystemService.get_frontend_logs(20)

        assert "Error Log" in logs
        assert "Access Log" in logs
        assert "err-line" in logs
        assert "acc-line" in logs

    @patch("app.services.system_service.run_cmd")
    def test_get_services_status_timeout_maps_to_not_active(self, mock_run_cmd):
        # Simulate timeout path from run_cmd contract (returncode=-1)
        mock_run_cmd.return_value = ("", "Command timed out after 5s", -1)

        services = SystemService.get_services_status()

        assert len(services) > 0
        for svc in services:
            assert svc["active"] is False
            # status can be empty string if command produced no stdout
            assert "status" in svc
