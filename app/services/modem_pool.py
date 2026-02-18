"""
ModemPool Service - Multi-modem management

Detects all USB 4G modems, monitors their health and quality,
and provides intelligent selection (manual or automatic).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =====================
# Data Models
# =====================


@dataclass
class ModemSignalMetrics:
    """Cellular signal metrics for a modem"""

    sinr: Optional[float] = None  # dB  (-20 to +30)
    rsrq: Optional[float] = None  # dB  (-20 to -3)
    rsrp: Optional[float] = None  # dBm (-140 to -44)
    rssi: Optional[float] = None  # dBm
    band: str = ""
    cell_id: str = ""
    pci: str = ""
    operator: str = ""
    network_type: str = ""
    signal_percent: int = 0


@dataclass
class ModemNetworkMetrics:
    """Network performance metrics for a modem"""

    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss: float = 0.0
    p95_latency_ms: float = 0.0


@dataclass
class ModemInfo:
    """Complete info about a single modem"""

    interface: str
    ip_address: Optional[str] = None
    gateway: Optional[str] = None
    is_connected: bool = False
    is_active: bool = False  # Currently selected/routing through
    is_healthy: bool = True
    signal: ModemSignalMetrics = field(default_factory=ModemSignalMetrics)
    network: ModemNetworkMetrics = field(default_factory=ModemNetworkMetrics)
    quality_score: float = 0.0  # 0-100 composite
    signal_score: float = 0.0  # 0-100 signal quality
    network_score: float = 0.0  # 0-100 network performance
    consecutive_failures: int = 0
    last_updated: float = 0.0
    last_switch_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "interface": self.interface,
            "ip_address": self.ip_address,
            "gateway": self.gateway,
            "is_connected": self.is_connected,
            "is_active": self.is_active,
            "is_healthy": self.is_healthy,
            "quality_score": round(self.quality_score, 1),
            "signal_score": round(self.signal_score, 1),
            "network_score": round(self.network_score, 1),
            "sinr": self.signal.sinr,
            "rsrq": self.signal.rsrq,
            "rsrp": self.signal.rsrp,
            "band": self.signal.band,
            "operator": self.signal.operator,
            "network_type": self.signal.network_type,
            "signal_percent": self.signal.signal_percent,
            "latency_ms": round(self.network.latency_ms, 1),
            "jitter_ms": round(self.network.jitter_ms, 1),
            "packet_loss": round(self.network.packet_loss, 1),
            "consecutive_failures": self.consecutive_failures,
            "last_updated": self.last_updated,
        }


class ModemSelectionMode(Enum):
    MANUAL = "manual"
    BEST_SCORE = "best_score"
    BEST_SINR = "best_sinr"
    BEST_LATENCY = "best_latency"
    ROUND_ROBIN = "round_robin"


# =====================
# ModemPool Service
# =====================


class ModemPool:
    """
    Manages a pool of USB 4G modems.

    - Detects all modems (interfaces with 192.168.8.x IPs)
    - Monitors individual health + quality for each modem
    - Auto-selects best modem (configurable strategy)
    - Anti-flapping: delta threshold + cooldown
    """

    # Anti-flapping config
    SWITCH_SCORE_DELTA = 20.0  # Min score advantage to force a switch
    SWITCH_COOLDOWN_S = 60.0  # Min seconds between auto-switches
    UNHEALTHY_FAILURES = 3  # Consecutive failures → mark unhealthy
    DETECTION_INTERVAL_S = 5.0  # How often to re-detect modems
    HEALTH_CHECK_INTERVAL_S = 10.0  # How often to check health per modem

    def __init__(self):
        self._modems: Dict[str, ModemInfo] = {}
        self._active_modem: Optional[str] = None
        self._selection_mode: ModemSelectionMode = ModemSelectionMode.BEST_SCORE
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._last_auto_switch: float = 0.0
        self._modem_provider = None  # Huawei/other modem provider
        self._latency_monitor = None  # LatencyMonitor instance
        logger.info("ModemPool initialized")

    def set_services(self, modem_provider=None, latency_monitor=None):
        """Wire up external service references"""
        if modem_provider:
            self._modem_provider = modem_provider
        if latency_monitor:
            self._latency_monitor = latency_monitor

    # ----------------------
    # Lifecycle
    # ----------------------

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._detection_loop())
        logger.info("ModemPool started")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ModemPool stopped")

    # ----------------------
    # Detection Loop
    # ----------------------

    async def _detection_loop(self):
        """Main loop: detect modems, update health, auto-select"""
        while self._running:
            try:
                await self._detect_modems()
                await self._update_all_health()
                await self._update_all_scores()
                if self._selection_mode != ModemSelectionMode.MANUAL:
                    await self._auto_select()
            except Exception as e:
                logger.error(f"ModemPool loop error: {e}")
            await asyncio.sleep(self.DETECTION_INTERVAL_S)

    async def _detect_modems(self):
        """Detect all modem interfaces via IP detection"""
        from app.api.routes.network.common import detect_modem_interfaces, get_gateway_for_interface

        try:
            interfaces = await detect_modem_interfaces()
        except Exception as e:
            logger.warning(f"ModemPool: detection error: {e}")
            return

        async with self._lock:
            # Add newly detected modems
            for iface in interfaces:
                if iface not in self._modems:
                    gateway = await get_gateway_for_interface(iface)
                    ip = await self._get_interface_ip(iface)
                    self._modems[iface] = ModemInfo(
                        interface=iface,
                        ip_address=ip,
                        gateway=gateway,
                        is_connected=True,
                        last_updated=time.time(),
                    )
                    logger.info(f"ModemPool: new modem detected: {iface} (gw={gateway})")

                    # First modem detected becomes active
                    if self._active_modem is None:
                        self._active_modem = iface
                        self._modems[iface].is_active = True
                        logger.info(f"ModemPool: {iface} set as initial active modem")
                else:
                    # Update connectivity
                    gw = await get_gateway_for_interface(iface)
                    self._modems[iface].gateway = gw
                    self._modems[iface].is_connected = True

            # Mark removed modems as disconnected (don't delete — preserve history)
            for iface, modem in self._modems.items():
                if iface not in interfaces:
                    if modem.is_connected:
                        logger.warning(f"ModemPool: modem disconnected: {iface}")
                    modem.is_connected = False
                    modem.is_healthy = False
                    if modem.is_active:
                        modem.is_active = False
                        self._active_modem = None

    async def _get_interface_ip(self, interface: str) -> Optional[str]:
        """Get IP address for interface"""
        import re
        from app.api.routes.network.common import run_command

        stdout, _, rc = await run_command(["ip", "-o", "addr", "show", interface])
        if rc == 0:
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", stdout)
            if match:
                return match.group(1)
        return None

    # ----------------------
    # Health & Score Updates
    # ----------------------

    async def _update_all_health(self):
        """Update health status for all connected modems"""
        async with self._lock:
            for modem in self._modems.values():
                if not modem.is_connected:
                    continue
                try:
                    await self._check_modem_health(modem)
                except Exception as e:
                    logger.debug(f"Health check error for {modem.interface}: {e}")

    async def _check_modem_health(self, modem: ModemInfo):
        """Ping and signal check for a single modem"""
        from app.api.routes.network.common import run_command

        healthy = False

        # 1. Ping check via modem gateway
        if modem.gateway:
            _, _, rc = await run_command(
                ["ping", "-c", "1", "-W", "2", "-I", modem.interface, modem.gateway],
                timeout=5,
            )
            healthy = rc == 0

        # 2. SINR sanity check
        if modem.signal.sinr is not None and modem.signal.sinr < -10:
            healthy = False

        if healthy:
            modem.consecutive_failures = 0
            modem.is_healthy = True
        else:
            modem.consecutive_failures += 1
            if modem.consecutive_failures >= self.UNHEALTHY_FAILURES:
                modem.is_healthy = False
                logger.warning(
                    f"ModemPool: {modem.interface} marked unhealthy " f"(failures={modem.consecutive_failures})"
                )

    async def _update_all_scores(self):
        """Get signal + latency metrics and compute quality scores for each modem"""
        async with self._lock:
            for modem in self._modems.values():
                if not modem.is_connected:
                    continue
                await self._update_modem_metrics(modem)
                self._compute_quality_score(modem)
                modem.last_updated = time.time()

    async def _update_modem_metrics(self, modem: ModemInfo):
        """Fetch signal and latency metrics for a modem"""
        # Signal metrics — only from active modem via provider
        if self._modem_provider and modem.is_active:
            try:
                loop = asyncio.get_event_loop()

                if hasattr(self._modem_provider, "async_get_signal_info"):
                    signal = await self._modem_provider.async_get_signal_info()
                else:
                    signal = await loop.run_in_executor(None, self._modem_provider._get_signal_info_sync)

                if hasattr(self._modem_provider, "async_get_raw_network_info"):
                    network = await self._modem_provider.async_get_raw_network_info()
                else:
                    network = await loop.run_in_executor(None, self._modem_provider._get_network_info_sync)

                if signal:

                    def _parse_float(val, suffix=""):
                        try:
                            return float(str(val).replace(suffix, "").strip())
                        except Exception:
                            return None

                    modem.signal.sinr = _parse_float(signal.get("sinr", ""), "dB")
                    modem.signal.rsrq = _parse_float(signal.get("rsrq", ""), "dB")
                    modem.signal.rsrp = _parse_float(signal.get("rsrp", ""), "dBm")
                    modem.signal.band = signal.get("band", "")
                    modem.signal.cell_id = signal.get("cell_id", "")
                    modem.signal.pci = signal.get("pci", "")
                    modem.signal.signal_percent = signal.get("signal_percent", 0)
                    if network:
                        modem.signal.operator = network.get("operator", "")
                        modem.signal.network_type = network.get("network_type_ex", "")

            except Exception as e:
                logger.debug(f"Signal metrics error for {modem.interface}: {e}")

        # Latency metrics — use LatencyMonitor per interface if available
        if self._latency_monitor:
            try:
                latency_data = await self._latency_monitor.get_interface_latency(modem.interface)
                if latency_data:
                    modem.network.latency_ms = latency_data.avg_latency
                    modem.network.jitter_ms = latency_data.jitter_ms
                    modem.network.packet_loss = latency_data.packet_loss
                    modem.network.p95_latency_ms = latency_data.p95_latency
            except Exception as e:
                logger.debug(f"Latency metrics error for {modem.interface}: {e}")

    def _compute_quality_score(self, modem: ModemInfo):
        """
        Compute quality_score (0-100) based on signal + network metrics.

        Weights: SINR 40% | RSRQ 15% | Latency 30% | Jitter 15%
        """

        def clamp(v: float, lo=0.0, hi=100.0) -> float:
            return max(lo, min(hi, v))

        # Signal score
        sinr_score = 50.0
        rsrq_score = 50.0

        if modem.signal.sinr is not None:
            sinr_score = clamp((modem.signal.sinr + 5) * 100 / 30)
        if modem.signal.rsrq is not None:
            rsrq_score = clamp((modem.signal.rsrq + 20) * 100 / 17)

        signal_score = 0.72 * sinr_score + 0.28 * rsrq_score  # sub-weighted

        # Network score
        latency_score = clamp(100 - modem.network.latency_ms / 4)
        jitter_score = clamp(100 - modem.network.jitter_ms)

        network_score = 0.67 * latency_score + 0.33 * jitter_score  # sub-weighted

        # Composite (SINR 40%, RSRQ 15%, Latency 30%, Jitter 15%)
        quality_score = 0.40 * sinr_score + 0.15 * rsrq_score + 0.30 * latency_score + 0.15 * jitter_score

        modem.signal_score = round(signal_score, 1)
        modem.network_score = round(network_score, 1)
        modem.quality_score = round(quality_score, 1)

    # ----------------------
    # Auto-Selection
    # ----------------------

    async def _auto_select(self):
        """Auto-select best modem based on mode, with anti-flapping"""
        now = time.time()

        # Cooldown check
        if now - self._last_auto_switch < self.SWITCH_COOLDOWN_S:
            return

        async with self._lock:
            healthy_modems = [m for m in self._modems.values() if m.is_connected and m.is_healthy]
            if len(healthy_modems) < 2:
                return  # Nothing to compare

            # Find best candidate
            candidate = self._pick_best(healthy_modems)
            if not candidate or candidate.interface == self._active_modem:
                return

            # Get current active modem score
            current = self._modems.get(self._active_modem)
            current_score = current.quality_score if current else 0.0

            if candidate.quality_score < current_score + self.SWITCH_SCORE_DELTA:
                return  # Not enough advantage

        # Switch (outside lock to avoid deadlock)
        logger.info(
            f"ModemPool: auto-switching {self._active_modem} → {candidate.interface} "
            f"(score delta: {candidate.quality_score - current_score:.1f})"
        )
        await self.select_modem(candidate.interface, reason="auto")
        self._last_auto_switch = now

    def _pick_best(self, modems: List[ModemInfo]) -> Optional[ModemInfo]:
        """Pick best modem according to selection mode"""
        if not modems:
            return None

        if self._selection_mode == ModemSelectionMode.BEST_SCORE:
            return max(modems, key=lambda m: m.quality_score)
        elif self._selection_mode == ModemSelectionMode.BEST_SINR:
            with_sinr = [m for m in modems if m.signal.sinr is not None]
            return max(with_sinr, key=lambda m: m.signal.sinr) if with_sinr else modems[0]
        elif self._selection_mode == ModemSelectionMode.BEST_LATENCY:
            return min(modems, key=lambda m: m.network.latency_ms or 9999)
        else:
            return modems[0]

    # ----------------------
    # Public API
    # ----------------------

    async def select_modem(self, interface: str, reason: str = "manual") -> bool:
        """
        Select a modem as the active one.
        Updates routing priority so traffic goes through it.

        FASE 3 — VPN protection:
          1. PRE-SWITCH:  check VPN health baseline (non-blocking warn)
          2. Execute switch + apply routing
          3. POST-SWITCH: wait up to 15s for VPN recovery
          4. ROLLBACK:    if VPN doesn't recover, revert to previous modem
        """
        async with self._lock:
            if interface not in self._modems:
                logger.error(f"ModemPool: unknown modem {interface}")
                return False

            modem = self._modems[interface]
            if not modem.is_connected:
                logger.warning(f"ModemPool: {interface} is not connected")
                return False

            previous = self._active_modem
            if previous == interface:
                return True  # Already active

            # Deactivate previous
            if previous and previous in self._modems:
                self._modems[previous].is_active = False

            # Activate new
            modem.is_active = True
            modem.last_switch_time = time.time()
            self._active_modem = interface

        logger.info(f"ModemPool: switched {previous} → {interface} (reason={reason})")

        # ── FASE 3: PRE-SWITCH VPN baseline ──────────────────────────────
        vpn_pre_ok = True
        vpn_health_enabled = self._is_vpn_health_enabled()
        if vpn_health_enabled and reason != "rollback":
            try:
                from app.services.vpn_health_checker import get_vpn_health_checker

                vpn_checker = get_vpn_health_checker()
                pre_result = await vpn_checker.check_vpn_health()
                vpn_pre_ok = pre_result["healthy"]
                if not vpn_pre_ok:
                    logger.warning(
                        f"ModemPool: VPN unhealthy before switch " f"({pre_result['message']}) — proceeding anyway"
                    )
                else:
                    logger.debug(
                        "ModemPool: VPN pre-switch baseline OK"
                        + (f" RTT={pre_result['rtt_ms']}ms" if pre_result["rtt_ms"] else "")
                    )
            except Exception as ve:
                logger.debug(f"ModemPool: VPN pre-check skipped: {ve}")
                vpn_health_enabled = False  # Disable post-check too if pre-check fails
        # ─────────────────────────────────────────────────────────────────

        # Apply routing priority
        success = await self._apply_modem_priority(interface)
        if not success:
            logger.warning(f"ModemPool: routing update failed for {interface}")

        # ── FASE 3: POST-SWITCH VPN recovery + rollback ───────────────────
        if vpn_health_enabled and reason != "rollback" and previous:
            try:
                from app.services.vpn_health_checker import get_vpn_health_checker

                vpn_checker = get_vpn_health_checker()

                # Determine recovery timeout from preferences (default 15s)
                timeout_s = self._get_vpn_recovery_timeout()
                logger.info(f"ModemPool: waiting up to {timeout_s}s for VPN recovery on {interface}…")
                recovered = await vpn_checker.wait_for_vpn_recovery(timeout_s)

                if not recovered:
                    logger.error(
                        f"ModemPool: VPN did NOT recover after switch to {interface} " f"— rolling back to {previous}"
                    )
                    await self._rollback_to_modem(previous, interface)
                    return False
            except Exception as ve:
                logger.warning(f"ModemPool: VPN post-check error (non-fatal): {ve}")
        # ─────────────────────────────────────────────────────────────────

        return True

    async def _rollback_to_modem(self, previous: str, failed: str):
        """Revert modem selection to `previous` after a VPN recovery failure."""
        logger.warning(f"ModemPool: ROLLBACK {failed} → {previous}")
        async with self._lock:
            # Reset active state
            if failed in self._modems:
                self._modems[failed].is_active = False
            if previous in self._modems and self._modems[previous].is_connected:
                self._modems[previous].is_active = True
                self._modems[previous].last_switch_time = time.time()
                self._active_modem = previous
            else:
                self._active_modem = None

        if previous in self._modems:
            await self._apply_modem_priority(previous)
            logger.info(f"ModemPool: rollback to {previous} completed")

    def _is_vpn_health_enabled(self) -> bool:
        """Read vpn_health_check_enabled from preferences (default True)."""
        try:
            from app.services.preferences_service import get_preferences_service

            prefs_svc = get_preferences_service()
            all_prefs = prefs_svc.get_all_preferences()
            return all_prefs.get("network", {}).get("vpn_health_check_enabled", True)
        except Exception:
            return True

    def _get_vpn_recovery_timeout(self) -> float:
        """Read vpn_recovery_timeout_s from preferences (default 15s)."""
        try:
            from app.services.preferences_service import get_preferences_service

            prefs_svc = get_preferences_service()
            all_prefs = prefs_svc.get_all_preferences()
            return float(all_prefs.get("network", {}).get("vpn_recovery_timeout_s", 15))
        except Exception:
            return 15.0

    async def _apply_modem_priority(self, interface: str) -> bool:
        """Apply OS-level routing to route traffic through selected modem"""
        async with self._lock:
            modem = self._modems.get(interface)
            if not modem or not modem.gateway:
                return False
            gateway = modem.gateway

        from app.api.routes.network.common import run_command

        try:
            # Remove all existing default routes
            stdout, _, _ = await run_command(["ip", "route", "show", "default"])
            for line in stdout.splitlines():
                if "default" in line:
                    parts = line.split()
                    await run_command(["sudo", "ip", "route", "del"] + parts)

            # Add new default route via selected modem
            _, _, rc = await run_command(
                [
                    "sudo",
                    "ip",
                    "route",
                    "add",
                    "default",
                    "via",
                    gateway,
                    "dev",
                    interface,
                    "metric",
                    "100",
                ]
            )

            # ── FASE 2: update policy routing tables (VPN + Video) ────────
            try:
                from app.services.policy_routing_manager import get_policy_routing_manager

                policy_manager = get_policy_routing_manager()
                policy_ok = await policy_manager.update_active_modem(interface, gateway)
                if policy_ok:
                    logger.info(f"ModemPool: policy routing updated for {interface} via {gateway}")
                else:
                    logger.warning(f"ModemPool: policy routing update failed for {interface}")
            except Exception as pe:
                logger.warning(f"ModemPool: policy routing error (non-fatal): {pe}")
            # ─────────────────────────────────────────────────────────────

            return rc == 0
        except Exception as e:
            logger.error(f"ModemPool: routing error: {e}")
            return False

    async def get_all_modems(self) -> List[ModemInfo]:
        async with self._lock:
            return list(self._modems.values())

    async def get_connected_modems(self) -> List[ModemInfo]:
        async with self._lock:
            return [m for m in self._modems.values() if m.is_connected]

    async def get_healthy_modems(self) -> List[ModemInfo]:
        async with self._lock:
            return [m for m in self._modems.values() if m.is_connected and m.is_healthy]

    async def get_active_modem(self) -> Optional[ModemInfo]:
        async with self._lock:
            if self._active_modem:
                return self._modems.get(self._active_modem)
            return None

    async def get_best_modem(self) -> Optional[ModemInfo]:
        async with self._lock:
            healthy = [m for m in self._modems.values() if m.is_connected and m.is_healthy]
            return max(healthy, key=lambda m: m.quality_score) if healthy else None

    async def get_modem(self, interface: str) -> Optional[ModemInfo]:
        async with self._lock:
            return self._modems.get(interface)

    async def refresh(self):
        """Force immediate re-detection"""
        await self._detect_modems()
        await self._update_all_health()
        await self._update_all_scores()

    def set_selection_mode(self, mode: str) -> bool:
        try:
            self._selection_mode = ModemSelectionMode(mode)
            logger.info(f"ModemPool: selection mode set to {mode}")
            return True
        except ValueError:
            logger.error(f"ModemPool: unknown selection mode: {mode}")
            return False

    async def get_status(self) -> dict:
        async with self._lock:
            modems = list(self._modems.values())

        return {
            "enabled": self._running,
            "total_modems": len(modems),
            "connected_modems": sum(1 for m in modems if m.is_connected),
            "healthy_modems": sum(1 for m in modems if m.is_connected and m.is_healthy),
            "active_modem": self._active_modem,
            "selection_mode": self._selection_mode.value,
            "modems": [m.to_dict() for m in modems],
        }


# =====================
# Singleton
# =====================

_modem_pool: Optional[ModemPool] = None


def get_modem_pool() -> ModemPool:
    global _modem_pool
    if _modem_pool is None:
        _modem_pool = ModemPool()
    return _modem_pool
