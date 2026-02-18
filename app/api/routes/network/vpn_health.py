"""
VPN Health API Routes — FASE 3

4 endpoints for monitoring VPN health during modem switches.
All under prefix /api/network/vpn-health
"""

from fastapi import APIRouter

router = APIRouter(prefix="/vpn-health")


def _get_checker():
    from app.services.vpn_health_checker import get_vpn_health_checker

    return get_vpn_health_checker()


# ─────────────────────────────────────────────────────────────────────────────
# GET /status
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_vpn_health_status():
    """
    Synchronous status snapshot: initialized flag, VPN type, peer IP,
    last health check result and RTT.
    """
    checker = _get_checker()
    return {"success": True, **checker.get_status()}


# ─────────────────────────────────────────────────────────────────────────────
# POST /check
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/check")
async def run_vpn_health_check():
    """
    Run a full VPN health check right now: interface UP + peer ping.
    Returns health result with RTT measurement.
    """
    checker = _get_checker()
    result = await checker.check_vpn_health()
    return {"success": True, **result}


# ─────────────────────────────────────────────────────────────────────────────
# GET /peer-ip
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/peer-ip")
async def get_vpn_peer_ip():
    """
    Return the peer IP currently used for health pings.
    Triggers peer re-discovery if not yet cached.
    """
    checker = _get_checker()
    peer_ip = await checker.get_peer_ip()
    return {
        "success": True,
        "peer_ip": peer_ip,
        "vpn_type": checker._vpn_type,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /type
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/type")
async def get_vpn_type():
    """
    Return the detected VPN type (tailscale / wireguard / openvpn / none / unknown).
    Triggers detection if not yet initialized.
    """
    checker = _get_checker()
    if not checker._initialized:
        await checker.initialize()
    return {
        "success": True,
        "vpn_type": checker._vpn_type,
        "initialized": checker._initialized,
        "has_peer": checker._peer_ip is not None,
    }
