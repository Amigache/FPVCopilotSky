"""
Network ↔ Video Event Bridge (Mejoras Nº3, Nº4, Nº7, Nº8)

Self-healing streaming: network events trigger adaptive video responses.
Converts the system from reactive to predictive by monitoring cellular
signal metrics and cross-referencing with video encoding parameters.

Events monitored:
- Cell change (Cell ID, PCI, Band) → force keyframe + recalibrate bitrate
- SINR degradation → proactive bitrate reduction
- Jitter spikes → increase keyframe rate
- RTT spikes → reduce framerate
- Packet loss → reduce resolution

Composite Quality Score (Mejora Nº7):
- Replaces fixed SINR thresholds with weighted multi-metric score
- Smooth bitrate adaptation instead of step functions
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
from app.services.preferences import get_preferences

logger = logging.getLogger(__name__)


class NetworkEvent(Enum):
    """Network events that can trigger video adaptation"""

    CELL_CHANGE = "cell_change"
    BAND_CHANGE = "band_change"
    SINR_DROP = "sinr_drop"
    SINR_RECOVERY = "sinr_recovery"
    RSRP_DROP = "rsrp_drop"
    HIGH_JITTER = "high_jitter"
    JITTER_RECOVERY = "jitter_recovery"
    HIGH_RTT = "high_rtt"
    RTT_RECOVERY = "rtt_recovery"
    PACKET_LOSS = "packet_loss"
    PACKET_LOSS_RECOVERY = "packet_loss_recovery"
    DISCONNECTION = "disconnection"
    RECONNECTION = "reconnection"
    QUALITY_CHANGE = "quality_change"


class VideoAction(Enum):
    """Video actions triggered by network events"""

    FORCE_KEYFRAME = "force_keyframe"
    REDUCE_BITRATE = "reduce_bitrate"
    INCREASE_BITRATE = "increase_bitrate"
    REDUCE_FRAMERATE = "reduce_framerate"
    RESTORE_FRAMERATE = "restore_framerate"
    INCREASE_KEYFRAME_RATE = "increase_keyframe_rate"
    RESTORE_KEYFRAME_RATE = "restore_keyframe_rate"
    REDUCE_RESOLUTION = "reduce_resolution"
    RESTORE_RESOLUTION = "restore_resolution"


@dataclass
class CellState:
    """Tracks cellular state for change detection (Mejora Nº3)"""

    cell_id: str = ""
    pci: str = ""
    band: str = ""
    sinr: Optional[float] = None
    rsrp: Optional[float] = None
    rsrq: Optional[float] = None
    network_type: str = ""
    operator: str = ""
    timestamp: float = 0.0

    # Rolling SINR history for trend detection
    sinr_history: List[float] = field(default_factory=list)
    sinr_history_max: int = 20


@dataclass
class NetworkQualityScore:
    """
    Composite quality score (Mejora Nº7)

    Replaces fixed threshold tables with a continuous 0-100 score.
    Bitrate adapts smoothly based on this score.
    """

    score: float = 50.0  # 0-100
    sinr_component: float = 0.0
    rsrq_component: float = 0.0
    jitter_component: float = 0.0
    packet_loss_component: float = 0.0
    recommended_bitrate_kbps: int = 1500
    recommended_resolution: str = "1280x720"
    recommended_framerate: int = 30
    quality_label: str = "Moderado"
    trend: str = "stable"  # "improving", "degrading", "stable"


@dataclass
class EventBridgeConfig:
    """Configuration for the network-video event bridge"""

    # Monitoring interval
    poll_interval_s: float = 2.0

    # Cell change detection (Mejora Nº3)
    cell_change_keyframe_delay_ms: int = 100  # Delay before forcing keyframe after cell change
    cell_change_bitrate_reduction: float = 0.8  # Reduce bitrate to 80% on cell change

    # SINR degradation detection (Mejora Nº2 predictive)
    sinr_drop_threshold_percent: float = 30.0  # 30% drop in 10s = pre-switch
    sinr_drop_window_s: float = 10.0
    sinr_critical: float = 0.0  # dB
    sinr_poor: float = 5.0
    sinr_moderate: float = 10.0
    sinr_good: float = 15.0
    sinr_excellent: float = 20.0

    # Jitter control (Mejora Nº4)
    jitter_high_ms: float = 40.0  # Reduce bitrate when jitter > 40ms
    jitter_critical_ms: float = 80.0  # Drastically reduce when > 80ms
    jitter_recovery_ms: float = 20.0  # Restore when jitter < 20ms

    # RTT thresholds
    rtt_high_ms: float = 200.0  # Reduce framerate
    rtt_critical_ms: float = 400.0  # Minimum framerate
    rtt_recovery_ms: float = 100.0  # Restore framerate

    # Packet loss thresholds
    packet_loss_moderate: float = 2.0  # % - increase keyframe rate
    packet_loss_high: float = 5.0  # % - reduce resolution
    packet_loss_critical: float = 10.0  # % - minimum everything

    # Composite score weights (Mejora Nº7)
    weight_sinr: float = 0.35
    weight_rsrq: float = 0.15
    weight_jitter: float = 0.30
    weight_packet_loss: float = 0.20

    # Bitrate mapping (score → kbps)
    max_bitrate_kbps: int = 8000
    min_bitrate_kbps: int = 500

    # Smoothing
    score_smoothing: float = 0.3  # EMA alpha (0=no change, 1=instant)
    bitrate_change_rate: float = 0.2  # Max 20% change per interval


@dataclass
class BridgeEvent:
    """A recorded network event"""

    timestamp: float
    event: NetworkEvent
    details: Dict[str, Any]
    actions_taken: List[VideoAction]


async def detect_primary_interface() -> dict:
    """
    Detect the primary network interface directly from the routing table.
    Returns {"interface": "eth1", "type": "modem"} or {"interface": "wlan0", "type": "wifi"}
    No HTTP calls - fast and reliable.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "route", "show", "default", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        output = stdout.decode().strip()

        if not output:
            return {"interface": "", "type": "unknown"}

        # Parse all default routes and pick the one with lowest metric
        best_iface = None
        best_metric = float("inf")

        for line in output.split("\n"):
            if "default" not in line:
                continue
            iface = None
            metric = 0
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "dev" and i + 1 < len(parts):
                    iface = parts[i + 1]
                elif part == "metric" and i + 1 < len(parts):
                    try:
                        metric = int(parts[i + 1])
                    except ValueError:
                        pass
            if iface and metric < best_metric:
                best_iface = iface
                best_metric = metric

        if not best_iface:
            return {"interface": "", "type": "unknown"}

        # Determine type: check if interface has modem IP (192.168.8.x)
        iface_type = "unknown"
        proc2 = await asyncio.create_subprocess_exec(
            "ip", "-o", "addr", "show", best_iface, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=2.0)
        addr_output = stdout2.decode().strip()

        if "192.168.8." in addr_output:
            iface_type = "modem"
        elif best_iface.startswith(("wlan", "wl")):
            iface_type = "wifi"
        elif best_iface.startswith(("eth", "enp")):
            iface_type = "ethernet"
        elif best_iface.startswith(("wwan", "usb", "enx")):
            iface_type = "modem"

        return {"interface": best_iface, "type": iface_type}

    except Exception as e:
        logger.debug(f"Error detecting primary interface: {e}")
        return {"interface": "", "type": "unknown"}


