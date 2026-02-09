#!/usr/bin/env python3
"""
Network Advanced Services Tests

Tests for new network services: LatencyMonitor, AutoFailover, NetworkOptimizer, DNSCache
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestLatencyMonitor:
    """Test LatencyMonitor service"""

    @pytest.mark.asyncio
    async def test_latency_monitor_initialization(self):
        """Test LatencyMonitor can be initialized"""
        from app.services.latency_monitor import LatencyMonitor

        monitor = LatencyMonitor(targets=["8.8.8.8", "1.1.1.1"], interval=2.0, history_size=30)

        assert monitor.targets == ["8.8.8.8", "1.1.1.1"]
        assert monitor.interval == 2.0
        assert monitor.history_size == 30
        assert not monitor._monitoring

    @pytest.mark.asyncio
    async def test_latency_monitor_start_stop(self):
        """Test starting and stopping latency monitoring"""
        from app.services.latency_monitor import LatencyMonitor

        monitor = LatencyMonitor(targets=["8.8.8.8"])

        # Start monitoring
        await monitor.start()
        assert monitor._monitoring is True

        # Stop monitoring
        await monitor.stop()
        assert monitor._monitoring is False

    @pytest.mark.asyncio
    @patch("app.services.latency_monitor.asyncio.create_subprocess_exec")
    async def test_ping_target(self, mock_subprocess):
        """Test ping to a single target"""
        from app.services.latency_monitor import LatencyMonitor

        # Mock successful ping
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"time=15.3 ms\n", b""))
        mock_subprocess.return_value = mock_process

        monitor = LatencyMonitor()
        result = await monitor._ping_target("8.8.8.8")

        assert result.success is True
        assert result.latency_ms is not None
        assert result.target == "8.8.8.8"

    @pytest.mark.asyncio
    async def test_get_current_latency_empty(self):
        """Test getting latency stats when no data"""
        from app.services.latency_monitor import LatencyMonitor

        monitor = LatencyMonitor()
        stats = await monitor.get_current_latency()

        # Should return empty dict when no monitoring done
        assert isinstance(stats, dict)


class TestAutoFailover:
    """Test AutoFailover service"""

    @pytest.mark.asyncio
    async def test_failover_initialization(self):
        """Test AutoFailover can be initialized"""
        from app.services.auto_failover import AutoFailover, FailoverConfig

        config = FailoverConfig(latency_threshold_ms=200.0, latency_check_window=15, switch_cooldown_s=30.0)

        failover = AutoFailover(config=config)

        assert failover.config.latency_threshold_ms == 200.0
        assert failover.config.latency_check_window == 15
        assert not failover._monitoring

    @pytest.mark.asyncio
    async def test_failover_start_stop(self):
        """Test starting and stopping auto-failover"""
        from app.services.auto_failover import AutoFailover, NetworkMode

        failover = AutoFailover()

        # Start with initial mode
        await failover.start(initial_mode=NetworkMode.MODEM)
        assert failover._monitoring is True
        assert failover.state.current_mode == NetworkMode.MODEM

        # Stop
        await failover.stop()
        assert failover._monitoring is False

    @pytest.mark.asyncio
    async def test_failover_config_update(self):
        """Test updating failover configuration"""
        from app.services.auto_failover import AutoFailover

        failover = AutoFailover()

        # Update config
        await failover.update_config(latency_threshold_ms=250.0, switch_cooldown_s=45.0)

        assert failover.config.latency_threshold_ms == 250.0
        assert failover.config.switch_cooldown_s == 45.0

    @pytest.mark.asyncio
    async def test_failover_force_switch(self):
        """Test forcing a manual network switch"""
        from app.services.auto_failover import AutoFailover, NetworkMode

        switch_called = False

        async def mock_switch_callback(target_mode):
            nonlocal switch_called
            switch_called = True
            return True

        failover = AutoFailover(switch_callback=mock_switch_callback)

        # Force switch
        result = await failover.force_switch(NetworkMode.WIFI, reason="Test")

        assert result is True
        assert switch_called is True


class TestNetworkOptimizer:
    """Test NetworkOptimizer service"""

    def test_optimizer_initialization(self):
        """Test NetworkOptimizer can be initialized"""
        from app.services.network_optimizer import NetworkOptimizer

        optimizer = NetworkOptimizer()

        assert optimizer is not None
        assert hasattr(optimizer, "enable_flight_mode")
        assert hasattr(optimizer, "disable_flight_mode")

    @patch("app.services.network_optimizer.NetworkOptimizer._run_command")
    def test_enable_flight_mode(self, mock_run_command):
        """Test enabling Flight Mode"""
        from app.services.network_optimizer import NetworkOptimizer

        # Mock _run_command to return success
        # Format: (stdout, stderr, returncode)
        mock_run_command.return_value = ("192.168.8.1", "", 0)

        optimizer = NetworkOptimizer()
        result = optimizer.enable_flight_mode()

        # Should return result dict
        assert isinstance(result, dict)
        assert "success" in result
        assert "active" in result

    @patch("app.services.network_optimizer.NetworkOptimizer._run_command")
    def test_disable_flight_mode(self, mock_run_command):
        """Test disabling Flight Mode"""
        from app.services.network_optimizer import NetworkOptimizer

        # Mock _run_command to return success
        # Format: (stdout, stderr, returncode)
        mock_run_command.return_value = ("192.168.8.1", "", 0)

        optimizer = NetworkOptimizer()

        # Enable first
        optimizer.flight_mode_active = True
        optimizer.original_settings = {"mtu": 1500}

        # Then disable
        result = optimizer.disable_flight_mode()

        assert isinstance(result, dict)
        assert "success" in result
        if result.get("success"):
            assert optimizer.flight_mode_active is False

    def test_get_status(self):
        """Test getting optimizer status"""
        from app.services.network_optimizer import NetworkOptimizer

        optimizer = NetworkOptimizer()
        status = optimizer.get_status()

        assert isinstance(status, dict)
        assert "active" in status
        assert "config" in status

    @patch("app.services.network_optimizer.subprocess.run")
    def test_get_network_metrics(self, mock_subprocess):
        """Test getting network metrics"""
        from app.services.network_optimizer import NetworkOptimizer

        # Mock sysctl output
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="bbr\n26214400\n26214400\n", stderr="")

        optimizer = NetworkOptimizer()
        metrics = optimizer.get_network_metrics()

        assert isinstance(metrics, dict)
        assert "success" in metrics


class TestDNSCache:
    """Test DNSCache service"""

    @pytest.mark.asyncio
    async def test_dns_cache_initialization(self):
        """Test DNSCache can be initialized"""
        from app.services.dns_cache import DNSCache, DNSCacheConfig

        config = DNSCacheConfig(cache_size=1000, upstream_dns=["8.8.8.8", "1.1.1.1"])

        dns_cache = DNSCache(config=config)

        assert dns_cache.config.cache_size == 1000
        assert "8.8.8.8" in dns_cache.config.upstream_dns

    @pytest.mark.asyncio
    @patch("app.services.dns_cache.asyncio.create_subprocess_exec")
    async def test_is_installed_check(self, mock_subprocess):
        """Test checking if dnsmasq is installed"""
        from app.services.dns_cache import DNSCache

        # Mock 'which dnsmasq' success
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"/usr/sbin/dnsmasq\n", b""))
        mock_subprocess.return_value = mock_process

        dns_cache = DNSCache()
        is_installed = await dns_cache.is_installed()

        assert is_installed is True

    def test_generate_config(self):
        """Test dnsmasq config generation"""
        from app.services.dns_cache import DNSCache, DNSCacheConfig

        config = DNSCacheConfig(cache_size=500, upstream_dns=["8.8.8.8"], min_ttl=300, max_ttl=3600)

        dns_cache = DNSCache(config=config)
        config_content = dns_cache._generate_config()

        assert "cache-size=500" in config_content
        assert "server=8.8.8.8" in config_content
        assert "min-cache-ttl=300" in config_content
        assert "max-cache-ttl=3600" in config_content


class TestNetworkAPIEndpoints:
    """Test network API endpoints for new services"""

    def test_latency_endpoints_exist(self):
        """Test that latency monitor endpoints are defined"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # These should all be valid routes (may return errors without services running)
        routes = [
            "/api/network/latency/start",
            "/api/network/latency/stop",
            "/api/network/latency/current",
            "/api/network/latency/history",
        ]

        for route in routes:
            # Check route exists (not 404)
            response = client.post(route) if "start" in route or "stop" in route else client.get(route)
            assert response.status_code != 404, f"Route {route} should exist"

    def test_failover_endpoints_exist(self):
        """Test that auto-failover endpoints are defined"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        routes = [
            "/api/network/failover/start",
            "/api/network/failover/stop",
            "/api/network/failover/status",
            "/api/network/failover/config",
        ]

        for route in routes:
            if "status" in route:
                response = client.get(route)
            else:
                response = client.post(route)
            assert response.status_code != 404, f"Route {route} should exist"

    def test_flight_mode_endpoints_exist(self):
        """Test that Flight Mode endpoints are defined"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        routes = [
            "/api/network/flight-mode/status",
            "/api/network/flight-mode/enable",
            "/api/network/flight-mode/disable",
            "/api/network/flight-mode/metrics",
        ]

        for route in routes:
            if "status" in route or "metrics" in route:
                response = client.get(route)
            else:
                response = client.post(route)
            assert response.status_code != 404, f"Route {route} should exist"

    def test_dns_cache_endpoints_exist(self):
        """Test that DNS cache endpoints are defined"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        routes = [
            "/api/network/dns/status",
            "/api/network/dns/install",
            "/api/network/dns/start",
            "/api/network/dns/stop",
            "/api/network/dns/clear",
        ]

        for route in routes:
            if "status" in route:
                response = client.get(route)
            else:
                response = client.post(route)
            assert response.status_code != 404, f"Route {route} should exist"

    def test_dashboard_endpoint_exists(self):
        """Test that unified dashboard endpoint exists"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        response = client.get("/api/network/dashboard")
        assert response.status_code != 404, "Dashboard endpoint should exist"

        # If successful, should have required fields
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "network" in data or "cached" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
