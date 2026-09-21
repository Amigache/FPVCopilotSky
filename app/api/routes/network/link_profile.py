"""Link profile endpoints: adapt video + telemetry to the connection type."""

import logging
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.link_profile_manager import get_link_profile_manager
from app.services.preferences import get_preferences

logger = logging.getLogger(__name__)

router = APIRouter()


class OverrideRequest(BaseModel):
    profile: Literal["", "lan", "modem", "vpn"]


class SettingsRequest(BaseModel):
    mode: Optional[Literal["auto", "manual"]] = None
    forced: Optional[Literal["", "lan", "modem", "vpn"]] = None
    auto_apply: Optional[bool] = None
    telemetry_apply: Optional[bool] = None


@router.get("/link-profile")
async def get_link_profile():
    """Current link profile state (detected link, active/desired profile)."""
    return get_link_profile_manager().get_status()


@router.post("/link-profile/override")
async def set_link_profile_override(req: OverrideRequest):
    """Force a profile ('' to return to automatic detection)."""
    return await get_link_profile_manager().set_override(req.profile)


@router.post("/link-profile/settings")
async def set_link_profile_settings(req: SettingsRequest):
    """Update link profile mode / auto-apply / telemetry opt-in."""
    prefs = get_preferences()
    prefs.set_link_profile_settings(mode=req.mode, forced=req.forced, auto_apply=req.auto_apply)

    if req.telemetry_apply is not None:
        prefs.set_link_profile_telemetry_apply(req.telemetry_apply)

    return {"success": True, "settings": get_link_profile_manager().get_status()}


@router.post("/link-profile/apply")
async def apply_link_profile():
    """Apply the current desired profile immediately."""
    manager = get_link_profile_manager()
    status = manager.get_status()
    desired = status.get("desired_profile") or status.get("detected_link")
    if not desired or desired == "unknown":
        raise HTTPException(status_code=400, detail="No link profile to apply")
    return await manager.apply_profile(desired, reason="manual")
