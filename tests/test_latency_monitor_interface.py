"""Tests for per-interface latency measurement (ping -I via the real interface)."""

import asyncio

from app.services.latency_monitor import LatencyMonitor, LatencyResult


def test_get_interface_latency_pings_via_interface():
    monitor = LatencyMonitor(targets=["1.1.1.1", "8.8.8.8"], history_size=3, timeout=1.0)
    seen = []

    async def fake_ping(target, interface=None):
        seen.append((target, interface))
        latency = 10.0 if target == "1.1.1.1" else 20.0
        return LatencyResult(target=target, latency_ms=latency, timestamp=0.0, success=True, interface=interface)

    monitor._ping_target = fake_ping

    stats = asyncio.run(monitor.get_interface_latency("wlan0"))

    assert stats is not None
    assert stats.interface == "wlan0"
    assert stats.avg_latency == 15.0
    assert stats.packet_loss == 0.0
    assert stats.sample_count == 2
    assert all(iface == "wlan0" for _, iface in seen)


def test_get_interface_latency_without_interface_returns_none():
    monitor = LatencyMonitor(test_mode=True)
    assert asyncio.run(monitor.get_interface_latency("")) is None


def test_get_interface_latency_reports_packet_loss():
    monitor = LatencyMonitor(targets=["1.1.1.1", "8.8.8.8"])

    async def fake_ping(target, interface=None):
        ok = target == "1.1.1.1"
        return LatencyResult(
            target=target,
            latency_ms=5.0 if ok else None,
            timestamp=0.0,
            success=ok,
            interface=interface,
        )

    monitor._ping_target = fake_ping

    stats = asyncio.run(monitor.get_interface_latency("eth1"))

    assert stats is not None
    assert stats.packet_loss == 50.0
    assert stats.sample_count == 2
