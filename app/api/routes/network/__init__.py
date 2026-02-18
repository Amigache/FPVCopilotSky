"""
Network Routes Module

This package contains all network-related API endpoints, organized by functionality:

- status: Network status, dashboard, interfaces, priority
- flight_mode: Complete network optimization for FPV streaming
- flight_session: Network performance recording during flights
- latency: Latency monitoring and testing
- failover: Automatic network switching
- dns: DNS caching management
- bridge: Network-video event bridge (self-healing streaming)
- mptcp: Multi-Path TCP configuration
- common: Shared utilities and models
"""

from fastapi import APIRouter

# Import all sub-routers
from .status import router as status_router, get_network_status
from .flight_mode import router as flight_mode_router
from .flight_session import router as flight_session_router
from .latency import router as latency_router
from .failover import router as failover_router
from .dns import router as dns_router
from .bridge import router as bridge_router
from .mptcp import router as mptcp_router
from .modem_pool import router as modem_pool_router
from .policy_routing import router as policy_routing_router
from .vpn_health import router as vpn_health_router

# Create main router that includes all sub-routers
router = APIRouter(tags=["network"])

# Include all sub-routers
router.include_router(status_router, tags=["network-status"])
router.include_router(flight_mode_router, tags=["network-flight-mode"])
router.include_router(flight_session_router, tags=["network-flight-session"])
router.include_router(latency_router, tags=["network-latency"])
router.include_router(failover_router, tags=["network-failover"])
router.include_router(dns_router, tags=["network-dns"])
router.include_router(bridge_router, tags=["network-bridge"])
router.include_router(mptcp_router, tags=["network-mptcp"])
router.include_router(modem_pool_router, tags=["network-modem-pool"])
router.include_router(policy_routing_router, tags=["network-policy-routing"])
router.include_router(vpn_health_router, tags=["network-vpn-health"])

# Export for backward compatibility
__all__ = ["router", "get_network_status"]
