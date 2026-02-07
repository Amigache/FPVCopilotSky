"""
MAVLink Router API Routes
Endpoints for managing router outputs (UDP, TCP server/client)
Auto-starts outputs on creation, only allows delete (no start/stop)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, List
import uuid

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
async def list_outputs() -> List[dict]:
    """List all router outputs with their status."""
    if not _router_service:
        raise HTTPException(status_code=500, detail="Router service not initialized")
    
    status = _router_service.get_status()
    return status.get("outputs", [])


@router.post("/outputs")
async def add_output(request: AddOutputRequest):
    """Add a new router output and auto-start it."""
    if not _router_service:
        raise HTTPException(status_code=500, detail="Router service not initialized")
    
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
async def update_output(output_id: str, request: AddOutputRequest):
    """Update a router output configuration."""
    if not _router_service:
        raise HTTPException(status_code=500, detail="Router service not initialized")
    
    from app.services.mavlink_router import OutputConfig, OutputType
    
    # Check if output exists
    outputs = _router_service.outputs
    if output_id not in outputs:
        raise HTTPException(status_code=404, detail=f"Output {output_id} not found")
    
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
async def remove_output(output_id: str):
    """Remove a router output (stops it first if running)."""
    if not _router_service:
        raise HTTPException(status_code=500, detail="Router service not initialized")
    
    success, message = _router_service.remove_output(output_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=message)
    
    return {"success": True, "message": message}


@router.get("/status")
async def get_router_status():
    """Get full router status and statistics."""
    if not _router_service:
        raise HTTPException(status_code=500, detail="Router service not initialized")
    
    return _router_service.get_status()
