"""
MAVLink API Routes
Endpoints for MAVLink connection management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.mavlink_dialect import MAVLinkDialect

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

@router.post("/connect")
async def connect(request: ConnectRequest):
    """Connect to MAVLink device and save configuration"""
    if not mavlink_service:
        raise HTTPException(status_code=500, detail="MAVLink service not initialized")
    
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
async def disconnect():
    """Disconnect from MAVLink device"""
    if not mavlink_service:
        raise HTTPException(status_code=500, detail="MAVLink service not initialized")
    
    result = mavlink_service.disconnect()
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.get("/status")
async def get_status():
    """Get MAVLink connection status"""
    if not mavlink_service:
        raise HTTPException(status_code=500, detail="MAVLink service not initialized")
    
    return mavlink_service.get_status()

@router.get("/telemetry")
async def get_telemetry():
    """Get current telemetry data"""
    if not mavlink_service:
        raise HTTPException(status_code=500, detail="MAVLink service not initialized")
    
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
async def get_enum_values(enum_name: str):
    """Get all values for a specific enum"""
    # Return known enums
    if enum_name == "MAV_TYPE":
        return MAVLinkDialect.MAV_TYPE
    elif enum_name == "MAV_AUTOPILOT":
        return MAVLinkDialect.MAV_AUTOPILOT
    elif enum_name == "MAV_STATE":
        return MAVLinkDialect.MAV_STATE
    else:
        raise HTTPException(status_code=404, detail=f"Enum {enum_name} not found")

