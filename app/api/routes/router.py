"""
MAVLink Router API Routes
Endpoints for managing router outputs (UDP, TCP server/client)
Auto-starts outputs on creation, only allows delete (no start/stop)
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Literal, List
import uuid
from app.i18n import get_language_from_request, translate

router = APIRouter(prefix="/api/mavlink-router", tags=["mavlink-router"])

# Router instance (injected from main.py)
_router_service = None


def set_router_service(service):
    """Inject router service instance."""
    global _router_service
    _router_service = service


class AddOutputRequest(BaseModel):
    type: Literal["tcp_server", "tcp_client", "udp"]
    host: str = "0.0.0.0"
    port: int
    name: str = ""


class OutputResponse(BaseModel):
    id: str
    type: str
    host: str
    port: int
    name: str
    running: bool
    clients: int
    stats: dict


@router.get("/outputs")
async def list_outputs(request: Request) -> List[dict]:
    """List all router outputs with their status."""
    lang = get_language_from_request(request)
    if not _router_service:
        raise HTTPException(status_code=500, detail=translate("router.service_not_initialized", lang))
    
    status = _router_service.get_status()
    return status.get("outputs", [])


@router.post("/outputs")
async def add_output(request: AddOutputRequest, req: Request):
    """Add a new router output and auto-start it."""
    lang = get_language_from_request(req)
    if not _router_service:
        raise HTTPException(status_code=500, detail=translate("router.service_not_initialized", lang))
    
    from app.services.mavlink_router import OutputConfig, OutputType
    
    output_id = str(uuid.uuid4())[:8]
    
    config = OutputConfig(
        id=output_id,
        type=OutputType(request.type),
        host=request.host,
        port=request.port,
        name=request.name or f"{request.type}:{request.port}",
        enabled=True,
        auto_start=True  # Always auto-start
    )
    
    # Add the output (auto_start=True will also start it)
    success, message = _router_service.add_output(config)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "id": output_id,
        "type": request.type,
        "host": request.host,
        "port": request.port,
        "name": config.name,
        "running": True,
        "clients": 0,
        "stats": {"tx": 0, "rx": 0, "errors": 0}
    }


@router.put("/outputs/{output_id}")
async def update_output(output_id: str, request: AddOutputRequest, req: Request):
    """Update a router output configuration."""
    lang = get_language_from_request(req)
    if not _router_service:
        raise HTTPException(status_code=500, detail=translate("router.service_not_initialized", lang))
    
    from app.services.mavlink_router import OutputConfig, OutputType
    
    # Check if output exists
    outputs = _router_service.outputs
    if output_id not in outputs:
        raise HTTPException(status_code=404, detail=translate("router.output_not_found", lang, output_id=output_id))
    
    # Remove the old output
    success, message = _router_service.remove_output(output_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Create new output with updated config
    config = OutputConfig(
        id=output_id,
        type=OutputType(request.type),
        host=request.host,
        port=request.port,
        name=request.name or f"{request.type}:{request.port}",
        enabled=True,
        auto_start=True  # Always auto-start after update
    )
    
    # Add the updated output
    success, message = _router_service.add_output(config)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "id": output_id,
        "type": request.type,
        "host": request.host,
        "port": request.port,
        "name": config.name,
        "running": True,
        "clients": 0,
        "stats": {"tx": 0, "rx": 0, "errors": 0}
    }


@router.delete("/outputs/{output_id}")
async def remove_output(output_id: str, request: Request):
    """Remove a router output (stops it first if running)."""
    lang = get_language_from_request(request)
    if not _router_service:
        raise HTTPException(status_code=500, detail=translate("router.service_not_initialized", lang))
    
    success, message = _router_service.remove_output(output_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=message)
    
    return {"success": True, "message": message}


@router.get("/status")
async def get_router_status(request: Request):
    """Get full router status and statistics."""
    lang = get_language_from_request(request)
    if not _router_service:
        raise HTTPException(status_code=500, detail=translate("router.service_not_initialized", lang))
    
    return _router_service.get_status()

@router.get("/presets")
async def get_router_presets(request: Request):
    """
    Get predefined router output presets.
    
    Returns common configurations for different Ground Control Stations:
    - QGroundControl UDP
    - Mission Planner TCP Server
    - Custom TCP Client
    """
    lang = get_language_from_request(request)
    return {
        "success": True,
        "presets": {
            "qgc_udp": {
                "name": "QGroundControl UDP",
                "type": "udp",
                "host": "0.0.0.0",
                "port": 14550,
                "description": "Standard QGroundControl UDP endpoint"
            },
            "mission_planner_tcp": {
                "name": "Mission Planner TCP",
                "type": "tcp_server",
                "host": "0.0.0.0",
                "port": 5760,
                "description": "For Mission Planner GCS"
            },
            "custom_tcp_client": {
                "name": "Custom TCP Client",
                "type": "tcp_client",
                "host": "192.168.1.100",
                "port": 5760,
                "description": "For remote GCS (edit host/port as needed)"
            }
        },
        "message": translate("router.presets_loaded", lang)
    }