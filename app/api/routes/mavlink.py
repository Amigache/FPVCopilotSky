"""
MAVLink API Routes
Endpoints for MAVLink connection management
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from services.mavlink_dialect import MAVLinkDialect
from app.i18n import get_language_from_request, translate

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
        from services.preferences import get_preferences
        prefs = get_preferences()
        prefs.set_serial_config(
            port=request.port,
            baudrate=request.baudrate,
            successful=True
        )
    except Exception as e:
        print(f"⚠️ Failed to save connection preferences: {e}")
    
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
    
    return {
        "mav_type": mav_type,
        "vehicle_type": vehicle_type,
        "modes": modes
    }

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
        raise HTTPException(status_code=404, detail=translate("mavlink.enum_not_found", lang, enum_name=enum_name))


# ============ Parameter Management ============

class ParameterRequest(BaseModel):
    param_name: str

class ParameterSetRequest(BaseModel):
    param_name: str
    value: float

class ParametersBatchGetRequest(BaseModel):
    params: list  # [param_name1, param_name2, ...]

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
        raise HTTPException(status_code=400, detail=result.get("error", translate("mavlink.parameter_get_failed", lang)))
    
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
        raise HTTPException(status_code=400, detail=result.get("error", translate("mavlink.parameter_set_failed", lang)))
    
    return result

@router.post("/params/batch/get")
def get_parameters_batch(request: ParametersBatchGetRequest, req: Request):
    """Get multiple parameters at once"""
    lang = get_language_from_request(req)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))
    
    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))
    
    result = mavlink_service.get_parameters_batch(request.params)
    return result

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

# GCS-Only operation preset parameters
GCS_ONLY_PARAMS = {
    "FS_THR_ENABLE": 0,      # Disable throttle failsafe (no RC)
    "RC1_MIN": 1101,         # Roll min (emulate calibration)
    "RC1_MAX": 1901,         # Roll max
    "RC2_MIN": 1101,         # Pitch min
    "RC2_MAX": 1901,         # Pitch max
    "RC3_MIN": 1101,         # Throttle min
    "RC3_MAX": 1901,         # Throttle max
    "RC4_MIN": 1101,         # Yaw min
    "RC4_MAX": 1901,         # Yaw max
    "RC_PROTOCOLS": 0,       # Disable RC protocol detection
    "FS_GCS_ENABLE": 1,      # Enable GCS failsafe (RTL on disconnect)
}

@router.get("/params/gcs-only")
async def get_gcs_only_params(request: Request):
    """Get current values of GCS-only operation parameters"""
    lang = get_language_from_request(request)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))
    
    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))
    
    param_names = list(GCS_ONLY_PARAMS.keys())
    # Add ARMING_CHECK separately as it needs special handling
    param_names.append("ARMING_CHECK")
    
    result = mavlink_service.get_parameters_batch(param_names)
    
    # Add recommended values for reference
    result["recommended"] = {**GCS_ONLY_PARAMS, "ARMING_CHECK": 65470}
    
    return result

@router.post("/params/gcs-only/apply")
async def apply_gcs_only_params(request: Request, custom_values: Optional[dict] = None):
    """Apply recommended GCS-only operation parameters"""
    lang = get_language_from_request(request)
    if not mavlink_service:
        raise HTTPException(status_code=500, detail=translate("services.mavlink_not_initialized", lang))
    
    if not mavlink_service.connected:
        raise HTTPException(status_code=400, detail=translate("mavlink.not_connected", lang))
    
    # Start with defaults
    params_to_set = {**GCS_ONLY_PARAMS}
    
    # First, get current ARMING_CHECK value and modify it
    arming_result = mavlink_service.get_parameter("ARMING_CHECK")
    if arming_result["success"]:
        current_arming = int(arming_result["value"])
        # Disable bit 6 (RC check) - bit 6 = 64
        new_arming = current_arming & ~64  # Clear bit 6
        params_to_set["ARMING_CHECK"] = new_arming
    else:
        # Use safe default that skips RC check
        params_to_set["ARMING_CHECK"] = 65470
    
    # Apply custom values if provided
    if custom_values:
        params_to_set.update(custom_values)
    
    result = mavlink_service.set_parameters_batch(params_to_set)
    return result

@router.get("/preferences")
async def get_serial_preferences():
    """
    Get serial connection preferences from persistent storage
    
    Returns:
        Serial configuration including auto_connect settings
    """
    try:
        from services.preferences import get_preferences
        prefs = get_preferences()
        config = prefs.get_serial_config()
        return {
            "success": True,
            "preferences": {
                "auto_connect": config.auto_connect
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        from services.preferences import get_preferences
        prefs = get_preferences()
        
        try:
            prefs.set_serial_auto_connect(preferences.auto_connect)
            
            # Verify the save
            saved_config = prefs.get_serial_config()
            if saved_config.auto_connect != preferences.auto_connect:
                print(f"⚠️ Verification failed: requested auto_connect={preferences.auto_connect}, saved={saved_config.auto_connect}")
                return {
                    "success": False,
                    "message": "Failed to verify saved preferences",
                    "preferences": {
                        "auto_connect": saved_config.auto_connect
                    }
                }
            
            return {
                "success": True,
                "message": translate("serial.preferences_saved", lang),
                "preferences": {
                    "auto_connect": preferences.auto_connect
                }
            }
        except Exception as e:
            print(f"❌ Error in set_serial_auto_connect: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save preferences: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
