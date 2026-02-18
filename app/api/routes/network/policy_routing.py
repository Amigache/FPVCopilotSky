"""
Policy Routing API Routes

7 endpoints for managing traffic isolation via Linux policy routing.
All under prefix /api/network/policy-routing
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/policy-routing")


class UpdateModemRequest(BaseModel):
    interface: str
    gateway: str


def _get_manager():
    from app.services.policy_routing_manager import get_policy_routing_manager

    return get_policy_routing_manager()


# ─────────────────────────────────────────────────────────────────────────────
# GET /status
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_policy_routing_status():
    """Full status: initialized flag, active modem, policy rules, table routes, traffic classes."""
    manager = _get_manager()
    status = await manager.get_status()
    return {"success": True, **status}


# ─────────────────────────────────────────────────────────────────────────────
# POST /initialize
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/initialize")
async def initialize_policy_routing():
    """
    Idempotent initialization: create iptables mangle marks,
    ip rules (fwmark → table), and routing tables.
    Safe to call multiple times.
    """
    manager = _get_manager()
    success = await manager.initialize()
    return {
        "success": success,
        "message": "Policy routing initialized" if success else "Initialization failed — check logs",
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /cleanup
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/cleanup")
async def cleanup_policy_routing():
    """Remove all iptables marks and ip rules created by PolicyRoutingManager."""
    manager = _get_manager()
    success = await manager.cleanup()
    return {
        "success": success,
        "message": "Policy routing cleaned up" if success else "Cleanup partially failed — check logs",
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /update-modem
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/update-modem")
async def update_active_modem(req: UpdateModemRequest):
    """
    Update routing tables 100 (VPN) and 200 (Video/MAVLink) to route
    through the specified modem interface and gateway.
    """
    manager = _get_manager()
    success = await manager.update_active_modem(req.interface, req.gateway)
    return {
        "success": success,
        "interface": req.interface,
        "gateway": req.gateway,
        "message": (
            f"Routing updated: tables VPN(100)+Video(200) → {req.interface} via {req.gateway}"
            if success
            else "Failed to update routing — check logs"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /tables
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/tables")
async def get_routing_tables():
    """Show routes in all managed routing tables (VPN=100, Video=200, per-modem 201+)."""
    manager = _get_manager()
    tables = await manager.get_tables()
    return {"success": True, "tables": tables}


# ─────────────────────────────────────────────────────────────────────────────
# GET /rules
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/rules")
async def get_policy_rules():
    """Show current ip rules (fwmark → table mappings)."""
    manager = _get_manager()
    rules = await manager.get_rules()
    return {"success": True, "rules": rules, "count": len(rules)}


# ─────────────────────────────────────────────────────────────────────────────
# GET /traffic-classes
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/traffic-classes")
async def get_traffic_classes():
    """Show all traffic classes (name, fwmark, table, description, ports)."""
    from app.services.policy_routing_manager import TRAFFIC_CLASSES

    # Return deduplicated by name (collapse video_tcp into video)
    seen = set()
    classes = []
    for tc in TRAFFIC_CLASSES:
        if tc["name"] not in seen:
            seen.add(tc["name"])
            classes.append(
                {
                    "name": tc["name"],
                    "fwmark": tc["fwmark"],
                    "table_id": tc["table_id"],
                    "description": tc["description"],
                    "ports": tc["dports"],
                    "proto": tc["proto"],
                }
            )
    return {"success": True, "traffic_classes": classes}
