"""
Video Streaming API Routes
Aggregates all video endpoint groups (status, control, configuration, info, adaptive)
"""

from fastapi import APIRouter

from app.api.routes import video_adaptive, video_config, video_control, video_info, video_status

# Main router that aggregates all video sub-routes
router = APIRouter(prefix="/api/video", tags=["video"])

# Include all sub-routers (they handle their own prefixes and tag groupings)
router.include_router(video_status.router)
router.include_router(video_control.router)
router.include_router(video_config.router)
router.include_router(video_info.router)
router.include_router(video_adaptive.router)


def set_video_service(service):
    """Set the video service instance for all sub-routers"""
    video_status.set_video_service(service)
    video_control.set_video_service(service)
    video_config.set_video_service(service)
    video_info.set_video_service(service)
    # video_adaptive doesn't need the service; uses preferences directly
