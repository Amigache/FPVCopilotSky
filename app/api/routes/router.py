"""
MAVLink Router API Routes
Endpoints for managing router outputs (UDP, TCP server/client)
Auto-starts outputs on creation, only allows delete (no start/stop)
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import re
import uuid
import logging
from app.i18n import get_language_from_request, translate

# Setup logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mavlink-router", tags=["mavlink-router"])

# Router instance (injected from main.py)
_router_service = None


def set_router_service(service):
    """Inject router service instance."""
    global _router_service
    _router_service = service


class AddOutputRequest(BaseModel):
    """Router output creation request with comprehensive validation"""

    type: Literal["tcp_server", "tcp_client", "udp"]
    host: str = Field(..., min_length=1, max_length=255)  # Allow hostnames up to 255 chars
    port: int = Field(..., ge=1024, le=65535)  # Avoid system ports
    name: Optional[str] = Field(default="", max_length=100)

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        """Validate host as IPv4 address or hostname/DNS"""
        if not v or v.strip() == "":
            raise ValueError("Host cannot be empty")

        v = v.strip()

        # IPv4 validation pattern
        ipv4_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"

        # Hostname/DNS validation pattern (alphanumeric, dots, hyphens)
        hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$"

        if not (re.match(ipv4_pattern, v) or re.match(hostname_pattern, v)):
            raise ValueError("Invalid IP address or hostname format")

        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        """Enhanced port validation with range check"""
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError("Port must be a valid integer")

        if v < 1024:
            raise ValueError("Port must be between 1024 and 65535")
        if v > 65535:
            raise ValueError("Port must be between 1024 and 65535")

        return v


class UpdateOutputRequest(BaseModel):
    """Router output update request with validation"""

    type: Optional[Literal["tcp_server", "tcp_client", "udp"]] = None
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1024, le=65535)
    name: Optional[str] = Field(None, max_length=100)

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        """Validate host as IPv4 address or hostname/DNS if provided"""
        if v is None:
            return v

        v = v.strip()
        if not v:
            raise ValueError("Host cannot be empty")

        # IPv4 validation pattern
        ipv4_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"

        # Hostname/DNS validation pattern (alphanumeric, dots, hyphens)
        hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$"

        if not (re.match(ipv4_pattern, v) or re.match(hostname_pattern, v)):
            raise ValueError("Invalid IP address or hostname format")

        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        """Enhanced port validation with range check if provided"""
        if v is None:
            return v

        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError("Port must be a valid integer")

        if v < 1024:
            raise ValueError("Port must be between 1024 and 65535")
        if v > 65535:
            raise ValueError("Port must be between 1024 and 65535")

        return v


class OutputResponse(BaseModel):
    id: str
    type: str
    host: str
    port: int
    name: str
    running: bool
    clients: Optional[int] = 0
    stats: Optional[dict] = None


@router.get("/outputs")
async def list_outputs(request: Request) -> JSONResponse:
    """List all router outputs with their status."""
    try:
        lang = get_language_from_request(request)

        print(f"DEBUG: list_outputs called, _router_service = {_router_service}")
        if not _router_service:
            logger.error("Router service not initialized")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": translate("router.service_not_initialized", lang), "outputs": []},
            )

        status = _router_service.get_status()
        outputs = status.get("outputs", [])

        logger.debug(f"Retrieved {len(outputs)} router outputs")
        return JSONResponse(content=outputs)

    except Exception as e:
        logger.error(f"Error listing outputs: {e}")
        return JSONResponse(
            status_code=500, content={"success": False, "error": "Failed to get outputs", "outputs": []}
        )


@router.post("/outputs")
async def add_output(request: AddOutputRequest, req: Request) -> JSONResponse:
    """Add a new router output with validation and conflict detection."""
    try:
        lang = get_language_from_request(req)

        if not _router_service:
            logger.error("Router service not initialized")
            return JSONResponse(
                status_code=500, content={"success": False, "error": translate("router.service_not_initialized", lang)}
            )

        from app.services.mavlink_router import OutputConfig, OutputType

        # Check for port conflicts
        existing_outputs = _router_service.get_status().get("outputs", [])
        for output in existing_outputs:
            if output.get("port") == request.port and output.get("host") == request.host:
                logger.warning(f"Port conflict: {request.host}:{request.port} already in use")
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Port {request.port} on {request.host} is already in use"},
                )

        output_id = str(uuid.uuid4())[:8]
        output_name = request.name or f"{request.type}:{request.port}"

        config = OutputConfig(
            id=output_id,
            type=OutputType(request.type),
            host=request.host,
            port=request.port,
            name=output_name,
            enabled=True,
            auto_start=True,
        )

        # Add the output (auto_start=True will also start it)
        success, message = _router_service.add_output(config)

        if not success:
            logger.error(f"Failed to add output: {message}")
            return JSONResponse(
                status_code=400, content={"success": False, "error": message or "Failed to create output"}
            )

        logger.info(f"Successfully added output {output_id}: {request.type} {request.host}:{request.port}")
        return JSONResponse(
            content={"success": True, "message": translate("router.output_created", lang), "output_id": output_id}
        )

    except ValueError as e:
        # Pydantic validation errors
        logger.warning(f"Validation error adding output: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})
    except Exception as e:
        logger.error(f"Error adding output: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to create output"})


@router.put("/outputs/{output_id}")
async def update_output(output_id: str, request: UpdateOutputRequest, req: Request) -> JSONResponse:
    """Update a router output configuration with validation."""
    try:
        lang = get_language_from_request(req)

        if not _router_service:
            logger.error("Router service not initialized")
            return JSONResponse(
                status_code=500, content={"success": False, "error": translate("router.service_not_initialized", lang)}
            )

        # Check if output exists
        outputs = _router_service.outputs
        if output_id not in outputs:
            logger.warning(f"Output {output_id} not found for update")
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": translate("router.output_not_found", lang, output_id=output_id)},
            )

        # Get current output config
        current_config = outputs[output_id]

        # Build updated config with only provided fields
        updated_data = {}
        if request.type is not None:
            updated_data["type"] = request.type
        if request.host is not None:
            updated_data["host"] = request.host
        if request.port is not None:
            updated_data["port"] = request.port
        if request.name is not None:
            updated_data["name"] = request.name

        # Check for port conflicts if port/host changed
        if "port" in updated_data or "host" in updated_data:
            new_port = updated_data.get("port", current_config.config.port)
            new_host = updated_data.get("host", current_config.config.host)

            existing_outputs = _router_service.get_status().get("outputs", [])
            for output in existing_outputs:
                if output.get("id") != output_id and output.get("port") == new_port and output.get("host") == new_host:
                    logger.warning(f"Port conflict: {new_host}:{new_port} already in use")
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "error": f"Port {new_port} on {new_host} is already in use"},
                    )

        # Update output
        success, message = _router_service.update_output(output_id, updated_data)

        if not success:
            logger.error(f"Failed to update output {output_id}: {message}")
            return JSONResponse(
                status_code=400, content={"success": False, "error": message or "Failed to update output"}
            )

        logger.info(f"Successfully updated output {output_id}")
        return JSONResponse(content={"success": True, "message": translate("router.output_updated", lang)})

    except ValueError as e:
        # Pydantic validation errors
        logger.warning(f"Validation error updating output {output_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})
    except Exception as e:
        logger.error(f"Error updating output {output_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to update output"})


@router.delete("/outputs/{output_id}")
async def remove_output(output_id: str, request: Request) -> JSONResponse:
    """Remove a router output (stops it first if running)."""
    try:
        lang = get_language_from_request(request)

        if not _router_service:
            logger.error("Router service not initialized")
            return JSONResponse(
                status_code=500, content={"success": False, "error": translate("router.service_not_initialized", lang)}
            )

        # Check if output exists
        outputs = _router_service.outputs
        if output_id not in outputs:
            logger.warning(f"Output {output_id} not found for deletion")
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": translate("router.output_not_found", lang, output_id=output_id)},
            )

        success, message = _router_service.remove_output(output_id)

        if not success:
            logger.error(f"Failed to remove output {output_id}: {message}")
            return JSONResponse(
                status_code=400, content={"success": False, "error": message or "Failed to delete output"}
            )

        logger.info(f"Successfully removed output {output_id}")
        return JSONResponse(content={"success": True, "message": translate("router.output_deleted", lang)})

    except Exception as e:
        logger.error(f"Error removing output {output_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to delete output"})


# Additional endpoints for presets and restart functionality


@router.get("/presets")
async def get_presets(request: Request) -> JSONResponse:
    """Get available router presets."""
    try:
        # Default presets
        presets = {
            "qgc": {"type": "udp", "host": "255.255.255.255", "port": 14550, "name": "QGroundControl UDP"},
            "missionplanner": {"type": "tcp_client", "host": "127.0.0.1", "port": 5760, "name": "Mission Planner TCP"},
        }

        return JSONResponse(content={"success": True, "presets": presets})

    except Exception as e:
        logger.error(f"Error getting presets: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to get presets"})


@router.post("/restart")
async def restart_router(request: Request) -> JSONResponse:
    """Restart the MAVLink router service."""
    try:
        lang = get_language_from_request(request)

        if not _router_service:
            logger.error("Router service not initialized")
            return JSONResponse(
                status_code=500, content={"success": False, "error": translate("router.service_not_initialized", lang)}
            )

        success, message = _router_service.restart()

        if not success:
            logger.error(f"Failed to restart router: {message}")
            return JSONResponse(
                status_code=500, content={"success": False, "error": message or "Failed to restart router"}
            )

        logger.info("Successfully restarted MAVLink router")
        return JSONResponse(content={"success": True, "message": translate("router.restarted", lang)})

    except Exception as e:
        logger.error(f"Error restarting router: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to restart router"})


@router.post("/outputs/{output_id}/restart")
async def restart_output(output_id: str, request: Request) -> JSONResponse:
    """Restart a specific router output."""
    try:
        lang = get_language_from_request(request)

        if not _router_service:
            logger.error("Router service not initialized")
            return JSONResponse(
                status_code=500, content={"success": False, "error": translate("router.service_not_initialized", lang)}
            )

        # Check if output exists
        outputs = _router_service.outputs
        if output_id not in outputs:
            logger.warning(f"Output {output_id} not found for restart")
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": translate("router.output_not_found", lang, output_id=output_id)},
            )

        success, message = _router_service.restart_output(output_id)

        if not success:
            logger.error(f"Failed to restart output {output_id}: {message}")
            return JSONResponse(
                status_code=400, content={"success": False, "error": message or "Failed to restart output"}
            )

        logger.info(f"Successfully restarted output {output_id}")
        return JSONResponse(content={"success": True, "message": translate("router.output_restarted", lang)})

    except Exception as e:
        logger.error(f"Error restarting output {output_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to restart output"})
