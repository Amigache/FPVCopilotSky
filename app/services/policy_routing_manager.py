"""
PolicyRoutingManager — FASE 2

Implements Linux policy routing to isolate critical traffic
into dedicated routing tables, ensuring:
 - VPN never disconnects during modem switches
 - Video always uses the best modem
 - MAVLink follows video routing (low-latency guaranteed)

Architecture:
  iptables mangle (mark packets)
      → ip rule (fwmark → table)
          → ip route table 100 (VPN)
          → ip route table 200 (Video + MAVLink)

Traffic marks (fwmark):
  VPN     → 0x100  → table 100
  Video   → 0x200  → table 200
  MAVLink → 0x300  → table 200  (follows video)
"""

import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

TABLE_VPN = 100  # Routing table for VPN control traffic
TABLE_VIDEO = 200  # Routing table for video + MAVLink traffic
TABLE_MODEM_BASE = 201  # Per-modem tables start here (201, 202, …)

MARK_VPN = "0x100"
MARK_VIDEO = "0x200"
MARK_MAVLINK = "0x300"

# Policy rule priorities (lower = higher priority, must not conflict with system)
PRIO_VPN = 100
PRIO_VIDEO = 200
PRIO_MAVLINK = 300

# Traffic classes: (name, fwmark, table_id, description, ports)
TRAFFIC_CLASSES = [
    {
        "name": "vpn",
        "fwmark": MARK_VPN,
        "table_id": TABLE_VPN,
        "description": "VPN control traffic (Tailscale, WireGuard)",
        "proto": "udp",
        "dports": ["41641", "51820"],
        "priority": PRIO_VPN,
    },
    {
        "name": "video",
        "fwmark": MARK_VIDEO,
        "table_id": TABLE_VIDEO,
        "description": "Video streaming traffic (GStreamer UDP, RTSP)",
        "proto": "udp",
        "dports": [str(p) for p in range(5600, 5611)] + ["8554"],
        "priority": PRIO_VIDEO,
    },
    {
        "name": "video_tcp",
        "fwmark": MARK_VIDEO,
        "table_id": TABLE_VIDEO,
        "description": "Video streaming RTSP TCP",
        "proto": "tcp",
        "dports": ["8554"],
        "priority": PRIO_VIDEO,
    },
    {
        "name": "mavlink",
        "fwmark": MARK_MAVLINK,
        "table_id": TABLE_VIDEO,  # Shares table 200 with video
        "description": "MAVLink telemetry (follows video routing)",
        "proto": "udp",
        "dports": ["14550", "14551", "14552"],
        "priority": PRIO_MAVLINK,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# PolicyRoutingManager
# ─────────────────────────────────────────────────────────────────────────────


class PolicyRoutingManager:
    """
    Manages Linux policy routing for traffic isolation.

    Singleton — obtain via get_policy_routing_manager().
    """

    def __init__(self):
        self._initialized = False
        self._active_interface: Optional[str] = None
        self._active_gateway: Optional[str] = None
        # interface → table_id mapping (per-modem tables 201, 202, …)
        self._modem_tables: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        logger.info("PolicyRoutingManager created")

    # ──────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """
        Idempotent initialization:
          1. Add routing tables to /etc/iproute2/rt_tables (if missing)
          2. Install iptables mangle MARK rules
          3. Install ip rules (fwmark → table)
        Returns True if successful.
        """
        async with self._lock:
            try:
                await self._ensure_rt_tables()
                await self._setup_iptables_marks()
                await self._setup_ip_rules()
                self._initialized = True
                logger.info("PolicyRoutingManager initialized successfully")
                return True
            except Exception as e:
                logger.error(f"PolicyRoutingManager.initialize() failed: {e}")
                return False

    async def cleanup(self) -> bool:
        """Remove all iptables marks and ip rules created by this manager."""
        async with self._lock:
            try:
                await self._remove_ip_rules()
                await self._remove_iptables_marks()
                self._initialized = False
                logger.info("PolicyRoutingManager cleaned up")
                return True
            except Exception as e:
                logger.error(f"PolicyRoutingManager.cleanup() failed: {e}")
                return False

    # ──────────────────────────────────────────────────────────────────────
    # Core Public API
    # ──────────────────────────────────────────────────────────────────────

    async def update_active_modem(self, interface: str, gateway: str) -> bool:
        """
        Update routing tables 100 (VPN) and 200 (Video/MAVLink)
        to route through the specified modem interface/gateway.

        Also creates/updates per-modem table (201+) for the interface.
        Called by ModemPool._apply_modem_priority() on every modem switch.
        """
        if not self._initialized:
            logger.warning("PolicyRoutingManager not initialized, calling initialize() first")
            ok = await self.initialize()
            if not ok:
                return False

        async with self._lock:
            logger.info(f"PolicyRoutingManager: updating active modem → " f"{interface} via {gateway}")
            try:
                # Update shared tables (VPN + Video)
                await self._update_table_route(TABLE_VPN, interface, gateway)
                await self._update_table_route(TABLE_VIDEO, interface, gateway)

                # Ensure per-modem table exists
                table_id = await self._ensure_modem_table(interface, gateway)
                logger.info(
                    f"PolicyRoutingManager: tables updated — " f"VPN(100), Video(200), Modem({table_id}) via {gateway}"
                )

                self._active_interface = interface
                self._active_gateway = gateway
                return True
            except Exception as e:
                logger.error(f"PolicyRoutingManager.update_active_modem() failed: {e}")
                return False

    async def get_status(self) -> dict:
        """Return current status of policy routing."""
        rules = await self._get_ip_rules()
        table_routes = await self._get_all_table_routes()

        return {
            "initialized": self._initialized,
            "active_modem": (
                {
                    "interface": self._active_interface,
                    "gateway": self._active_gateway,
                }
                if self._active_interface
                else None
            ),
            "modem_tables": dict(self._modem_tables),
            "policy_rules": rules,
            "traffic_classes": [
                {
                    "name": tc["name"],
                    "fwmark": tc["fwmark"],
                    "table_id": tc["table_id"],
                    "description": tc["description"],
                }
                for tc in TRAFFIC_CLASSES
                if tc["name"] != "video_tcp"  # Collapse TCP/UDP video into one entry
            ],
            "tables": table_routes,
        }

    async def get_tables(self) -> dict:
        """Return routes in all managed routing tables."""
        return await self._get_all_table_routes()

    async def get_rules(self) -> List[str]:
        """Return current ip rules."""
        return await self._get_ip_rules()

    # ──────────────────────────────────────────────────────────────────────
    # Internal — rt_tables
    # ──────────────────────────────────────────────────────────────────────

    async def _ensure_rt_tables(self):
        """Register routing tables in /etc/iproute2/rt_tables if missing.
        Non-fatal: ip route works with numeric table IDs even without names.
        """
        entries = {
            TABLE_VPN: "fpv_vpn",
            TABLE_VIDEO: "fpv_video",
        }
        try:
            with open("/etc/iproute2/rt_tables", "r") as f:
                current = f.read()
        except Exception:
            return  # File not readable — skip silently, numeric IDs still work

        additions = []
        for table_id, name in entries.items():
            if str(table_id) not in current:
                additions.append(f"{table_id}\t{name}\n")

        if not additions:
            return  # Already present

        content = "".join(additions).encode()
        try:
            import subprocess

            loop = asyncio.get_event_loop()

            def _write_rt_tables():
                result = subprocess.run(
                    ["sudo", "tee", "-a", "/etc/iproute2/rt_tables"],
                    input=content,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=5,
                )
                return result.returncode, result.stderr.decode().strip()

            rc, err = await loop.run_in_executor(None, _write_rt_tables)
            if rc == 0:
                logger.info(f"PolicyRoutingManager: added rt_tables entries: {list(entries.values())}")
            else:
                # Read-only rootfs is common on embedded systems — not an error,
                # ip route/rule commands accept numeric table IDs without named entries.
                logger.debug(f"PolicyRoutingManager: rt_tables not writable (read-only rootfs, non-fatal): {err}")
        except Exception as e:
            logger.warning(f"PolicyRoutingManager: rt_tables write skipped: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # Internal — iptables mangle
    # ──────────────────────────────────────────────────────────────────────

    async def _setup_iptables_marks(self):
        """Install iptables mangle MARK rules for all traffic classes.

        Uses a single ``sudo iptables-restore --noflush`` call instead of one
        ``sudo iptables`` invocation per rule.  This reduces ~20 separate sudo
        sessions to 2 (remove stale + add new).
        """
        # First remove any stale FPV marks to ensure idempotency
        await self._remove_iptables_marks()

        # Build rules in iptables-restore format and apply atomically
        lines = ["*mangle"]
        for tc in TRAFFIC_CLASSES:
            proto = tc["proto"]
            fwmark = tc["fwmark"]
            for dport in tc["dports"]:
                lines.append(
                    f"-A OUTPUT -p {proto} --dport {dport} "
                    f"-j MARK --set-mark {fwmark} "
                    f"-m comment --comment fpv_{tc['name']}"
                )
        lines.append("COMMIT")
        rules_input = "\n".join(lines) + "\n"

        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "iptables-restore",
                "--noflush",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(rules_input.encode()), timeout=10)
            if proc.returncode != 0:
                logger.warning(f"PolicyRoutingManager: iptables-restore failed: {stderr.decode().strip()}")
            else:
                rule_count = sum(len(tc["dports"]) for tc in TRAFFIC_CLASSES)
                logger.info(f"PolicyRoutingManager: {rule_count} iptables mangle marks installed (1 sudo call)")
        except Exception as e:
            logger.error(f"PolicyRoutingManager: iptables-restore error: {e}")

    async def _remove_iptables_marks(self):
        """Remove all FPV-tagged iptables mangle marks.

        Uses ``iptables-save | filter | iptables-restore`` — just 2 sudo calls
        regardless of how many fpv_ rules exist.
        """
        try:
            # Dump current mangle table
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "iptables-save",
                "-t",
                "mangle",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode != 0:
                return

            current = stdout.decode()
            # Strip any line that contains our fpv_ comment marker
            filtered_lines = [line for line in current.splitlines() if "fpv_" not in line]
            filtered = "\n".join(filtered_lines) + "\n"

            if filtered == current:
                return  # Nothing to remove — skip the restore call entirely

            removed = len(current.splitlines()) - len(filtered_lines)

            # Atomically restore the filtered state (flushes + re-applies in one call)
            proc2 = await asyncio.create_subprocess_exec(
                "sudo",
                "iptables-restore",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc2.communicate(filtered.encode()), timeout=10)
            if proc2.returncode != 0:
                logger.warning(f"PolicyRoutingManager: iptables-restore (remove) failed: {stderr.decode().strip()}")
            else:
                logger.info(f"PolicyRoutingManager: removed {removed} iptables marks (2 sudo calls)")
        except Exception as e:
            logger.warning(f"PolicyRoutingManager: _remove_iptables_marks error (non-fatal): {e}")

    # ──────────────────────────────────────────────────────────────────────
    # Internal — ip rules
    # ──────────────────────────────────────────────────────────────────────

    async def _setup_ip_rules(self):
        """
        Install ip rule fwmark→table mappings (idempotent).

        Uses a single ``sudo ip -force -batch -`` call instead of one
        ``sudo ip rule`` invocation per rule, reducing 6 sudo calls to 1.
        The -force flag suppresses errors from the delete pass (rules may
        not exist on a fresh boot).
        """
        # Build batch: delete existing rules first (idempotency), then add.
        # -force ensures the batch continues even if a del fails (rule absent).
        del_lines = [
            f"rule del fwmark {MARK_VPN} lookup {TABLE_VPN}",
            f"rule del fwmark {MARK_VIDEO} lookup {TABLE_VIDEO}",
            f"rule del fwmark {MARK_MAVLINK} lookup {TABLE_VIDEO}",
        ]
        add_lines = [
            f"rule add fwmark {MARK_VPN} lookup {TABLE_VPN} prio {PRIO_VPN}",
            f"rule add fwmark {MARK_VIDEO} lookup {TABLE_VIDEO} prio {PRIO_VIDEO}",
            f"rule add fwmark {MARK_MAVLINK} lookup {TABLE_VIDEO} prio {PRIO_MAVLINK}",
        ]
        batch_input = "\n".join(del_lines + add_lines) + "\n"

        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "ip",
            "-force",
            "-batch",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(batch_input.encode())
        if proc.returncode not in (0, 1):  # 1 = some dels skipped, non-fatal
            logger.warning(f"PolicyRoutingManager: ip rule batch errors: {stderr.decode().strip()}")

        logger.info("PolicyRoutingManager: ip rules installed (1 batch sudo call)")

    async def _remove_ip_rules(self):
        """
        Remove FPV policy rules using a single ``sudo ip -force -batch -`` call.
        -force suppresses 'not found' errors when rules were never installed.
        """
        batch_input = (
            f"rule del fwmark {MARK_VPN} lookup {TABLE_VPN}\n"
            f"rule del fwmark {MARK_VIDEO} lookup {TABLE_VIDEO}\n"
            f"rule del fwmark {MARK_MAVLINK} lookup {TABLE_VIDEO}\n"
        )

        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "ip",
            "-force",
            "-batch",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate(batch_input.encode())
        # Ignore return code — errors are expected when rules don't exist

    # ──────────────────────────────────────────────────────────────────────
    # Internal — routing tables
    # ──────────────────────────────────────────────────────────────────────

    async def _update_table_route(self, table_id: int, interface: str, gateway: str):
        """Replace the default route in the given routing table."""
        from app.api.routes.network.common import run_command

        # Remove existing default in table (ignore errors — may not exist)
        await run_command(
            [
                "sudo",
                "ip",
                "route",
                "del",
                "default",
                "table",
                str(table_id),
            ]
        )

        # Add new default route
        _, stderr, rc = await run_command(
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
                "table",
                str(table_id),
            ]
        )
        if rc != 0:
            logger.warning(f"PolicyRoutingManager: route add failed for table {table_id}: {stderr}")

    async def _ensure_modem_table(self, interface: str, gateway: str) -> int:
        """Get or assign a per-modem routing table and populate it."""
        if interface not in self._modem_tables:
            table_id = TABLE_MODEM_BASE + len(self._modem_tables)
            self._modem_tables[interface] = table_id
            logger.info(f"PolicyRoutingManager: assigned table {table_id} to {interface}")
        else:
            table_id = self._modem_tables[interface]

        await self._update_table_route(table_id, interface, gateway)
        return table_id

    # ──────────────────────────────────────────────────────────────────────
    # Internal — status helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _get_ip_rules(self) -> List[str]:
        """Return filtered ip rule output (only FPV-relevant rules)."""
        from app.api.routes.network.common import run_command

        stdout, _, rc = await run_command(["ip", "rule", "show"])
        if rc != 0:
            return []
        keywords = [
            MARK_VPN.replace("0x", "0x"),
            MARK_VIDEO,
            MARK_MAVLINK,
            "0x100",
            "0x200",
            "0x300",
            str(TABLE_VPN),
            str(TABLE_VIDEO),
        ]
        return [line.strip() for line in stdout.splitlines() if any(kw in line for kw in keywords)]

    async def _get_table_routes(self, table_id: int) -> List[str]:
        """Return routes in a specific table."""
        from app.api.routes.network.common import run_command

        stdout, _, rc = await run_command(["ip", "route", "show", "table", str(table_id)])
        if rc != 0 or not stdout.strip():
            return []
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    async def _get_all_table_routes(self) -> dict:
        """Return routes for all managed tables."""
        result = {
            "vpn": {
                "id": TABLE_VPN,
                "routes": await self._get_table_routes(TABLE_VPN),
            },
            "video": {
                "id": TABLE_VIDEO,
                "routes": await self._get_table_routes(TABLE_VIDEO),
            },
            "modems": {},
        }
        for iface, table_id in self._modem_tables.items():
            result["modems"][iface] = {
                "id": table_id,
                "routes": await self._get_table_routes(table_id),
            }
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_policy_routing_manager: Optional[PolicyRoutingManager] = None


def get_policy_routing_manager() -> PolicyRoutingManager:
    global _policy_routing_manager
    if _policy_routing_manager is None:
        _policy_routing_manager = PolicyRoutingManager()
    return _policy_routing_manager
