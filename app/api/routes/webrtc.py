"""
WebRTC Signaling API Routes

Endpoints for WebRTC peer connection management:
- Session creation and SDP exchange (with aiortc)
- ICE candidate trickle
- Connection stats and monitoring
- 4G-optimized configuration
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.i18n import get_language_from_request, translate

router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])

# Service reference (set by main.py)
_webrtc_service = None


def set_webrtc_service(service):
    """Set the WebRTC service instance"""
    global _webrtc_service
    _webrtc_service = service


# ── Pydantic Models ──────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    peer_id: Optional[str] = None


class SDPRequest(BaseModel):
    peer_id: str
    sdp: str
    type: str = Field(pattern="^(offer|answer)$")


class ICECandidateRequest(BaseModel):
    peer_id: str
    candidate: Dict[str, Any]


class PeerStatsRequest(BaseModel):
    peer_id: str
    stats: Dict[str, Any]


class AdaptiveConfigRequest(BaseModel):
    max_bitrate: Optional[int] = Field(None, ge=100, le=10000)
    min_bitrate: Optional[int] = Field(None, ge=100, le=5000)
    target_bitrate: Optional[int] = Field(None, ge=100, le=10000)
    max_framerate: Optional[int] = Field(None, ge=5, le=60)
    min_framerate: Optional[int] = Field(None, ge=5, le=30)
    adaptation_enabled: Optional[bool] = None
    congestion_control: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_status(request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    return _webrtc_service.get_status()


@router.post("/session")
async def create_session(req: CreateSessionRequest, request: Request):
    """Create a new WebRTC peer session (aiortc RTCPeerConnection)."""
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))

    # Use async create_peer_connection which creates the aiortc PC
    result = await _webrtc_service.create_peer_connection(req.peer_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create session"))
    return result


@router.post("/offer")
async def handle_offer(req: SDPRequest, request: Request):
    """Handle SDP offer from browser → returns SDP answer from aiortc."""
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))

    result = await _webrtc_service.handle_offer(req.peer_id, req.sdp)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to handle offer"))
    return result


@router.post("/answer")
async def handle_answer(req: SDPRequest, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    result = _webrtc_service.handle_answer(req.peer_id, req.sdp)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to handle answer"))
    return result


@router.post("/ice-candidate")
async def add_ice_candidate(req: ICECandidateRequest, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    result = await _webrtc_service.add_ice_candidate(req.peer_id, req.candidate)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to add ICE candidate"))
    return result


@router.get("/ice-candidates/{peer_id}")
async def get_ice_candidates(peer_id: str, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    return _webrtc_service.get_ice_candidates(peer_id)


@router.post("/connected")
async def set_connected(req: CreateSessionRequest, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    if not req.peer_id:
        raise HTTPException(status_code=400, detail="peer_id is required")
    result = _webrtc_service.set_peer_connected(req.peer_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/stats")
async def update_stats(req: PeerStatsRequest, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    return _webrtc_service.update_peer_stats(req.peer_id, req.stats)


@router.post("/disconnect")
async def disconnect_peer(req: CreateSessionRequest, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    if not req.peer_id:
        raise HTTPException(status_code=400, detail="peer_id is required")
    result = _webrtc_service.disconnect_peer(req.peer_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/logs")
async def get_logs(request: Request, limit: int = 100):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    return {"logs": _webrtc_service.get_logs(limit)}


@router.get("/4g-config")
async def get_4g_config(request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    return _webrtc_service.get_4g_optimized_config()


@router.post("/adaptive-config")
async def update_adaptive_config(req: AdaptiveConfigRequest, request: Request):
    lang = get_language_from_request(request)
    if not _webrtc_service:
        raise HTTPException(status_code=503, detail=translate("services.webrtc_not_initialized", lang))
    config_dict = {k: v for k, v in req.model_dump().items() if v is not None}
    if not config_dict:
        raise HTTPException(status_code=400, detail="No configuration provided")
    result = _webrtc_service.update_adaptive_config(config_dict)
    if not result["success"]:
        raise HTTPException(status_code=400, detail="Failed to update configuration")
    return result
