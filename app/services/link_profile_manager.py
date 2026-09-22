"""Link Profile Manager.

Detects the active connection class (LAN/WiFi, 4G/LTE, VPN) and applies the
corresponding :mod:`app.services.link_profiles` profile to the video pipeline
and (optionally) the MAVLink telemetry stream rates.

Design principles:
- Auto by default, with manual override.
- Conservative: debounce the detection and use a cooldown between applies so a
  flapping link does not repeatedly restart the stream.
- Video restart only when mode/resolution/fps actually change; otherwise the
  bitrate is adjusted live (no stream interruption).
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from app.services.link_profiles import classify_link_type

logger = logging.getLogger(__name__)


class LinkProfileManager:
    def __init__(self, poll_interval_s: float = 5.0, required_stable: int = 2, cooldown_s: float = 60.0):
        self.poll_interval_s = poll_interval_s
        self.required_stable = required_stable
        self.cooldown_s = cooldown_s

        self._gstreamer_service = None
        self._mavlink_service = None
        self._websocket_manager = None

        self._monitoring = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        self._detected_link: str = "unknown"
        self._detected_interface: str = ""
        self._candidate: str = ""
        self._candidate_count: int = 0

        self._active_profile: str = ""
        self._last_apply_time: float = 0.0
        self._last_actions: list = []
        self._res_cache: Dict[str, set] = {}

        # Read from preferences each cycle; defaults are safe.
        self._telemetry_apply = False
        self._auto_apply_video = True

    # ── Wiring ──────────────────────────────────────────────────────────────

    def set_services(self, gstreamer_service=None, mavlink_service=None, websocket_manager=None):
        self._gstreamer_service = gstreamer_service
        self._mavlink_service = mavlink_service
        self._websocket_manager = websocket_manager

    async def start(self):
        if self._monitoring:
            return
        self._monitoring = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Link Profile Manager started")

    async def stop(self):
        self._monitoring = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("Link Profile Manager stopped")

    # ── Status / manual control ────────────────────────────────────────────

    def _desired_profile(self, settings: Dict[str, Any]) -> str:
        forced = (settings.get("forced") or "").strip()
        if settings.get("mode") == "manual" and forced:
            return forced
        return self._detected_link

    def get_status(self) -> Dict[str, Any]:
        try:
            from app.services.preferences import get_preferences

            settings = get_preferences().get_link_profile_settings()
            profiles = get_preferences().get_link_profiles()
        except Exception:
            settings = {"mode": "auto", "forced": "", "auto_apply": True}
            profiles = {}

        desired = self._desired_profile(settings)
        return {
            "detected_link": self._detected_link,
            "detected_interface": self._detected_interface,
            "active_profile": self._active_profile,
            "desired_profile": desired,
            "mode": settings.get("mode", "auto"),
            "forced": settings.get("forced", ""),
            "auto_apply": settings.get("auto_apply", True),
            "telemetry_apply": self._telemetry_apply,
            "available_profiles": profiles,
            "last_actions": self._last_actions,
            "last_apply_time": self._last_apply_time,
        }

    async def set_override(self, profile_name: str) -> Dict[str, Any]:
        """Manually force a profile ('' to return to auto)."""
        from app.services.preferences import get_preferences

        profile_name = (profile_name or "").strip()
        if profile_name and profile_name not in ("lan", "modem", "vpn"):
            return {"success": False, "message": f"Unknown profile: {profile_name}"}

        prefs = get_preferences()
        if profile_name:
            prefs.set_link_profile_settings(mode="manual", forced=profile_name)
        else:
            prefs.set_link_profile_settings(mode="auto", forced="")

        if profile_name:
            return await self.apply_profile(profile_name, reason="manual")
        return {"success": True, "message": "Link profile set to auto", "profile": ""}

    # ── Monitor loop ───────────────────────────────────────────────────────

    async def _monitor_loop(self):
        # Small initial delay so startup work settles first.
        await asyncio.sleep(3)
        while self._monitoring:
            try:
                await self._tick()
            except Exception as e:
                logger.debug(f"Link profile tick error: {e}")
            await asyncio.sleep(self.poll_interval_s)

    async def _tick(self):
        from app.services.network_event_bridge import detect_primary_interface
        from app.services.preferences import get_preferences

        info = await detect_primary_interface()
        interface = info.get("interface", "")
        link = classify_link_type(interface, info.get("type", ""))
        self._detected_interface = interface
        self._detected_link = link

        # Debounce: require N consecutive identical detections.
        if link != self._candidate:
            self._candidate = link
            self._candidate_count = 1
        else:
            self._candidate_count += 1

        prefs = get_preferences()
        settings = prefs.get_link_profile_settings()
        self._telemetry_apply = bool(
            prefs.get_all_preferences().get("network", {}).get("link_profile_telemetry_apply", False)
        )
        self._auto_apply_video = settings.get("auto_apply", True)

        desired = self._desired_profile(settings)
        if desired == self._active_profile or desired in ("", "unknown"):
            return
        if self._candidate_count < self.required_stable:
            return
        if time.time() - self._last_apply_time < self.cooldown_s and self._active_profile:
            return

        await self.apply_profile(desired, reason="auto")

    # ── Applying a profile ─────────────────────────────────────────────────

    async def apply_profile(self, profile_name: str, reason: str = "auto") -> Dict[str, Any]:
        from app.services.preferences import get_preferences

        profiles = get_preferences().get_link_profiles()
        profile = profiles.get(profile_name)
        if not profile:
            return {"success": False, "message": f"Unknown profile: {profile_name}"}

        async with self._lock:
            actions = []

            if self._auto_apply_video and self._gstreamer_service:
                if self._gstreamer_service.is_streaming:
                    actions.extend(await self._apply_video(profile))
                else:
                    # Not streaming: apply the profile to the configuration so the
                    # next start uses it, without forcing the stream on.
                    await asyncio.to_thread(self._configure_video_only, profile)
                    actions.append("video-config-only")

            if self._telemetry_apply and self._mavlink_service:
                result = await asyncio.to_thread(
                    self._mavlink_service.apply_telemetry_profile, profile.get("telemetry", "full")
                )
                actions.append(f"telemetry:{profile.get('telemetry')}:{'ok' if result.get('success') else 'fail'}")

            buffer_size = int(profile.get("udp_buffer_size") or 0)
            if buffer_size > 0 and self._gstreamer_service:
                applied = await asyncio.to_thread(self._gstreamer_service.set_udp_buffer_size, buffer_size)
                if applied:
                    actions.append(f"udp_buffer:{buffer_size}")

            self._active_profile = profile_name
            self._last_apply_time = time.time()
            self._last_actions = actions

        logger.info(
            "Link profile applied",
            extra={"profile": profile_name, "reason": reason, "actions": actions},
        )

        await self._broadcast_status()
        return {"success": True, "profile": profile_name, "reason": reason, "actions": actions}

    def _supported_resolutions(self, device: str) -> set:
        """Camera resolutions according to v4l2-ctl (cached). Empty = unknown."""
        if not device:
            return set()
        if device in self._res_cache:
            return self._res_cache[device]
        resolutions = set()
        try:
            from app.utils.cmd import run_cmd

            stdout, _, rc = run_cmd(["v4l2-ctl", "-d", device, "--list-formats-ext"], timeout=3, check=False)
            if rc == 0:
                for line in stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Size: Discrete"):
                        resolutions.add(line.split()[-1])
        except Exception as e:
            logger.debug(f"Could not query camera resolutions: {e}")
        self._res_cache[device] = resolutions
        return resolutions

    def _target_resolution(self, profile: Dict[str, Any], cfg) -> tuple:
        """Resolve the profile resolution, falling back to current if unsupported."""
        width = int(profile.get("width", cfg.width))
        height = int(profile.get("height", cfg.height))
        if (width, height) == (cfg.width, cfg.height):
            return width, height, False

        supported = self._supported_resolutions(getattr(cfg, "device", ""))
        if supported and f"{width}x{height}" not in supported:
            logger.info(
                "Profile resolution not supported by camera, keeping current",
                extra={"requested": f"{width}x{height}", "keeping": f"{cfg.width}x{cfg.height}"},
            )
            return cfg.width, cfg.height, True
        return width, height, False

    async def _apply_video(self, profile: Dict[str, Any]) -> list:
        """Apply the profile's video settings, restarting only if needed."""
        service = self._gstreamer_service
        cfg = service.video_config
        current_mode = service.streaming_config.mode

        target_mode = profile.get("video_mode", current_mode)
        width, height, res_unavailable = self._target_resolution(profile, cfg)

        # Use the resolved resolution for the (possible) restart.
        effective_profile = dict(profile)
        effective_profile["width"] = width
        effective_profile["height"] = height

        needs_restart = (
            target_mode != current_mode
            or width != cfg.width
            or height != cfg.height
            or int(profile.get("framerate", cfg.framerate)) != cfg.framerate
        )

        if not needs_restart:
            result = await asyncio.to_thread(
                service.update_live_property, "bitrate", int(profile.get("h264_bitrate", 0))
            )
            actions = []
            if res_unavailable:
                actions.append(f"resolution-kept:{width}x{height}")
            if result.get("success"):
                actions.append(f"bitrate:{profile.get('h264_bitrate')}")
            else:
                actions.append(f"bitrate-failed:{result.get('message')}")
            return actions

        result = await asyncio.to_thread(self._restart_video, effective_profile, target_mode)
        if not (isinstance(result, dict) and result.get("success")):
            message = result.get("message") if isinstance(result, dict) else str(result)
            logger.warning("Link profile video restart failed", extra={"mode": target_mode, "error": message})
            return [f"video-restart-failed:{message}"]
        actions = []
        if res_unavailable:
            actions.append(f"resolution-kept:{width}x{height}")
        actions.append(
            f"video-restart:{target_mode} {width}x{height}@{effective_profile.get('framerate')} "
            f"{effective_profile.get('h264_bitrate')}kbps"
        )
        return actions

    def _video_config_from_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        service = self._gstreamer_service
        return {
            "width": int(profile.get("width", service.video_config.width)),
            "height": int(profile.get("height", service.video_config.height)),
            "framerate": int(profile.get("framerate", service.video_config.framerate)),
            "h264_bitrate": int(profile.get("h264_bitrate", service.video_config.h264_bitrate)),
            "quality": int(profile.get("quality", service.video_config.quality)),
        }

    def _configure_video_only(self, profile: Dict[str, Any]):
        """Apply profile values to the video config without starting the stream."""
        service = self._gstreamer_service
        service.configure(
            video_config=self._video_config_from_profile(profile),
            streaming_config={"mode": profile.get("video_mode", service.streaming_config.mode)},
        )

    def _restart_video(self, profile: Dict[str, Any], mode: str) -> Dict[str, Any]:
        """Reconfigure and restart the video pipeline (blocking, run in a thread)."""
        service = self._gstreamer_service
        service.configure(
            video_config=self._video_config_from_profile(profile),
            streaming_config={"mode": mode},
        )

        if service.is_streaming:
            service.stop()
            # The camera/source needs a moment to be fully released before the
            # new pipeline opens it again, otherwise start fails with a stream
            # error. 0.5 s was not enough on the Radxa; use a safer margin.
            time.sleep(2.5)

        result = service.start()
        retries = 0
        while not (isinstance(result, dict) and result.get("success")) and retries < 2:
            retries += 1
            logger.warning(
                "Video start failed, retrying",
                extra={"mode": mode, "attempt": retries, "result": result},
            )
            time.sleep(1.5)
            result = service.start()
        return result if isinstance(result, dict) else {"success": bool(result)}

    async def _broadcast_status(self):
        if not self._websocket_manager or not getattr(self._websocket_manager, "has_clients", False):
            return
        try:
            await self._websocket_manager.broadcast("link_profile", self.get_status())
        except Exception as e:
            logger.debug(f"Link profile broadcast failed: {e}")


_manager: Optional[LinkProfileManager] = None


def get_link_profile_manager() -> LinkProfileManager:
    global _manager
    if _manager is None:
        _manager = LinkProfileManager()
    return _manager
