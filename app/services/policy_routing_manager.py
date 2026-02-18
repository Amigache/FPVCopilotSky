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
from typing import Dict, List, Optional, Tuple

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
        """Install iptables mangle MARK rules for all traffic classes (idempotent)."""
        from app.api.routes.network.common import run_command

        # First remove any stale FPV marks to ensure idempotency
        await self._remove_iptables_marks()

        for tc in TRAFFIC_CLASSES:
            proto = tc["proto"]
            fwmark = tc["fwmark"]
            for dport in tc["dports"]:
                _, _, rc = await run_command(
                    [
                        "sudo",
                        "iptables",
                        "-t",
                        "mangle",
                        "-A",
                        "OUTPUT",
                        "-p",
                        proto,
                        "--dport",
                        dport,
                        "-j",
                        "MARK",
                        "--set-mark",
                        fwmark,
                        "-m",
                        "comment",
                        "--comment",
                        f"fpv_{tc['name']}",
                    ]
                )
                if rc != 0:
                    logger.warning(f"PolicyRoutingManager: iptables rule failed for " f"{tc['name']} {proto}/{dport}")

        logger.info("PolicyRoutingManager: iptables mangle marks installed")

    async def _remove_iptables_marks(self):
        """Remove all FPV-tagged iptables mangle marks."""
        from app.api.routes.network.common import run_command

        # List all OUTPUT mangle rules and delete ones tagged fpv_*
        stdout, _, rc = await run_command(
            [
                "sudo",
                "iptables",
                "-t",
                "mangle",
                "-L",
                "OUTPUT",
                "--line-numbers",
                "-n",
            ]
        )
        if rc != 0:
            return

        # Parse lines in reverse so line numbers stay valid when deleting
        lines_to_del = []
        for line in stdout.splitlines():
            if "fpv_" in line:
                parts = line.split()
                if parts and parts[0].isdigit():
                    lines_to_del.append(int(parts[0]))

        for num in sorted(lines_to_del, reverse=True):
            await run_command(
                [
                    "sudo",
                    "iptables",
                    "-t",
                    "mangle",
                    "-D",
                    "OUTPUT",
                    str(num),
                ]
            )

        if lines_to_del:
            logger.info(f"PolicyRoutingManager: removed {len(lines_to_del)} iptables marks")

    # ──────────────────────────────────────────────────────────────────────
    # Internal — ip rules
    # ──────────────────────────────────────────────────────────────────────

    async def _setup_ip_rules(self):
        """Install ip rule fwmark→table mappings (idempotent)."""
        from app.api.routes.network.common import run_command

        # Remove first to ensure idempotency
        await self._remove_ip_rules()

        rules: List[Tuple[int, str, int]] = [
            (PRIO_VPN, MARK_VPN, TABLE_VPN),
            (PRIO_VIDEO, MARK_VIDEO, TABLE_VIDEO),
            (PRIO_MAVLINK, MARK_MAVLINK, TABLE_VIDEO),
        ]

        for prio, fwmark, table in rules:
            _, _, rc = await run_command(
                [
                    "sudo",
                    "ip",
                    "rule",
                    "add",
                    "fwmark",
                    fwmark,
                    "lookup",
                    str(table),
                    "prio",
                    str(prio),
                ]
            )
            if rc != 0:
                logger.warning(f"PolicyRoutingManager: ip rule failed — " f"prio={prio} fwmark={fwmark} table={table}")

        logger.info("PolicyRoutingManager: ip rules installed")

    async def _remove_ip_rules(self):
        """Remove FPV policy rules (by fwmark/table combo)."""
        from app.api.routes.network.common import run_command

        rules_to_remove = [
            (MARK_VPN, TABLE_VPN),
            (MARK_VIDEO, TABLE_VIDEO),
            (MARK_MAVLINK, TABLE_VIDEO),
        ]

        for fwmark, table in rules_to_remove:
            # Try to delete (may not exist — suppress errors)
            await run_command(
                [
                    "sudo",
                    "ip",
                    "rule",
                    "del",
                    "fwmark",
                    fwmark,
                    "lookup",
                    str(table),
                ]
            )

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
