"""
MAVLink API Routes
Endpoints for MAVLink connection management
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.services.mavlink_dialect import MAVLinkDialect
from app.i18n import get_language_from_request, translate
from app.exceptions import ServiceInitError

logger = logging.getLogger(__name__)

router = APIRouter()

# Global service instance (injected from main.py)
mavlink_service = None


def set_mavlink_service(service):
    """Inject MAVLink service instance"""
    global mavlink_service
    mavlink_service = service


class ConnectRequest(BaseModel):
    port: str
    baudrate: int = 115200


class SerialPreferencesModel(BaseModel):
    """Serial connection preferences"""

    auto_connect: bool = False


@router.post("/connect")
async def connect(request: ConnectRequest, req: Request):
    """Connect to MAVLink device and save configuration"""
    lang = get_language_from_request(req)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    result = mavlink_service.connect(request.port, request.baudrate)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    # Save successful connection to preferences
    try:
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        prefs.set_serial_config(port=request.port, baudrate=request.baudrate, successful=True)
    except (ValueError, TypeError, IOError) as e:
        logger.warning("Failed to save connection preferences", extra={"error": str(e), "port": request.port})
    except ServiceInitError as e:
        logger.warning("Preferences service unavailable", extra=e.to_dict())

    return result


@router.post("/disconnect")
async def disconnect(request: Request):
    """Disconnect from MAVLink device"""
    lang = get_language_from_request(request)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    result = mavlink_service.disconnect()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/status")
async def get_status(request: Request):
    """Get MAVLink connection status"""
    lang = get_language_from_request(request)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    return mavlink_service.get_status()


@router.get("/telemetry")
async def get_telemetry(request: Request):
    """Get current telemetry data"""
    lang = get_language_from_request(request)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    return mavlink_service.get_telemetry()


@router.get("/modes/{mav_type}")
async def get_available_modes(mav_type: int):
    """Get available flight modes for a vehicle type"""
    modes = MAVLinkDialect.get_all_modes_for_type(mav_type)
    vehicle_type = MAVLinkDialect.get_type_string(mav_type)

    return {"mav_type": mav_type, "vehicle_type": vehicle_type, "modes": modes}


@router.get("/enums/{enum_name}")
async def get_enum_values(enum_name: str, request: Request):
    """Get all values for a specific enum"""
    lang = get_language_from_request(request)
    # Return known enums
    if enum_name == "MAV_TYPE":
        return MAVLinkDialect.MAV_TYPE
    elif enum_name == "MAV_AUTOPILOT":
        return MAVLinkDialect.MAV_AUTOPILOT
    elif enum_name == "MAV_STATE":
        return MAVLinkDialect.MAV_STATE
    else:
        raise HTTPException(
            status_code=404,
            detail=translate("mavlink.enum_not_found", lang, enum_name=enum_name),
        )


# ============ Parameter Management ============


class ParameterRequest(BaseModel):
    param_name: str


class ParameterSetRequest(BaseModel):
    param_name: str
    value: float


class ParametersBatchGetRequest(BaseModel):
    params: list  # [param_name1, param_name2, ...]
    include_all: bool = False
    force_refresh: bool = False


class ParametersBatchRequest(BaseModel):
    params: dict  # {param_name: value}


@router.get("/param/{param_name}")
def get_parameter(param_name: str, request: Request):
    """Get a single parameter value from the flight controller"""
    lang = get_language_from_request(request)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))

    result = mavlink_service.get_parameter(param_name)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", translate("mavlink.parameter_get_failed", lang)),
        )

    return result


@router.post("/param")
def set_parameter(request: ParameterSetRequest, req: Request):
    """Set a parameter on the flight controller"""
    lang = get_language_from_request(req)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))

    result = mavlink_service.set_parameter(request.param_name, request.value)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", translate("mavlink.parameter_set_failed", lang)),
        )

    return result


@router.post("/params/batch/get")
def get_parameters_batch(request: ParametersBatchGetRequest, req: Request):
    """Get multiple parameters at once"""
    lang = get_language_from_request(req)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))

    result = mavlink_service.get_parameters_batch(
        request.params,
        include_all=request.include_all,
        force_refresh=request.force_refresh,
    )
    return result


@router.get("/params/cache/status")
def get_params_cache_status(req: Request):
    """Return live parameter cache status for progress polling."""
    lang = get_language_from_request(req)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))
    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))
    with mavlink_service._param_cache_lock:
        cache_count = len(mavlink_service._param_cache)
        loaded = mavlink_service._param_cache_loaded

    expected = mavlink_service._param_list_expected_count
    # Keep progress consistent with completion logic in bridge:
    # during active fetch, count whichever is more complete.
    if mavlink_service._param_list_active:
        loaded_count = max(len(mavlink_service._param_list_indexes), len(mavlink_service._param_list_params))
    else:
        loaded_count = cache_count

    if expected > 0:
        loaded_count = min(loaded_count, expected)

    return {"loaded": loaded_count, "expected": expected, "complete": loaded}


@router.post("/params/batch/set")
def set_parameters_batch(request: ParametersBatchRequest, req: Request):
    """Set multiple parameters at once"""
    lang = get_language_from_request(req)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))

    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))

    result = mavlink_service.set_parameters_batch(request.params)
    return result


@router.get("/preferences")
async def get_serial_preferences():
    """
    Get serial connection preferences from persistent storage

    Returns:
        Serial configuration including port, baudrate, and auto_connect settings
    """
    try:
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        config = prefs.get_serial_config()
        return {
            "success": True,
            "preferences": {
                "auto_connect": config.auto_connect,
                "port": config.port,
                "baudrate": config.baudrate,
            },
        }
    except (ValueError, TypeError, IOError) as e:
        logger.error("Error retrieving serial preferences (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Could not retrieve serial preferences")
    except ServiceInitError as e:
        logger.error("Preferences service error", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Service error")


@router.post("/preferences")
async def save_serial_preferences(preferences: SerialPreferencesModel, request: Request):
    """
    Save serial connection preferences to persistent storage

    Args:
        preferences: Serial preferences including auto_connect

    Returns:
        Success status and saved preferences
    """
    try:
        lang = get_language_from_request(request)
        from app.services.preferences import get_preferences

        prefs = get_preferences()

        try:
            prefs.set_serial_auto_connect(preferences.auto_connect)

            # Verify the save
            saved_config = prefs.get_serial_config()
            if saved_config.auto_connect != preferences.auto_connect:
                logger.warning(
                    "Auto-connect save verification failed",
                    extra={"requested": preferences.auto_connect, "saved": saved_config.auto_connect},
                )
                return {
                    "success": False,
                    "message": "Failed to verify saved preferences",
                    "preferences": {"auto_connect": saved_config.auto_connect},
                }

            return {
                "success": True,
                "message": translate("serial.preferences_saved", lang),
                "preferences": {"auto_connect": preferences.auto_connect},
            }
        except (ValueError, TypeError, IOError) as e:
            logger.error("Error in set_serial_auto_connect (%s): %s", type(e).__name__, e)
            raise HTTPException(status_code=500, detail="Failed to save preferences")
    except (ValueError, TypeError, IOError) as e:
        logger.error("Error saving serial preferences (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Could not save serial preferences")
    except ServiceInitError as e:
        logger.error("Preferences service error", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Service error")
