"""Regression tests for Huawei latency measurement after run_cmd migration."""

from unittest.mock import patch

from app.providers.modem.hilink.huawei import HuaweiE3372hProvider


class TestHuaweiLatencyRegression:
    @patch("app.providers.modem.hilink.huawei.run_cmd")
    def test_measure_latency_success_parses_metrics(self, mock_run_cmd):
        route_out = "192.168.8.0/24 dev wwan0 proto kernel scope link src 192.168.8.100"
        ping_out = (
            "3 packets transmitted, 3 received, 0% packet loss, time 2002ms\n"
            "rtt min/avg/max/mdev = 23.456/45.678/67.890/12.345 ms"
        )
        mock_run_cmd.side_effect = [
            (route_out, "", 0),
            (ping_out, "", 0),
        ]

        provider = HuaweiE3372hProvider()
        result = provider.measure_latency(host="8.8.8.8", count=3)

        assert result["success"] is True
        assert result["interface"] == "wwan0"
        assert result["avg_ms"] == 45.7
        assert result["jitter_ms"] == 12.3
        assert result["packet_loss"] == 0.0

    @patch("app.providers.modem.hilink.huawei.run_cmd")
    def test_measure_latency_timeout_maps_to_ping_timeout(self, mock_run_cmd):
        route_out = "192.168.8.0/24 dev wwan0 proto kernel scope link src 192.168.8.100"
        mock_run_cmd.side_effect = [
            (route_out, "", 0),
            ("", "Command timed out after 20s", -1),
        ]

        provider = HuaweiE3372hProvider()
        result = provider.measure_latency(host="1.1.1.1", count=3)

        assert result["success"] is False
        assert result["error"] == "Ping timeout"

    @patch("app.providers.modem.hilink.huawei.run_cmd")
    def test_measure_latency_ping_failure_propagates_stderr(self, mock_run_cmd):
        route_out = "192.168.8.0/24 dev wwan0 proto kernel scope link src 192.168.8.100"
        mock_run_cmd.side_effect = [
            (route_out, "", 0),
            ("", "network unreachable", 2),
        ]

        provider = HuaweiE3372hProvider()
        result = provider.measure_latency(host="9.9.9.9", count=3)

        assert result["success"] is False
        assert "network unreachable" in result["error"]
