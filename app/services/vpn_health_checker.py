"""
VPNHealthChecker — FASE 3

Verifies VPN connectivity before and after modem switches to ensure
the VPN tunnel never drops during network changes.

Supports:
  - Tailscale (preferred: uses `tailscale status --json` for peer discovery)
  - WireGuard (parses `wg show all` for peers)
  - OpenVPN (checks tun0/tun1 interface + gateway ping)

Integration in ModemPool.select_modem():
  1. PRE-SWITCH:  check_vpn_health()      → establish baseline
  2. POST-SWITCH: wait_for_vpn_recovery() → polling until tunnel recovered
  3. ROLLBACK:    if recovery fails, caller restores previous modem
"""

import asyncio
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_vpn_health_checker: Optional["VPNHealthChecker"] = None


def get_vpn_health_checker() -> "VPNHealthChecker":
    global _vpn_health_checker
    if _vpn_health_checker is None:
        _vpn_health_checker = VPNHealthChecker()
    return _vpn_health_checker


# ─────────────────────────────────────────────────────────────────────────────
# VPN type constants
# ─────────────────────────────────────────────────────────────────────────────

VPN_TYPE_NONE = "none"
VPN_TYPE_TAILSCALE = "tailscale"
VPN_TYPE_WIREGUARD = "wireguard"
VPN_TYPE_OPENVPN = "openvpn"
VPN_TYPE_UNKNOWN = "unknown"

# How long to wait between individual recovery polls (seconds)
POLL_INTERVAL = 1.0

# Ping timeout per attempt (seconds)
PING_TIMEOUT = 2

# Max ping RTT considered healthy (ms) — above this is "degraded but alive"
HEALTHY_RTT_MS = 500


# ─────────────────────────────────────────────────────────────────────────────
# VPNHealthChecker
# ─────────────────────────────────────────────────────────────────────────────