class NetworkEventBridge:
    """
    Bridge between network monitoring and video encoding.

    Monitors cellular signal metrics continuously and triggers
    adaptive video responses in real-time.

    This is the core of the self-healing streaming system.
    """

    def __init__(self, config: EventBridgeConfig = None):
        self.config = config or EventBridgeConfig()

        # Current state
        self._cell_state = CellState()
        self._quality_score = NetworkQualityScore()
        self._last_jitter_ms: float = 0.0
        self._last_rtt_ms: float = 0.0
        self._last_packet_loss: float = 0.0

        # Service references (set externally)
        self._modem_provider = None
        self._gstreamer_service = None
        self._webrtc_service = None
        self._websocket_manager = None
        self._latency_monitor = None

        # Event log
        self._events: List[BridgeEvent] = []
        self._events_max: int = 500

        # Primary interface tracking (cached to avoid flapping)
        self._primary_interface: str = ""
        self._primary_type: str = "unknown"  # "modem", "wifi", "ethernet", "unknown"

        # Monitoring state
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._netlink_task: Optional[asyncio.Task] = None
        self._route_changed_event: asyncio.Event = asyncio.Event()
        self._lock = asyncio.Lock()

        # Cooldowns to avoid flapping
        self._last_cell_change_time: float = 0
        self._last_bitrate_change_time: float = 0
        self._last_keyframe_time: float = 0

        # Adaptive resolution state (4.8)
        self._low_score_since: float = 0.0  # timestamp when score first dropped below threshold
        self._last_resolution_change_time: float = 0.0
        self._pre_downscale_resolution: Optional[tuple] = None  # (width, height) before downscale
        self._adaptive_res_threshold: float = 30.0  # score below which to trigger
        self._adaptive_res_hold_s: float = 10.0  # how long score must stay low
        self._adaptive_res_cooldown_s: float = 30.0  # min time between resolution changes

        logger.info("NetworkEventBridge initialized")

    def set_services(
        self,
        modem_provider=None,
        gstreamer_service=None,
        webrtc_service=None,
        websocket_manager=None,
        latency_monitor=None,
    ):
        """Wire up service references"""
        if modem_provider:
            self._modem_provider = modem_provider
        if gstreamer_service:
            self._gstreamer_service = gstreamer_service
        if webrtc_service:
            self._webrtc_service = webrtc_service
        if websocket_manager:
            self._websocket_manager = websocket_manager
        if latency_monitor:
            self._latency_monitor = latency_monitor
        logger.info("NetworkEventBridge services configured")

    # ======================
    # Lifecycle
    # ======================

    async def start(self):
        """Start monitoring network events"""
        if self._monitoring:
            logger.warning("NetworkEventBridge already running")
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._netlink_task = asyncio.create_task(self._netlink_route_monitor())
        logger.info("NetworkEventBridge started (polling + netlink)")

    async def stop(self):
        """Stop monitoring"""
        if not self._monitoring:
            return

        self._monitoring = False
        self._route_changed_event.set()  # unblock any wait

        for task in (self._monitor_task, self._netlink_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._monitor_task = None
        self._netlink_task = None
        logger.info("NetworkEventBridge stopped")

    # ======================
    # Netlink route monitor
    # ======================

    async def _netlink_route_monitor(self):
        """Watch for route changes via ``ip monitor route``.

        When a route change is detected the ``_route_changed_event`` flag is
        set so the main polling loop can immediately re-evaluate the primary
        interface instead of waiting for the next polling interval.
        """
        while self._monitoring:
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ip",
                    "monitor",
                    "route",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                while self._monitoring and proc.stdout:
                    try:
                        line = await asyncio.wait_for(proc.stdout.readline(), timeout=30.0)
                    except asyncio.TimeoutError:
                        continue
                    if not line:
                        break  # EOF
                    decoded = line.decode(errors="replace").strip()
                    if decoded:
                        logger.info(f"[Netlink] Route change detected: {decoded}")
                        self._route_changed_event.set()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Netlink monitor error: {e}")
                await asyncio.sleep(5.0)  # backoff before retry
            finally:
                if proc:
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        pass

    # ======================
    # Main Loop
    # ======================

    async def _monitor_loop(self):
        """Main monitoring loop - polls only the primary interface for quality"""
        _cycle_count = 0
        while self._monitoring:
            try:
                _cycle_count += 1

                # 0. Detect primary interface (direct from routing table, no HTTP)
                iface_info = await detect_primary_interface()
                new_iface = iface_info["interface"]
                new_type = iface_info["type"]

                # Only update if we got a valid result (avoid flapping on errors)
                if new_iface:
                    if new_iface != self._primary_interface:
                        logger.info(
                            f"[Bridge] Primary interface changed: "
                            f"{self._primary_interface or 'none'} → {new_iface} (type: {new_type})"
                        )
                    self._primary_interface = new_iface
                    self._primary_type = new_type
                else:
                    # Detection failed - keep previous interface, log warning
                    if _cycle_count % 15 == 0:  # Log every ~30s
                        logger.warning(
                            f"[Bridge] Interface detection failed, keeping: "
                            f"{self._primary_interface} ({self._primary_type})"
                        )

                # 1. Collect metrics ONLY for primary interface type
                cell_data = None
                latency_data = None

                if self._primary_type == "modem":
                    # Modem: get cellular signal metrics (SINR, RSRP, RSRQ)
                    cell_data = await self._get_cell_metrics()
                # else: no cell_data for wifi/ethernet - SINR/RSRQ not applicable

                # Latency metrics for any interface type
                if self._latency_monitor:
                    try:
                        latency_data_raw = await self._latency_monitor.get_interface_latency(self._primary_interface)
                        if latency_data_raw:
                            latency_data = {
                                "avg_rtt": latency_data_raw.avg_latency,
                                "jitter": latency_data_raw.jitter_ms,
                                "p95_latency": latency_data_raw.p95_latency,
                                "packet_loss": latency_data_raw.packet_loss,
                                "available": True,
                            }
                    except Exception:
                        latency_data = None

                # Diagnostic log every ~30s
                if _cycle_count % 15 == 1:
                    cell_str = f"OK sinr={cell_data.get('sinr')}" if cell_data else "None"
                    latency_str = f"OK rtt={round(latency_data.get('avg_rtt', 0), 1)}" if latency_data else "None"
                    logger.info(
                        f"[Bridge] iface={self._primary_interface}({self._primary_type}) "
                        f"cell={cell_str} latency={latency_str} "
                        f"score={self._quality_score.score}"
                    )

                # 2. Check if we have ANY data before updating score
                has_any_data = cell_data is not None or latency_data is not None

                if not has_any_data:
                    # No data at all - skip score update, keep previous values
                    # This prevents resetting to 100/0 when data is temporarily unavailable
                    if _cycle_count % 15 == 0:
                        logger.warning(
                            f"[Bridge] No data available for {self._primary_interface} - "
                            f"keeping previous score {self._quality_score.score}"
                        )
                    await self._broadcast_status()
                    await asyncio.sleep(self.config.poll_interval_s)
                    continue

                # 3. Detect events from primary interface metrics
                events = []
                if cell_data:
                    events.extend(self._detect_cell_events(cell_data))
                    events.extend(self._detect_sinr_events(cell_data))
                if latency_data:
                    events.extend(self._detect_jitter_events(latency_data))
                    events.extend(self._detect_rtt_events(latency_data))
                    events.extend(self._detect_packet_loss_events(latency_data))

                # 4. Calculate score with interface-aware weighting
                self._update_quality_score(cell_data, latency_data)

                # 5. Execute actions
                for event_type, details in events:
                    await self._handle_event(event_type, details)

                # 6. Adaptive bitrate
                await self._apply_adaptive_bitrate()

                # 6b. Adaptive resolution (pipeline restart when score is critically low)
                await self._apply_adaptive_resolution()

                # 7. Broadcast status
                await self._broadcast_status()

                # Sleep OR wake immediately if netlink detected a route change
                self._route_changed_event.clear()
                try:
                    await asyncio.wait_for(
                        self._route_changed_event.wait(),
                        timeout=self.config.poll_interval_s,
                    )
                    # Route changed — loop immediately
                    logger.debug("[Bridge] Woke early due to netlink route change")
                except asyncio.TimeoutError:
                    pass  # normal poll interval elapsed

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in NetworkEventBridge loop: {e}")
                await asyncio.sleep(self.config.poll_interval_s)

    # ======================
    # Metric Collection
    # ======================

    async def _get_cell_metrics(self) -> Optional[Dict]:
        """Get current cellular metrics from modem provider"""
        if not self._modem_provider:
            return None

        try:
            loop = asyncio.get_event_loop()

            # Try async methods first, fall back to sync
            if hasattr(self._modem_provider, "async_get_signal_info"):
                signal = await self._modem_provider.async_get_signal_info()
            else:
                signal = await loop.run_in_executor(None, self._modem_provider._get_signal_info_sync)

            if hasattr(self._modem_provider, "async_get_raw_network_info"):
                network = await self._modem_provider.async_get_raw_network_info()
            else:
                network = await loop.run_in_executor(None, self._modem_provider._get_network_info_sync)

            if not signal:
                return None

            # Parse SINR
            sinr = None
            sinr_str = signal.get("sinr", "")
            if sinr_str:
                try:
                    sinr = float(str(sinr_str).replace("dB", "").strip())
                except (ValueError, AttributeError):
                    pass

            # Parse RSRP
            rsrp = None
            rsrp_str = signal.get("rsrp", "")
            if rsrp_str:
                try:
                    rsrp = float(str(rsrp_str).replace("dBm", "").strip())
                except (ValueError, AttributeError):
                    pass

            # Parse RSRQ
            rsrq = None
            rsrq_str = signal.get("rsrq", "")
            if rsrq_str:
                try:
                    rsrq = float(str(rsrq_str).replace("dB", "").strip())
                except (ValueError, AttributeError):
                    pass

            return {
                "cell_id": signal.get("cell_id", ""),
                "pci": signal.get("pci", ""),
                "band": signal.get("band", ""),
                "sinr": sinr,
                "rsrp": rsrp,
                "rsrq": rsrq,
                "signal_percent": signal.get("signal_percent", 0),
                "network_type": network.get("network_type_ex", "") if network else "",
                "operator": network.get("operator", "") if network else "",
                "connection_status": network.get("connection_status_code", "") if network else "",
            }

        except Exception:
            # logger.debug(f"Error getting cell metrics: {e}")  # Comentado
            return None

    async def _get_latency_metrics(self) -> Optional[Dict]:
        """Get current latency metrics from latency monitor"""
        if not self._latency_monitor:
            return None

        try:
            stats = await self._latency_monitor.get_current_latency()
            if not stats:
                return None

            successful = [s for s in stats.values() if s.avg_latency > 0]
            if not successful:
                return {"avg_rtt": 0, "jitter": 0, "packet_loss": 100.0, "available": False}

            return {
                "avg_rtt": sum(s.avg_latency for s in successful) / len(successful),
                "jitter": max(s.jitter_ms for s in successful),
                "p95_latency": max(s.p95_latency for s in successful),
                "packet_loss": sum(s.packet_loss for s in successful) / len(successful),
                "available": True,
            }

        except Exception:
            # logger.debug(f"Error getting latency metrics: {e}")  # Comentado
            return None

    # ======================
    # Event Detection (Mejora Nº3: Cell Change)
    # ======================

    def _detect_cell_events(self, cell_data: Dict) -> List[tuple]:
        """Detect cell changes (Cell ID, PCI, Band) - Mejora Nº3"""
        events = []
        now = time.time()

        new_cell_id = cell_data.get("cell_id", "")
        new_pci = cell_data.get("pci", "")
        new_band = cell_data.get("band", "")

        # Cell ID change
        if new_cell_id and self._cell_state.cell_id and new_cell_id != self._cell_state.cell_id:
            events.append(
                (
                    NetworkEvent.CELL_CHANGE,
                    {
                        "old_cell_id": self._cell_state.cell_id,
                        "new_cell_id": new_cell_id,
                        "old_pci": self._cell_state.pci,
                        "new_pci": new_pci,
                    },
                )
            )
            logger.info(
                f"Cell change detected: {self._cell_state.cell_id} → {new_cell_id} "
                f"(PCI: {self._cell_state.pci} → {new_pci})"
            )

        # Band change
        if new_band and self._cell_state.band and new_band != self._cell_state.band:
            events.append(
                (
                    NetworkEvent.BAND_CHANGE,
                    {
                        "old_band": self._cell_state.band,
                        "new_band": new_band,
                    },
                )
            )
            logger.info(f"Band change detected: {self._cell_state.band} → {new_band}")

        # Disconnection/Reconnection
        conn_status = cell_data.get("connection_status", "")
        if conn_status == "902" and self._cell_state.timestamp > 0:
            events.append((NetworkEvent.DISCONNECTION, {}))
        elif conn_status == "901" and self._cell_state.cell_id == "":
            events.append((NetworkEvent.RECONNECTION, {}))

        # Update state
        self._cell_state.cell_id = new_cell_id
        self._cell_state.pci = new_pci
        self._cell_state.band = new_band
        self._cell_state.sinr = cell_data.get("sinr")
        self._cell_state.rsrp = cell_data.get("rsrp")
        self._cell_state.rsrq = cell_data.get("rsrq")
        self._cell_state.network_type = cell_data.get("network_type", "")
        self._cell_state.operator = cell_data.get("operator", "")
        self._cell_state.timestamp = now

        return events

    # ======================
    # Predictive SINR Detection (Mejora Nº2)
    # ======================

    def _detect_sinr_events(self, cell_data: Dict) -> List[tuple]:
        """Detect SINR degradation trends - predictive failover trigger"""
        events = []
        sinr = cell_data.get("sinr")
        if sinr is None:
            return events

        # Update SINR history
        self._cell_state.sinr_history.append(sinr)
        if len(self._cell_state.sinr_history) > self._cell_state.sinr_history_max:
            self._cell_state.sinr_history.pop(0)

        history = self._cell_state.sinr_history
        if len(history) < 3:
            return events

        # Check for rapid SINR drop (30% in window)
        window_size = min(
            len(history),
            int(self.config.sinr_drop_window_s / self.config.poll_interval_s),
        )
        if window_size >= 2:
            recent = history[-window_size:]
            peak = max(recent)
            current = recent[-1]

            if peak > 0 and current < peak * (1 - self.config.sinr_drop_threshold_percent / 100):
                events.append(
                    (
                        NetworkEvent.SINR_DROP,
                        {
                            "peak_sinr": round(peak, 1),
                            "current_sinr": round(current, 1),
                            "drop_percent": round((1 - current / peak) * 100, 1),
                        },
                    )
                )
                logger.warning(
                    f"SINR degradation: {peak:.1f} → {current:.1f} dB " f"({(1 - current / peak) * 100:.0f}% drop)"
                )

        # Check for SINR recovery
        if len(history) >= 5:
            avg_recent = sum(history[-3:]) / 3
            avg_older = sum(history[-6:-3]) / 3 if len(history) >= 6 else avg_recent

            if avg_recent > avg_older * 1.2 and avg_recent > self.config.sinr_moderate:
                events.append(
                    (
                        NetworkEvent.SINR_RECOVERY,
                        {
                            "current_sinr": round(sinr, 1),
                        },
                    )
                )

        return events

    # ======================
    # Jitter Detection (Mejora Nº4)
    # ======================

    def _detect_jitter_events(self, latency_data: Dict) -> List[tuple]:
        """Detect jitter spikes that degrade video quality"""
        events = []
        jitter = latency_data.get("jitter", 0)

        if jitter > self.config.jitter_critical_ms and self._last_jitter_ms <= self.config.jitter_critical_ms:
            events.append(
                (
                    NetworkEvent.HIGH_JITTER,
                    {
                        "jitter_ms": round(jitter, 1),
                        "severity": "critical",
                    },
                )
            )
        elif jitter > self.config.jitter_high_ms and self._last_jitter_ms <= self.config.jitter_high_ms:
            events.append(
                (
                    NetworkEvent.HIGH_JITTER,
                    {
                        "jitter_ms": round(jitter, 1),
                        "severity": "high",
                    },
                )
            )
        elif jitter < self.config.jitter_recovery_ms and self._last_jitter_ms >= self.config.jitter_high_ms:
            events.append(
                (
                    NetworkEvent.JITTER_RECOVERY,
                    {
                        "jitter_ms": round(jitter, 1),
                    },
                )
            )

        self._last_jitter_ms = jitter
        return events

    def _detect_rtt_events(self, latency_data: Dict) -> List[tuple]:
        """Detect RTT spikes"""
        events = []
        rtt = latency_data.get("avg_rtt", 0)

        if rtt > self.config.rtt_high_ms and self._last_rtt_ms <= self.config.rtt_high_ms:
            events.append(
                (
                    NetworkEvent.HIGH_RTT,
                    {
                        "rtt_ms": round(rtt, 1),
                        "critical": rtt > self.config.rtt_critical_ms,
                    },
                )
            )
        elif rtt < self.config.rtt_recovery_ms and self._last_rtt_ms >= self.config.rtt_high_ms:
            events.append((NetworkEvent.RTT_RECOVERY, {"rtt_ms": round(rtt, 1)}))

        self._last_rtt_ms = rtt
        return events

    def _detect_packet_loss_events(self, latency_data: Dict) -> List[tuple]:
        """Detect packet loss events"""
        events = []
        loss = latency_data.get("packet_loss", 0)

        if loss > self.config.packet_loss_high and self._last_packet_loss <= self.config.packet_loss_high:
            events.append(
                (
                    NetworkEvent.PACKET_LOSS,
                    {
                        "loss_percent": round(loss, 1),
                        "severity": "critical" if loss > self.config.packet_loss_critical else "high",
                    },
                )
            )
        elif loss < self.config.packet_loss_moderate and self._last_packet_loss >= self.config.packet_loss_high:
            events.append(
                (
                    NetworkEvent.PACKET_LOSS_RECOVERY,
                    {
                        "loss_percent": round(loss, 1),
                    },
                )
            )

        self._last_packet_loss = loss
        return events

    # ======================
    # Composite Quality Score (Mejora Nº7)
    # ======================

    def _update_quality_score(self, cell_data: Optional[Dict], latency_data: Optional[Dict]):
        """
        Calculate composite quality score from metrics of the PRIMARY interface only.

        - Modem mode: uses SINR + RSRQ + jitter + packet_loss (4 components)
        - WiFi/Ethernet mode: uses ONLY jitter + packet_loss + RTT (no SINR/RSRQ)

        Score is 0-100, where 100 = perfect conditions.
        """
        components = {}
        is_modem = self._primary_type == "modem"

        if is_modem and cell_data:
            # SINR component (0-100)
            sinr = cell_data.get("sinr")
            if sinr is not None:
                sinr_norm = max(0, min(100, (sinr + 5) * 100 / 30))
                components["sinr"] = sinr_norm
            else:
                components["sinr"] = 50

            # RSRQ component (0-100)
            rsrq = cell_data.get("rsrq")
            if rsrq is not None:
                rsrq_norm = max(0, min(100, (rsrq + 20) * 100 / 17))
                components["rsrq"] = rsrq_norm
            else:
                components["rsrq"] = 50
        else:
            # WiFi/Ethernet: no cellular metrics, mark as N/A
            components["sinr"] = 0
            components["rsrq"] = 0

        # Jitter component (0-100, inverse)
        jitter = latency_data.get("jitter", 0) if latency_data else 0
        jitter_norm = max(0, min(100, 100 - jitter))
        components["jitter"] = jitter_norm

        # Packet loss component (0-100, inverse)
        loss = latency_data.get("packet_loss", 0) if latency_data else 0
        loss_norm = max(0, min(100, 100 - loss * 5))
        components["packet_loss"] = loss_norm

        # RTT component for WiFi/Ethernet (0-100, inverse)
        rtt = latency_data.get("avg_rtt", 0) if latency_data else 0
        rtt_norm = max(0, min(100, 100 - rtt / 4))  # 0ms=100, 400ms=0
        components["rtt"] = rtt_norm

        # Weighted composite score - different weights based on connection type
        if is_modem:
            if cell_data:
                # Modem with cell data: SINR(35%) + RSRQ(15%) + Jitter(30%) + PacketLoss(20%)
                raw_score = (
                    self.config.weight_sinr * components["sinr"]
                    + self.config.weight_rsrq * components["rsrq"]
                    + self.config.weight_jitter * components["jitter"]
                    + self.config.weight_packet_loss * components["packet_loss"]
                )
            else:
                # Modem but cell_data failed - use latency only if available, else keep previous
                if latency_data:
                    raw_score = (
                        0.35 * components["rtt"] + 0.40 * components["jitter"] + 0.25 * components["packet_loss"]
                    )
                else:
                    # No data at all - keep previous score
                    return
        else:
            # WiFi/Ethernet: RTT(35%) + Jitter(40%) + PacketLoss(25%)
            if latency_data:
                raw_score = 0.35 * components["rtt"] + 0.40 * components["jitter"] + 0.25 * components["packet_loss"]
            else:
                # No latency data - keep previous score
                return

        # Apply EMA smoothing
        old_score = self._quality_score.score
        new_score = self.config.score_smoothing * raw_score + (1 - self.config.score_smoothing) * old_score

        # Determine trend
        if new_score > old_score + 3:
            trend = "improving"
        elif new_score < old_score - 3:
            trend = "degrading"
        else:
            trend = "stable"

        # Map score to recommendations
        recommended_bitrate = int(
            self.config.min_bitrate_kbps
            + (self.config.max_bitrate_kbps - self.config.min_bitrate_kbps)
            * (new_score / 100) ** 1.5  # Power curve for more aggressive low-end reduction
        )

        if new_score >= 80:
            label = "Excelente"
            resolution = "1920x1080"
            framerate = 30
        elif new_score >= 60:
            label = "Bueno"
            resolution = "1280x720"
            framerate = 30
        elif new_score >= 40:
            label = "Moderado"
            resolution = "854x480"
            framerate = 25
        elif new_score >= 20:
            label = "Bajo"
            resolution = "640x360"
            framerate = 20
        else:
            label = "Crítico"
            resolution = "320x240"
            framerate = 15

        # Update score
        self._quality_score = NetworkQualityScore(
            score=round(new_score, 1),
            sinr_component=round(components["sinr"], 1),
            rsrq_component=round(components["rsrq"], 1),
            jitter_component=round(components["jitter"], 1),
            packet_loss_component=round(components["packet_loss"], 1),
            recommended_bitrate_kbps=recommended_bitrate,
            recommended_resolution=resolution,
            recommended_framerate=framerate,
            quality_label=label,
            trend=trend,
        )

    # ======================
    # Event Handling → Video Actions (Mejora Nº8)
    # ======================

    async def _handle_event(self, event_type: NetworkEvent, details: Dict):
        """
        Handle a network event by triggering appropriate video actions.

        Event → Action mapping:
        ┌─────────────────────┬────────────────────────────────────┐
        │ Network Event       │ Video Action                       │
        ├─────────────────────┼────────────────────────────────────┤
        │ Cell change         │ force_keyframe + reduce bitrate 20%│
        │ Band change         │ force_keyframe + recalibrate       │
        │ SINR drop           │ reduce bitrate proactively         │
        │ High jitter         │ increase keyframe rate             │
        │ RTT > 200ms         │ reduce framerate                   │
        │ Packet loss > 5%    │ reduce resolution                  │
        │ Recovery events     │ gradually restore parameters       │
        └─────────────────────┴────────────────────────────────────┘
        """
        actions_taken = []
        now = time.time()

        if event_type == NetworkEvent.CELL_CHANGE:
            # Cell handover: force keyframe + temporary bitrate reduction
            if now - self._last_cell_change_time > 5:  # Cooldown 5s
                await asyncio.sleep(self.config.cell_change_keyframe_delay_ms / 1000)
                self._force_keyframe()
                actions_taken.append(VideoAction.FORCE_KEYFRAME)
                self._last_cell_change_time = now
                logger.info("Cell change → forced keyframe")

        elif event_type == NetworkEvent.BAND_CHANGE:
            # Band change: force keyframe + recalibrate
            self._force_keyframe()
            actions_taken.append(VideoAction.FORCE_KEYFRAME)
            logger.info("Band change → forced keyframe")

        elif event_type == NetworkEvent.SINR_DROP:
            # Predictive: SINR dropping fast → reduce bitrate before it gets worse
            drop_pct = details.get("drop_percent", 0)
            if drop_pct > 50:
                # Severe drop → aggressive reduction
                self._adjust_bitrate_percent(-30)
                actions_taken.append(VideoAction.REDUCE_BITRATE)
            elif drop_pct > 30:
                self._adjust_bitrate_percent(-20)
                actions_taken.append(VideoAction.REDUCE_BITRATE)
            logger.info(f"SINR drop {drop_pct:.0f}% → bitrate reduced")

        elif event_type == NetworkEvent.HIGH_JITTER:
            severity = details.get("severity", "high")
            if severity == "critical":
                self._set_keyframe_interval(0.5)
                self._adjust_bitrate_percent(-25)
                actions_taken.extend(
                    [
                        VideoAction.INCREASE_KEYFRAME_RATE,
                        VideoAction.REDUCE_BITRATE,
                    ]
                )
            else:
                self._set_keyframe_interval(1.0)
                actions_taken.append(VideoAction.INCREASE_KEYFRAME_RATE)
            logger.info(f"High jitter ({severity}) → increased keyframe rate")

        elif event_type == NetworkEvent.JITTER_RECOVERY:
            self._set_keyframe_interval(2.0)
            actions_taken.append(VideoAction.RESTORE_KEYFRAME_RATE)

        elif event_type == NetworkEvent.HIGH_RTT:
            if details.get("critical"):
                self._set_target_framerate(15)
            else:
                self._set_target_framerate(20)
            actions_taken.append(VideoAction.REDUCE_FRAMERATE)
            logger.info("High RTT → reduced framerate")

        elif event_type == NetworkEvent.RTT_RECOVERY:
            self._set_target_framerate(30)
            actions_taken.append(VideoAction.RESTORE_FRAMERATE)

        elif event_type == NetworkEvent.PACKET_LOSS:
            severity = details.get("severity", "high")
            if severity == "critical":
                self._adjust_bitrate_percent(-40)
                self._set_keyframe_interval(0.5)
                actions_taken.extend(
                    [
                        VideoAction.REDUCE_BITRATE,
                        VideoAction.INCREASE_KEYFRAME_RATE,
                    ]
                )
            else:
                self._adjust_bitrate_percent(-20)
                actions_taken.append(VideoAction.REDUCE_BITRATE)
            logger.info(f"Packet loss ({severity}) → bitrate/keyframe adjusted")

        elif event_type == NetworkEvent.PACKET_LOSS_RECOVERY:
            self._set_keyframe_interval(2.0)
            actions_taken.append(VideoAction.RESTORE_KEYFRAME_RATE)

        elif event_type == NetworkEvent.DISCONNECTION:
            logger.warning("Network disconnection detected")

        elif event_type == NetworkEvent.RECONNECTION:
            self._force_keyframe()
            actions_taken.append(VideoAction.FORCE_KEYFRAME)
            logger.info("Reconnection → forced keyframe")

        # Record event
        bridge_event = BridgeEvent(
            timestamp=now,
            event=event_type,
            details=details,
            actions_taken=actions_taken,
        )
        self._events.append(bridge_event)
        if len(self._events) > self._events_max:
            self._events.pop(0)

    # ======================
    # Smooth Adaptive Bitrate (Mejora Nº7)
    # ======================

    async def _apply_adaptive_bitrate(self):
        """Apply smooth bitrate adaptation based on composite quality score.

        Supports both H.264 (adjusts bitrate) and MJPEG (adjusts quality).
        """
        # Check if auto-adaptive bitrate is enabled in preferences
        try:
            prefs = get_preferences()
            if not prefs.get_auto_adaptive_bitrate():
                return  # User disabled auto-adaptation
        except Exception:
            pass  # If can't get preferences, continue with adaptation

        if not self._gstreamer_service or not self._gstreamer_service.is_streaming:
            return

        now = time.time()
        # Rate-limit changes
        if now - self._last_bitrate_change_time < self.config.poll_interval_s:
            return

        current_config = self._gstreamer_service.video_config
        codec = (current_config.codec or "mjpeg").lower()
        score = self._quality_score.score

        try:
            # ── MJPEG: adapt quality instead of bitrate ──
            if codec == "mjpeg":
                current_quality = getattr(current_config, "quality", 85) or 85
                # Map score (0-100) → quality (30-95)
                # score 100 → quality 95, score 0 → quality 30
                target_quality = int(30 + (score / 100) * 65)
                target_quality = max(30, min(95, target_quality))

                diff = target_quality - current_quality
                if abs(diff) < 3:
                    return  # Too small to bother

                # Limit change rate: max 10 units per step
                max_change = 10
                new_quality = current_quality + max(-max_change, min(max_change, diff))
                new_quality = max(30, min(95, new_quality))

                result = self._gstreamer_service.update_live_property("quality", new_quality)
                if result.get("success"):
                    self._last_bitrate_change_time = now
                    if self._websocket_manager:
                        try:
                            await self._websocket_manager.broadcast(
                                "bitrate_changed",
                                {
                                    "codec": "mjpeg",
                                    "old_quality": current_quality,
                                    "new_quality": new_quality,
                                    "quality_score": score,
                                    "quality_label": self._quality_score.quality_label,
                                    "timestamp": now,
                                },
                            )
                        except Exception:
                            pass
                return

            # ── H.264 family: adapt bitrate ──
            target_bitrate = self._quality_score.recommended_bitrate_kbps
            current_bitrate = getattr(current_config, "h264_bitrate", 1500) or 1500

            # Limit change rate
            max_change = int(current_bitrate * self.config.bitrate_change_rate)
            diff = target_bitrate - current_bitrate

            if abs(diff) < 50:
                return  # Too small to bother

            new_bitrate = current_bitrate + max(-max_change, min(max_change, diff))
            new_bitrate = max(self.config.min_bitrate_kbps, min(self.config.max_bitrate_kbps, new_bitrate))

            # Apply via live property update
            result = self._gstreamer_service.update_live_property("bitrate", new_bitrate)
            if result.get("success"):
                self._last_bitrate_change_time = now

                # Broadcast bitrate change notification via WebSocket
                if self._websocket_manager:
                    try:
                        await self._websocket_manager.broadcast(
                            "bitrate_changed",
                            {
                                "codec": codec,
                                "old_bitrate": current_bitrate,
                                "new_bitrate": new_bitrate,
                                "quality_score": score,
                                "quality_label": self._quality_score.quality_label,
                                "timestamp": now,
                            },
                        )
                    except Exception:
                        pass  # Don't fail if broadcast fails

        except Exception:
            pass  # logger.debug(f"Adaptive bitrate error: {e}")

    # ======================
    # Adaptive Resolution (4.8)
    # ======================

    async def _apply_adaptive_resolution(self):
        """Downscale resolution when quality_score stays below threshold.

        Rules:
        * Score < ``_adaptive_res_threshold`` for > ``_adaptive_res_hold_s``
          → stop pipeline, reconfigure with recommended resolution, restart.
        * Score recovers above threshold+15 for > hold time
          → restore original resolution.
        * Minimum ``_adaptive_res_cooldown_s`` between changes to avoid flapping.
        """
        # Check if auto-adaptive resolution is enabled
        try:
            prefs = get_preferences()
            if not prefs.get_auto_adaptive_resolution():
                return
        except Exception:
            pass

        if not self._gstreamer_service or not self._gstreamer_service.is_streaming:
            return

        now = time.time()
        score = self._quality_score.score

        # Respect cooldown
        if (now - self._last_resolution_change_time) < self._adaptive_res_cooldown_s:
            return

        # --- Downscale path ---
        if score < self._adaptive_res_threshold:
            if self._low_score_since == 0:
                self._low_score_since = now
                return  # start counting

            elapsed_low = now - self._low_score_since
            if elapsed_low < self._adaptive_res_hold_s:
                return  # not yet sustained

            # Score has been critically low long enough — downscale
            rec_res = self._quality_score.recommended_resolution  # e.g. "640x360"
            rec_fps = self._quality_score.recommended_framerate
            try:
                new_w, new_h = (int(x) for x in rec_res.split("x"))
            except Exception:
                return

            cfg = self._gstreamer_service.video_config
            cur_w, cur_h = cfg.width, cfg.height

            if new_w >= cur_w and new_h >= cur_h:
                return  # already at or below recommended

            # Save current resolution for later restore
            if self._pre_downscale_resolution is None:
                self._pre_downscale_resolution = (cur_w, cur_h)

            logger.warning(
                f"[AdaptiveRes] Score {score:.0f} < {self._adaptive_res_threshold} "
                f"for {elapsed_low:.0f}s → downscaling {cur_w}x{cur_h} → {new_w}x{new_h} @ {rec_fps}fps"
            )

            self._gstreamer_service.configure(video_config={"width": new_w, "height": new_h, "framerate": rec_fps})
            self._gstreamer_service.restart()
            self._last_resolution_change_time = now
            self._low_score_since = 0

            if self._websocket_manager:
                try:
                    await self._websocket_manager.broadcast(
                        "resolution_changed",
                        {
                            "old_resolution": f"{cur_w}x{cur_h}",
                            "new_resolution": f"{new_w}x{new_h}",
                            "framerate": rec_fps,
                            "quality_score": score,
                            "reason": "adaptive_downscale",
                        },
                    )
                except Exception:
                    pass
        else:
            self._low_score_since = 0  # reset counter

            # --- Restore path ---
            if self._pre_downscale_resolution and score > (self._adaptive_res_threshold + 15):
                orig_w, orig_h = self._pre_downscale_resolution
                cfg = self._gstreamer_service.video_config
                if cfg.width < orig_w or cfg.height < orig_h:
                    logger.info(
                        f"[AdaptiveRes] Score recovered to {score:.0f} — "
                        f"restoring {cfg.width}x{cfg.height} → {orig_w}x{orig_h}"
                    )
                    self._gstreamer_service.configure(video_config={"width": orig_w, "height": orig_h, "framerate": 30})
                    self._gstreamer_service.restart()
                    self._last_resolution_change_time = now

                    if self._websocket_manager:
                        try:
                            await self._websocket_manager.broadcast(
                                "resolution_changed",
                                {
                                    "old_resolution": f"{cfg.width}x{cfg.height}",
                                    "new_resolution": f"{orig_w}x{orig_h}",
                                    "framerate": 30,
                                    "quality_score": score,
                                    "reason": "adaptive_restore",
                                },
                            )
                        except Exception:
                            pass

                self._pre_downscale_resolution = None

    # ======================
    # Video Action Helpers
    # ======================

    def _force_keyframe(self):
        """Force an IDR keyframe from GStreamer encoder"""
        now = time.time()
        if now - self._last_keyframe_time < 0.5:  # Max 2 keyframes/sec
            return

        if self._gstreamer_service and self._gstreamer_service.is_streaming:
            self._gstreamer_service.force_keyframe()
            self._last_keyframe_time = now

    def _adjust_bitrate_percent(self, percent: float):
        """Adjust bitrate by percentage (negative = reduce)"""
        if not self._gstreamer_service or not self._gstreamer_service.is_streaming:
            return

        try:
            current = getattr(self._gstreamer_service.video_config, "h264_bitrate", 1500) or 1500
            new_bitrate = int(current * (1 + percent / 100))
            new_bitrate = max(self.config.min_bitrate_kbps, min(self.config.max_bitrate_kbps, new_bitrate))
            self._gstreamer_service.update_live_property("bitrate", new_bitrate)
        except Exception:
            pass  # logger.debug(f"Bitrate adjustment error: {e}")

    def _set_keyframe_interval(self, interval_s: float):
        """Set WebRTC keyframe interval"""
        if self._webrtc_service:
            self._webrtc_service._adaptive_gop_interval = interval_s
            self._webrtc_service.adaptive_config["keyframe_interval"] = interval_s

    def _set_target_framerate(self, fps: int):
        """Set target framerate (advisory - WebRTC service uses this)"""
        if self._webrtc_service:
            self._webrtc_service.adaptive_config["target_framerate"] = fps

    # ======================
    # Status & History
    # ======================

    async def _broadcast_status(self):
        """Broadcast bridge status via WebSocket"""
        if not self._websocket_manager:
            return

        try:
            status = self.get_status()

            # Debug logs comentados para reducir verbosidad
            # if status.get("cell_state", {}).get("sinr") is not None:
            #     logger.debug(
            #         f"Broadcasting: SINR={status['cell_state']['sinr']}dB, "
            #         f"Score={status['quality_score']['score']:.1f}"
            #     )
            # else:
            #     logger.debug(f"Broadcasting: WiFi only, Jitter={status['latency']['jitter_ms']}ms")

            await self._websocket_manager.broadcast("network_quality", status)
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")

    def get_status(self) -> Dict:
        """Get current bridge status"""
        is_modem = self._primary_type == "modem"
        return {
            "active": self._monitoring,
            "primary_interface": self._primary_interface,
            "primary_type": self._primary_type,  # "modem", "wifi", "ethernet", "unknown"
            "quality_score": {
                "score": self._quality_score.score,
                "label": self._quality_score.quality_label,
                "trend": self._quality_score.trend,
                "components": {
                    "sinr": self._quality_score.sinr_component if is_modem else None,
                    "rsrq": self._quality_score.rsrq_component if is_modem else None,
                    "jitter": self._quality_score.jitter_component,
                    "packet_loss": self._quality_score.packet_loss_component,
                },
                "recommended": {
                    "bitrate_kbps": self._quality_score.recommended_bitrate_kbps,
                    "resolution": self._quality_score.recommended_resolution,
                    "framerate": self._quality_score.recommended_framerate,
                },
            },
            "cell_state": {
                "cell_id": self._cell_state.cell_id if is_modem else None,
                "pci": self._cell_state.pci if is_modem else None,
                "band": self._cell_state.band if is_modem else None,
                "sinr": self._cell_state.sinr if is_modem else None,
                "rsrp": self._cell_state.rsrp if is_modem else None,
                "rsrq": self._cell_state.rsrq if is_modem else None,
                "network_type": self._cell_state.network_type if is_modem else None,
                "operator": self._cell_state.operator if is_modem else None,
            },
            "latency": {
                "rtt_ms": round(self._last_rtt_ms, 1),
                "jitter_ms": round(self._last_jitter_ms, 1),
                "packet_loss": round(self._last_packet_loss, 1),
            },
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "event": e.event.value,
                    "details": e.details,
                    "actions": [a.value for a in e.actions_taken],
                }
                for e in self._events[-20:]
            ],
            "events_total": len(self._events),
        }

    def get_event_history(self, last_n: int = 100) -> List[Dict]:
        """Get event history"""
        return [
            {
                "timestamp": e.timestamp,
                "event": e.event.value,
                "details": e.details,
                "actions": [a.value for a in e.actions_taken],
            }
            for e in self._events[-last_n:]
        ]

    def clear_events(self):
        """Clear event history (useful when changing network mode)"""
        self._events.clear()
        logger.info("Event history cleared")


# ======================
# Global Instance
# ======================

_event_bridge: Optional[NetworkEventBridge] = None


def get_network_event_bridge() -> NetworkEventBridge:
    """Get or create global network event bridge"""
    global _event_bridge
    if _event_bridge is None:
        _event_bridge = NetworkEventBridge()
    return _event_bridge
