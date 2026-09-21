"""Single owner of the main-table default-route metrics.

Before this module, two independent writers manipulated the default route
metrics (``api/routes/network/status.set_priority_mode`` and
``services/modem_pool._apply_modem_priority``), which could clobber each
other. All main-table priority changes now go through :class:`RouteManager`,
which applies them idempotently and rate-limits with a short cooldown to
avoid flapping.

Policy-routing tables (100/200/...) remain owned by PolicyRoutingManager.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PRIMARY_METRIC = 100
BACKUP_METRIC = 200


class RouteManager:
    def __init__(self, cooldown_s: float = 5.0):
        self.cooldown_s = cooldown_s
        self._lock = asyncio.Lock()
        self._last_primary: str = ""
        self._last_change: float = 0.0

    async def _show_defaults(self) -> List[Dict[str, Any]]:
        from app.api.routes.network.common import run_command

        stdout, _, _ = await run_command(["ip", "route", "show", "default"])
        routes: List[Dict[str, Any]] = []
        for line in stdout.splitlines():
            if "default" not in line:
                continue
            parts = line.split()
            route: Dict[str, Any] = {}
            try:
                if "via" in parts:
                    route["via"] = parts[parts.index("via") + 1]
                if "dev" in parts:
                    route["dev"] = parts[parts.index("dev") + 1]
                if "metric" in parts:
                    route["metric"] = int(parts[parts.index("metric") + 1])
            except (ValueError, IndexError):
                continue
            if route.get("dev"):
                routes.append(route)
        return routes

    async def _replace_default(self, dev: str, via: Optional[str], metric: int) -> bool:
        from app.api.routes.network.common import run_command

        cmd = ["sudo", "ip", "route", "replace", "default", "dev", dev]
        if via:
            cmd += ["via", via]
        cmd += ["metric", str(metric)]
        _, _, rc = await run_command(cmd)
        return rc == 0

    async def set_priority(self, primary_interface: str) -> Dict[str, Any]:
        """Make *primary_interface* the metric-100 default; others become backups.

        Idempotent and rate-limited: if the same interface was set within the
        cooldown window, it is a no-op.
        """
        if not primary_interface:
            return {"success": False, "message": "No primary interface", "changes": []}

        async with self._lock:
            now = time.monotonic()
            if primary_interface == self._last_primary and (now - self._last_change) < self.cooldown_s:
                return {"success": True, "message": "unchanged (cooldown)", "changes": []}

            routes = await self._show_defaults()
            if not routes:
                return {"success": False, "message": "No default routes found", "changes": []}

            changes = []
            for route in routes:
                metric = PRIMARY_METRIC if route["dev"] == primary_interface else BACKUP_METRIC
                if route.get("metric") == metric:
                    continue
                if await self._replace_default(route["dev"], route.get("via"), metric):
                    changes.append(f"{route['dev']}: metric {metric}")

            self._last_primary = primary_interface
            self._last_change = now
            logger.info(
                "Default-route priority set",
                extra={"primary": primary_interface, "changes": changes},
            )
            return {"success": True, "primary": primary_interface, "changes": changes}

    async def get_status(self) -> Dict[str, Any]:
        routes = await self._show_defaults()
        primary = min(routes, key=lambda r: r.get("metric", 1_000_000))["dev"] if routes else None
        return {
            "primary": primary,
            "last_primary": self._last_primary,
            "routes": routes,
        }


_route_manager: Optional[RouteManager] = None


def get_route_manager() -> RouteManager:
    global _route_manager
    if _route_manager is None:
        _route_manager = RouteManager()
    return _route_manager