class VPNHealthChecker:
    """
    Singleton that checks VPN health before/after modem switches.

    State:
      _vpn_type       — detected VPN type (lazy-detected on first call)
      _peer_ip        — cached VPN peer IP used for ping probes
      _last_check     — timestamp of last check_vpn_health() call
      _last_healthy   — True if last check was healthy
      _last_rtt_ms    — last measured RTT to peer (or None)
    """

    def __init__(self):
        self._vpn_type: str = VPN_TYPE_UNKNOWN
        self._peer_ip: Optional[str] = None
        self._last_check: float = 0.0
        self._last_healthy: bool = False
        self._last_rtt_ms: Optional[float] = None
        self._initialized: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """
        Detect installed VPN type and locate a usable peer IP.
        Idempotent — safe to call multiple times.
        Returns True if a supported VPN was detected and we have a peer IP.
        """
        vpn_type = await self._detect_vpn_type()
        self._vpn_type = vpn_type

        if vpn_type == VPN_TYPE_NONE:
            logger.info("VPNHealthChecker: no VPN detected — health checks disabled")
            self._initialized = True
            return False

        peer_ip = await self._get_peer_ip(vpn_type)
        self._peer_ip = peer_ip

        if peer_ip:
            logger.info(f"VPNHealthChecker: initialized — type={vpn_type}, peer={peer_ip}")
        else:
            logger.warning(
                f"VPNHealthChecker: detected {vpn_type} but no reachable peer found — "
                f"health checks will use interface-only verification"
            )

        self._initialized = True
        return vpn_type != VPN_TYPE_NONE

    async def check_vpn_health(self) -> Dict:
        """
        Full VPN health check: interface UP + optional peer ping.

        Returns dict:
          {
            "healthy": bool,
            "vpn_type": str,
            "peer_ip": str | None,
            "rtt_ms": float | None,
            "interface_up": bool,
            "message": str,
          }
        """
        if not self._initialized:
            await self.initialize()

        if self._vpn_type == VPN_TYPE_NONE:
            return {
                "healthy": True,  # No VPN = no VPN problem
                "vpn_type": VPN_TYPE_NONE,
                "peer_ip": None,
                "rtt_ms": None,
                "interface_up": False,
                "message": "No VPN configured",
            }

        # 1. Check interface is UP
        interface_up = await self._check_interface_up(self._vpn_type)

        # 2. Ping peer (if we have one)
        rtt_ms: Optional[float] = None
        ping_ok = False
        if self._peer_ip and interface_up:
            rtt_ms = await self._ping(self._peer_ip)
            ping_ok = rtt_ms is not None
        elif interface_up:
            # No peer IP but interface is up — treat as healthy
            ping_ok = True

        healthy = interface_up and ping_ok

        self._last_check = time.time()
        self._last_healthy = healthy
        self._last_rtt_ms = rtt_ms

        message = self._build_message(healthy, interface_up, ping_ok, rtt_ms)
        logger.debug(f"VPNHealthChecker: {message}")

        return {
            "healthy": healthy,
            "vpn_type": self._vpn_type,
            "peer_ip": self._peer_ip,
            "rtt_ms": round(rtt_ms, 1) if rtt_ms is not None else None,
            "interface_up": interface_up,
            "message": message,
        }

    async def wait_for_vpn_recovery(self, timeout_s: float = 15.0) -> bool:
        """
        Poll VPN health until recovered or timeout expires.
        Used POST-SWITCH: modem routing has just changed and VPN needs to re-establish.

        Returns True as soon as VPN is healthy, False if timeout reached.
        """
        if not self._initialized:
            await self.initialize()

        if self._vpn_type == VPN_TYPE_NONE:
            return True  # Nothing to wait for

        deadline = time.monotonic() + timeout_s
        attempt = 0

        while time.monotonic() < deadline:
            attempt += 1
            result = await self.check_vpn_health()
            if result["healthy"]:
                elapsed = timeout_s - (deadline - time.monotonic())
                logger.info(
                    f"VPNHealthChecker: VPN recovered after {elapsed:.1f}s "
                    f"(attempt #{attempt})" + (f", RTT={result['rtt_ms']}ms" if result["rtt_ms"] else "")
                )
                return True

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            logger.debug(
                f"VPNHealthChecker: recovery poll #{attempt} — " f"not yet healthy, {remaining:.1f}s remaining"
            )
            await asyncio.sleep(POLL_INTERVAL)

        logger.warning(
            f"VPNHealthChecker: VPN did NOT recover within {timeout_s}s " f"({attempt} attempts) — rollback recommended"
        )
        return False

    async def get_peer_ip(self) -> Optional[str]:
        """Return the cached peer IP, refreshing if not yet set."""
        if not self._peer_ip and self._initialized:
            self._peer_ip = await self._get_peer_ip(self._vpn_type)
        return self._peer_ip

    def get_status(self) -> Dict:
        """Synchronous status snapshot — no I/O."""
        return {
            "initialized": self._initialized,
            "vpn_type": self._vpn_type,
            "peer_ip": self._peer_ip,
            "last_healthy": self._last_healthy,
            "last_rtt_ms": round(self._last_rtt_ms, 1) if self._last_rtt_ms else None,
            "last_check": self._last_check,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Detection helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _detect_vpn_type(self) -> str:
        """Detect which VPN is installed and running. Priority: Tailscale > WireGuard > OpenVPN."""
        from app.api.routes.network.common import run_command

        # Tailscale: check binary + daemon running
        _, _, rc = await run_command(["which", "tailscale"])
        if rc == 0:
            stdout, _, rc2 = await run_command(["tailscale", "status"], timeout=3)
            if rc2 == 0 and "Tailscale" not in stdout.split("\n")[0] if stdout else True:
                # Daemon is up (exit 0 even if not connected)
                return VPN_TYPE_TAILSCALE

        # WireGuard: check wg command
        _, _, rc = await run_command(["which", "wg"])
        if rc == 0:
            stdout, _, rc2 = await run_command(["sudo", "wg", "show", "all"])
            if rc2 == 0 and stdout.strip():
                return VPN_TYPE_WIREGUARD

        # OpenVPN: check for tun interface
        stdout, _, rc = await run_command(["ip", "link", "show"])
        if rc == 0:
            for line in stdout.splitlines():
                if "tun" in line and "UP" in line:
                    return VPN_TYPE_OPENVPN

        return VPN_TYPE_NONE

    async def _get_peer_ip(self, vpn_type: str) -> Optional[str]:
        """Find the best peer IP to use for health pings."""
        try:
            if vpn_type == VPN_TYPE_TAILSCALE:
                return await self._get_tailscale_peer()
            elif vpn_type == VPN_TYPE_WIREGUARD:
                return await self._get_wireguard_peer()
            elif vpn_type == VPN_TYPE_OPENVPN:
                return await self._get_openvpn_gateway()
        except Exception as e:
            logger.debug(f"VPNHealthChecker: peer discovery error: {e}")
        return None

    async def _get_tailscale_peer(self) -> Optional[str]:
        """Get first online Tailscale peer IP via `tailscale status --json`."""
        import json
        from app.api.routes.network.common import run_command

        stdout, _, rc = await run_command(["tailscale", "status", "--json"], timeout=5)
        if rc != 0 or not stdout:
            return None

        try:
            data = json.loads(stdout)
            peers = data.get("Peer", {}) or {}
            for peer in peers.values():
                if peer.get("Online", False):
                    ips = peer.get("TailscaleIPs", [])
                    if ips:
                        return ips[0]
            # No online peer — try any peer with an IP
            for peer in peers.values():
                ips = peer.get("TailscaleIPs", [])
                if ips:
                    return ips[0]
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    async def _get_wireguard_peer(self) -> Optional[str]:
        """Extract an endpoint IP from `wg show all`."""
        from app.api.routes.network.common import run_command

        stdout, _, rc = await run_command(["sudo", "wg", "show", "all"])
        if rc != 0 or not stdout:
            return None

        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("endpoint"):
                # Format: "endpoint   1.2.3.4:51820"
                parts = line.split()
                if len(parts) >= 2:
                    host_port = parts[-1]
                    ip = host_port.rsplit(":", 1)[0].strip("[]")
                    if ip:
                        return ip
            elif line.startswith("allowed ips"):
                # Fallback: grab first non-0.0.0.0 allowed IP
                parts = line.split(":", 1)
                if len(parts) == 2:
                    for cidr in parts[1].split(","):
                        ip = cidr.strip().split("/")[0]
                        if ip and ip != "0.0.0.0":
                            return ip
        return None

    async def _get_openvpn_gateway(self) -> Optional[str]:
        """Get the remote gateway for a tun interface."""
        from app.api.routes.network.common import run_command

        stdout, _, rc = await run_command(["ip", "-o", "addr", "show"])
        if rc != 0:
            return None

        # Find tun interface
        for line in stdout.splitlines():
            if "tun" in line and "inet" in line:
                # Parse P-t-P address: inet addr/peer
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "inet" and i + 1 < len(parts):
                        # Could be "10.8.0.2 peer 10.8.0.1/32" or just "10.8.0.2/24"
                        # Get the peer/gateway
                        if "peer" in parts:
                            peer_idx = parts.index("peer")
                            if peer_idx + 1 < len(parts):
                                peer = parts[peer_idx + 1].split("/")[0]
                                return peer
                        # Fallback: use gateway from routing table
                        iface = parts[1].rstrip(":")
                        gw_stdout, _, _ = await run_command(["ip", "route", "show", "dev", iface])
                        for route_line in gw_stdout.splitlines():
                            if "via" in route_line:
                                r_parts = route_line.split()
                                via_idx = r_parts.index("via")
                                if via_idx + 1 < len(r_parts):
                                    return r_parts[via_idx + 1]
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Interface health
    # ─────────────────────────────────────────────────────────────────────────

    async def _check_interface_up(self, vpn_type: str) -> bool:
        """Return True if the VPN interface is present and UP."""
        from app.api.routes.network.common import run_command

        interface_patterns = {
            VPN_TYPE_TAILSCALE: ["tailscale", "tailscale0", "tailscale1"],
            VPN_TYPE_WIREGUARD: ["wg0", "wg1", "wireguard"],
            VPN_TYPE_OPENVPN: ["tun0", "tun1"],
        }
        patterns = interface_patterns.get(vpn_type, [])

        stdout, _, rc = await run_command(["ip", "link", "show"])
        if rc != 0:
            return False

        for line in stdout.splitlines():
            for pat in patterns:
                if pat in line and ("UP" in line or "UNKNOWN" in line):
                    # UNKNOWN state is normal for Tailscale when connected
                    return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Ping helper
    # ─────────────────────────────────────────────────────────────────────────

    async def _ping(self, target: str, count: int = 1) -> Optional[float]:
        """
        Ping target IP and return RTT in milliseconds, or None if unreachable.
        Uses system ping to stay within sudoers — no extra permissions needed.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                str(count),
                "-W",
                str(PING_TIMEOUT),
                "-q",
                target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=PING_TIMEOUT * count + 2)
            if proc.returncode != 0:
                return None

            stdout = stdout_bytes.decode()
            # Parse: "rtt min/avg/max/mdev = 12.345/12.345/12.345/0.000 ms"
            for line in stdout.splitlines():
                if "rtt" in line and "avg" in line:
                    parts = line.split("=")
                    if len(parts) == 2:
                        values = parts[1].strip().split("/")
                        if len(values) >= 2:
                            return float(values[1])  # avg RTT
        except (asyncio.TimeoutError, Exception):
            pass
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Message builder
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_message(
        healthy: bool,
        interface_up: bool,
        ping_ok: bool,
        rtt_ms: Optional[float],
    ) -> str:
        if not interface_up:
            return "VPN interface is DOWN"
        if not ping_ok:
            return "VPN interface UP but peer unreachable"
        if rtt_ms is not None and rtt_ms > HEALTHY_RTT_MS:
            return f"VPN degraded — RTT {rtt_ms:.0f}ms (>{HEALTHY_RTT_MS}ms threshold)"
        if rtt_ms is not None:
            return f"VPN healthy — RTT {rtt_ms:.0f}ms"
        return "VPN healthy (no peer ping)"
