"""
Auto-Failover Service

Automatic network interface switching based on latency and availability.
Ensures continuous streaming by switching between WiFi and 4G intelligently.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable

from app.services.latency_monitor import get_latency_monitor

logger = logging.getLogger(__name__)


class NetworkMode(Enum):
    """Network operating mode"""

    WIFI = "wifi"
    MODEM = "modem"
    UNKNOWN = "unknown"


@dataclass
class FailoverConfig:
    """Auto-failover configuration"""

    # Latency thresholds
    latency_threshold_ms: float = 200.0  # Switch if latency > this
    latency_check_window: int = 15  # Consecutive bad samples before switching

    # Hysteresis to prevent flapping
    switch_cooldown_s: float = 30.0  # Minimum time between switches
    restore_delay_s: float = 60.0  # Wait before switching back to preferred

    # Preferred mode
    preferred_mode: NetworkMode = NetworkMode.MODEM  # Prefer 4G when available

    # Monitoring
    check_interval_s: float = 2.0  # How often to check latency


@dataclass
class FailoverState:
    """Current failover state"""

    active: bool = False
    current_mode: NetworkMode = NetworkMode.UNKNOWN
    last_switch: float = 0
    consecutive_bad_samples: int = 0
    reason: str = ""


class AutoFailover:
    """
    Automatic network failover based on latency monitoring.

    Features:
    - Continuous latency monitoring
    - Automatic switching when latency degrades
    - Hysteresis to prevent rapid switching
    - Return to preferred network when stable
    - Configurable thresholds and behavior
    """

    def __init__(self, config: FailoverConfig = None, switch_callback: Optional[Callable] = None):
        """
        Initialize auto-failover service.

        Args:
            config: Failover configuration
            switch_callback: Async function to call when switching networks
                            Should accept (target_mode: NetworkMode) and return success: bool
        """
        self.config = config or FailoverConfig()
        self.switch_callback = switch_callback

        self.state = FailoverState()
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        logger.info(f"AutoFailover initialized with config: {self.config}")

    async def start(self, initial_mode: NetworkMode = NetworkMode.UNKNOWN):
        """
        Start auto-failover monitoring.

        Args:
            initial_mode: Current network mode
        """
        if self._monitoring:
            logger.warning("AutoFailover already running")
            return

        async with self._lock:
            self.state.active = True
            self.state.current_mode = initial_mode
            self._monitoring = True

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"AutoFailover started with initial mode: {initial_mode.value}")

    async def stop(self):
        """Stop auto-failover monitoring"""
        if not self._monitoring:
            return

        self._monitoring = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            self.state.active = False

        logger.info("AutoFailover stopped")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self._monitoring:
            try:
                await self._check_and_switch()
                await asyncio.sleep(self.config.check_interval_s)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in failover monitoring loop: {e}")
                await asyncio.sleep(self.config.check_interval_s)

    async def _check_and_switch(self):
        """Check latency and switch if needed"""
        # Get current latency stats
        monitor = get_latency_monitor()
        stats = await monitor.get_current_latency()

        if not stats:
            logger.debug("No latency stats available")
            return

        # Calculate average latency across all targets
        successful_stats = [s for s in stats.values() if s.avg_latency > 0]

        if not successful_stats:
            # No connectivity - this is bad
            logger.warning("No successful pings to any target")
            await self._handle_connectivity_loss()
            return

        avg_latency = sum(s.avg_latency for s in successful_stats) / len(successful_stats)

        # Check if latency is degraded
        if avg_latency > self.config.latency_threshold_ms:
            async with self._lock:
                self.state.consecutive_bad_samples += 1

                logger.debug(
                    f"High latency detected: {avg_latency:.1f}ms "
                    f"(threshold: {self.config.latency_threshold_ms}ms), "
                    f"consecutive bad samples: {self.state.consecutive_bad_samples}"
                )

                # Check if we should switch
                if self.state.consecutive_bad_samples >= self.config.latency_check_window:
                    await self._perform_switch_if_needed(avg_latency)
        else:
            # Latency is good
            async with self._lock:
                self.state.consecutive_bad_samples = 0

            # Check if we should return to preferred mode
            await self._check_restore_preferred()

    async def _perform_switch_if_needed(self, current_latency: float):
        """
        Perform network switch if conditions are met.

        Args:
            current_latency: Current average latency
        """
        # Check cooldown period
        time_since_last_switch = time.time() - self.state.last_switch
        if time_since_last_switch < self.config.switch_cooldown_s:
            logger.debug(
                f"Switch cooldown active: {time_since_last_switch:.1f}s / " f"{self.config.switch_cooldown_s}s"
            )
            return

        # Determine target mode (switch to alternate)
        target_mode = NetworkMode.WIFI if self.state.current_mode == NetworkMode.MODEM else NetworkMode.MODEM

        # Attempt switch
        success = await self._switch_network(
            target_mode, reason=f"High latency: {current_latency:.1f}ms > {self.config.latency_threshold_ms}ms"
        )

        if success:
            self.state.last_switch = time.time()
            self.state.consecutive_bad_samples = 0
            logger.info(f"Switched to {target_mode.value} due to high latency")
        else:
            logger.error(f"Failed to switch to {target_mode.value}")

    async def _check_restore_preferred(self):
        """Check if we should restore to preferred network mode"""
        if self.state.current_mode == self.config.preferred_mode:
            return  # Already on preferred

        # Check if enough time has passed since last switch
        time_since_switch = time.time() - self.state.last_switch
        if time_since_switch < self.config.restore_delay_s:
            return

        # Check if preferred network has good latency
        monitor = get_latency_monitor()
        stats = await monitor.get_current_latency()

        if not stats:
            return

        successful_stats = [s for s in stats.values() if s.avg_latency > 0]
        if not successful_stats:
            return

        avg_latency = sum(s.avg_latency for s in successful_stats) / len(successful_stats)

        # Only restore if latency is significantly better than threshold
        restore_threshold = self.config.latency_threshold_ms * 0.7  # 30% margin

        if avg_latency < restore_threshold:
            success = await self._switch_network(
                self.config.preferred_mode, reason=f"Restoring to preferred mode (latency: {avg_latency:.1f}ms)"
            )

            if success:
                self.state.last_switch = time.time()
                logger.info(
                    f"Restored to preferred mode {self.config.preferred_mode.value} " f"(latency: {avg_latency:.1f}ms)"
                )

    async def _handle_connectivity_loss(self):
        """Handle complete connectivity loss"""
        # Try to switch to alternate network
        target_mode = NetworkMode.WIFI if self.state.current_mode == NetworkMode.MODEM else NetworkMode.MODEM

        await self._switch_network(target_mode, reason="Complete connectivity loss")

    async def _switch_network(self, target_mode: NetworkMode, reason: str) -> bool:
        """
        Execute network switch.

        Args:
            target_mode: Target network mode
            reason: Reason for switch (for logging)

        Returns:
            True if switch successful
        """
        if not self.switch_callback:
            logger.warning("No switch callback configured")
            return False

        try:
            logger.info(f"Switching to {target_mode.value}: {reason}")

            success = await self.switch_callback(target_mode)

            if success:
                async with self._lock:
                    self.state.current_mode = target_mode
                    self.state.reason = reason
                return True
            else:
                logger.error("Switch callback returned False")
                return False

        except Exception as e:
            logger.error(f"Error executing network switch: {e}")
            return False

    async def get_state(self) -> dict:
        """Get current failover state"""
        async with self._lock:
            return {
                "active": self.state.active,
                "current_mode": self.state.current_mode.value,
                "preferred_mode": self.config.preferred_mode.value,
                "last_switch": self.state.last_switch,
                "time_since_switch": time.time() - self.state.last_switch if self.state.last_switch > 0 else 0,
                "consecutive_bad_samples": self.state.consecutive_bad_samples,
                "reason": self.state.reason,
                "config": {
                    "latency_threshold_ms": self.config.latency_threshold_ms,
                    "latency_check_window": self.config.latency_check_window,
                    "switch_cooldown_s": self.config.switch_cooldown_s,
                    "restore_delay_s": self.config.restore_delay_s,
                },
            }

    async def force_switch(self, target_mode: NetworkMode, reason: str = "Manual override") -> bool:
        """
        Force an immediate network switch.

        Args:
            target_mode: Target network mode
            reason: Reason for switch

        Returns:
            True if successful
        """
        return await self._switch_network(target_mode, reason)

    async def update_config(self, **kwargs):
        """
        Update failover configuration.

        Args:
            **kwargs: Configuration parameters to update
        """
        async with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    logger.info(f"Config updated: {key} = {value}")


# Global auto-failover instance
_auto_failover: Optional[AutoFailover] = None


def get_auto_failover() -> AutoFailover:
    """Get global auto-failover instance"""
    global _auto_failover
    if _auto_failover is None:
        _auto_failover = AutoFailover()
    return _auto_failover


async def start_auto_failover(initial_mode: NetworkMode = NetworkMode.UNKNOWN):
    """Start global auto-failover"""
    failover = get_auto_failover()
    await failover.start(initial_mode)


async def stop_auto_failover():
    """Stop global auto-failover"""
    failover = get_auto_failover()
    await failover.stop()
