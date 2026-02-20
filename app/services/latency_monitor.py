"""
Latency Monitoring Service

Continuous monitoring of network latency to multiple targets
for intelligent network switching decisions.
"""

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detect at module-load time whether the ping binary has cap_net_raw / setuid.
# On some boards (e.g. Radxa) ping ships without either, so we must prefix
# the command with "sudo" as a fallback (sudoers entry: NOPASSWD: /usr/bin/ping).
# The result is cached in _PING_PREFIX so the check runs only once.
# ---------------------------------------------------------------------------
_PING_PREFIX: List[str] = []  # [] → plain "ping"; ["sudo"] → "sudo ping"


def _detect_ping_prefix() -> List[str]:
    """Return [] if ping can create raw sockets, ['sudo'] otherwise."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", "127.0.0.1"],
            capture_output=True,
            timeout=3,
        )
        if result.returncode == 0:
            return []
        # returncode=2 on permission error ("Operation not permitted")
        stderr = result.stderr.decode(errors="replace")
        if "permitted" in stderr or "capability" in stderr or "setuid" in stderr:
            logger.warning(
                "ping lacks cap_net_raw — using 'sudo ping' fallback. "
                "Fix permanently with: sudo setcap cap_net_raw+ep /usr/bin/ping"
            )
            return ["sudo"]
        return []
    except Exception:
        return []


_PING_PREFIX = _detect_ping_prefix()


@dataclass
class LatencyResult:
    """Single latency measurement result"""

    target: str
    latency_ms: Optional[float]
    timestamp: float
    success: bool
    interface: Optional[str] = None


@dataclass
class LatencyStats:
    """Latency statistics for a target"""

    target: str
    interface: Optional[str]
    avg_latency: float
    min_latency: float
    max_latency: float
    packet_loss: float
    sample_count: int
    last_update: float
    # Jitter metrics (Mejora Nº4: jitter-based quality)
    jitter_ms: float = 0.0  # Standard deviation of RTT
    variance_ms: float = 0.0  # Variance of RTT
    p95_latency: float = 0.0  # 95th percentile latency


class LatencyMonitor:
    """
    Monitor network latency to multiple targets continuously.

    Features:
    - Parallel ping tests to multiple targets
    - Per-interface latency tracking
    - Historical data with configurable window
    - Packet loss calculation
    - Real-time statistics
    """

    def __init__(
        self,
        targets: List[str] = None,
        interval: float = 2.0,
        history_size: int = 30,
        timeout: float = 2.0,
        test_mode: bool = False,
    ):
        """
        Initialize latency monitor.

        Args:
            targets: List of IP addresses to ping (default: Google DNS, Cloudflare DNS)
            interval: Seconds between ping tests
            history_size: Number of historical samples to keep
            timeout: Ping timeout in seconds
            test_mode: If True, use fake ping results for testing
        """
        self.targets = targets or ["8.8.8.8", "1.1.1.1", "9.9.9.9"]
        self.interval = interval
        self.history_size = history_size
        self.timeout = timeout
        self.test_mode = test_mode

        # Historical data: {target: deque([LatencyResult, ...])}
        self.history: Dict[str, deque] = {target: deque(maxlen=history_size) for target in self.targets}

        # Monitoring state
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        logger.info(f"LatencyMonitor initialized with targets: {self.targets}")

    async def start(self):
        """Start continuous latency monitoring"""
        if self._monitoring:
            logger.warning("LatencyMonitor already running")
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("LatencyMonitor started")

    async def stop(self):
        """Stop continuous latency monitoring"""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("LatencyMonitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self._monitoring:
            try:
                # Ping all targets in parallel
                results = await self._ping_all_targets()

                # Store results
                async with self._lock:
                    for result in results:
                        self.history[result.target].append(result)

                # Wait for next interval
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.interval)

    async def _ping_all_targets(self) -> List[LatencyResult]:
        """Ping all targets in parallel"""
        tasks = [self._ping_target(target) for target in self.targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        return [r for r in results if isinstance(r, LatencyResult)]

    async def _ping_target(self, target: str, interface: Optional[str] = None) -> LatencyResult:
        """
        Ping a single target.

        Args:
            target: IP address to ping
            interface: Optional network interface to use

        Returns:
            LatencyResult with measurement
        """
        # In test mode, return fake results immediately
        if self.test_mode:
            import random

            return LatencyResult(
                target=target,
                latency_ms=random.uniform(5.0, 25.0),  # Fake latency 5-25ms
                timestamp=time.time(),
                success=True,
                interface=interface,
            )

        cmd = _PING_PREFIX + ["ping", "-c", "1", "-W", str(int(self.timeout))]

        # Bind to specific interface if provided
        if interface:
            cmd.extend(["-I", interface])

        cmd.append(target)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self.timeout + 0.5)

            # Parse ping output for latency
            latency_ms = None
            if process.returncode == 0:
                output = stdout.decode()
                # Look for "time=X.XX ms" pattern
                import re

                match = re.search(r"time[=:](\d+\.?\d*)\s*ms", output)
                if match:
                    latency_ms = float(match.group(1))

            return LatencyResult(
                target=target,
                latency_ms=latency_ms,
                timestamp=time.time(),
                success=latency_ms is not None,
                interface=interface,
            )

        except asyncio.TimeoutError:
            return LatencyResult(
                target=target, latency_ms=None, timestamp=time.time(), success=False, interface=interface
            )
        except Exception as e:
            logger.debug(f"Ping to {target} failed: {e}")
            return LatencyResult(
                target=target, latency_ms=None, timestamp=time.time(), success=False, interface=interface
            )

    async def get_current_latency(self, target: Optional[str] = None) -> Dict[str, LatencyStats]:
        """
        Get current latency statistics.

        Args:
            target: Specific target to query (None for all targets)

        Returns:
            Dictionary of {target: LatencyStats}
        """
        async with self._lock:
            stats = {}

            targets_to_check = [target] if target else self.targets

            for t in targets_to_check:
                if t not in self.history or not self.history[t]:
                    continue

                history = list(self.history[t])
                successful = [r for r in history if r.success]

                if not successful:
                    # No successful pings
                    stats[t] = LatencyStats(
                        target=t,
                        interface=None,
                        avg_latency=0,
                        min_latency=0,
                        max_latency=0,
                        packet_loss=100.0,
                        sample_count=len(history),
                        last_update=history[-1].timestamp if history else 0,
                    )
                else:
                    latencies = [r.latency_ms for r in successful]

                    # Jitter calculation (Mejora Nº4)
                    avg_lat = sum(latencies) / len(latencies)
                    variance = sum((x - avg_lat) ** 2 for x in latencies) / len(latencies)
                    jitter = variance**0.5

                    # P95 latency
                    sorted_lats = sorted(latencies)
                    p95_idx = int(len(sorted_lats) * 0.95)
                    p95 = sorted_lats[min(p95_idx, len(sorted_lats) - 1)]

                    stats[t] = LatencyStats(
                        target=t,
                        interface=successful[-1].interface,
                        avg_latency=avg_lat,
                        min_latency=min(latencies),
                        max_latency=max(latencies),
                        packet_loss=(1 - len(successful) / len(history)) * 100,
                        sample_count=len(history),
                        last_update=successful[-1].timestamp,
                        jitter_ms=round(jitter, 2),
                        variance_ms=round(variance, 2),
                        p95_latency=round(p95, 2),
                    )

            return stats

    async def get_interface_latency(self, interface: str) -> Optional[LatencyStats]:
        """
        Get average latency across all targets for a specific interface.

        Args:
            interface: Network interface name

        Returns:
            Aggregated LatencyStats for the interface
        """
        stats = await self.get_current_latency()

        if not stats:
            return None

        # Calculate weighted average across all targets
        all_latencies = []
        all_samples = 0
        all_losses = []

        for target_stats in stats.values():
            # Always include entries that have samples (even if avg_latency==0 due to all pings failing)
            # This captures packet_loss=100% when there is no internet but the monitor IS running
            if target_stats.sample_count > 0:
                all_samples += target_stats.sample_count
                all_losses.append(target_stats.packet_loss)
                if target_stats.avg_latency > 0:
                    all_latencies.append(target_stats.avg_latency)

        if not all_losses:
            # No samples at all – monitor has not collected data yet
            return None

        avg_rtt = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
        return LatencyStats(
            target=f"aggregate ({len(stats)} targets)",
            interface=interface,
            avg_latency=avg_rtt,
            min_latency=min(all_latencies) if all_latencies else 0.0,
            max_latency=max(all_latencies) if all_latencies else 0.0,
            packet_loss=sum(all_losses) / len(all_losses) if all_losses else 0.0,
            sample_count=all_samples,
            last_update=time.time(),
        )

    async def test_interface_latency(self, interface: str, count: int = 3) -> LatencyStats:
        """
        Test latency for a specific interface (one-time test).

        Args:
            interface: Network interface to test
            count: Number of pings per target

        Returns:
            Aggregated LatencyStats
        """
        all_results = []

        for target in self.targets:
            for _ in range(count):
                result = await self._ping_target(target, interface)
                all_results.append(result)
                await asyncio.sleep(0.1)  # Small delay between pings

        successful = [r for r in all_results if r.success]

        if not successful:
            return LatencyStats(
                target=f"test ({len(self.targets)} targets)",
                interface=interface,
                avg_latency=0,
                min_latency=0,
                max_latency=0,
                packet_loss=100.0,
                sample_count=len(all_results),
                last_update=time.time(),
            )

        latencies = [r.latency_ms for r in successful]

        return LatencyStats(
            target=f"test ({len(self.targets)} targets)",
            interface=interface,
            avg_latency=sum(latencies) / len(latencies),
            min_latency=min(latencies),
            max_latency=max(latencies),
            packet_loss=(1 - len(successful) / len(all_results)) * 100,
            sample_count=len(all_results),
            last_update=time.time(),
        )

    def get_history(self, target: Optional[str] = None, last_n: int = None) -> Dict[str, List[LatencyResult]]:
        """
        Get historical latency data.

        Args:
            target: Specific target (None for all)
            last_n: Number of recent samples to return (None for all)

        Returns:
            Dictionary of {target: [LatencyResult, ...]}
        """
        targets_to_export = [target] if target else self.targets

        history_export = {}
        for t in targets_to_export:
            if t not in self.history:
                continue

            data = list(self.history[t])
            if last_n:
                data = data[-last_n:]

            history_export[t] = data

        return history_export

    def clear_history(self, target: Optional[str] = None):
        """Clear historical data"""
        if target:
            if target in self.history:
                self.history[target].clear()
        else:
            for t in self.targets:
                self.history[t].clear()

        logger.info(f"History cleared for: {target or 'all targets'}")


# Global latency monitor instance
_latency_monitor: Optional[LatencyMonitor] = None


def get_latency_monitor() -> LatencyMonitor:
    """Get global latency monitor instance"""
    global _latency_monitor
    if _latency_monitor is None:
        _latency_monitor = LatencyMonitor()
    return _latency_monitor


async def start_latency_monitoring():
    """Start global latency monitoring"""
    monitor = get_latency_monitor()
    await monitor.start()


async def stop_latency_monitoring():
    """Stop global latency monitoring"""
    monitor = get_latency_monitor()
    await monitor.stop()
