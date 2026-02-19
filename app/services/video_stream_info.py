"""
Video Stream Information Service
Sends VIDEO_STREAM_INFORMATION MAVLink message (269) to advertise video stream
compatible with Mission Planner's "Pop-Out or within Map" video detection
"""

import os
import threading
import time
from typing import Optional, TYPE_CHECKING

# MAVLink environment - set before importing pymavlink
os.environ["MAVLINK20"] = "1"
from pymavlink.dialects.v20 import ardupilotmega as mavlink2  # noqa: E402

if TYPE_CHECKING:
    from .mavlink_bridge import MAVLinkBridge
    from .gstreamer_service import GStreamerService


class VideoStreamInfoService:
    """
    Periodically sends MAVLink camera messages to advertise video stream
    parameters. This allows Mission Planner and other GCS to automatically
    detect, display, and control video streams.

    Messages sent:
    - HEARTBEAT (CompID=100 MAV_TYPE_CAMERA) — always, 1Hz
    - CAMERA_INFORMATION (259) — on first connect + every 5s
    - VIDEO_STREAM_INFORMATION (269) — while streaming, 1Hz
    - VIDEO_STREAM_STATUS (270) — while streaming, 1Hz (real-time stats)
    """

    def __init__(
        self,
        mavlink_bridge: Optional["MAVLinkBridge"] = None,
        gstreamer_service: Optional["GStreamerService"] = None,
    ):
        self.mavlink_bridge = mavlink_bridge
        self.gstreamer_service = gstreamer_service

        # Stream parameters
        self.stream_id: int = 1  # First stream
        self.count: int = 1  # Total number of streams
        self.stream_name: str = "FPVCopilotSky Video 1"

        # CAMERA_INFORMATION fields
        self.vendor_name: str = "FPVCopilot"
        self.model_name: str = "FPVCopilotSky"
        self.firmware_version: int = 0x01000000  # 1.0.0.0
        self.focal_length: float = 0.0  # Unknown
        self.sensor_size_h: float = 0.0  # Unknown
        self.sensor_size_v: float = 0.0  # Unknown
        self.cam_definition_uri: str = ""

        # Timing counters
        self._camera_info_counter: int = 0

        # Thread control
        self.running: bool = False
        self.sender_thread: Optional[threading.Thread] = None
        self.send_interval: float = 1.0  # Send every 1 second

    def start(self) -> bool:
        """Start periodically sending VIDEO_STREAM_INFORMATION"""
        if self.running:
            return True

        if not self.mavlink_bridge or not self.gstreamer_service:
            print("⚠️ VideoStreamInfo: MAVLink bridge or GStreamer service not available")
            return False

        self.running = True
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True, name="VideoStreamInfoSender")
        self.sender_thread.start()
        print(
            f"✅ Video Stream Information service started "
            f"(SysID={self.mavlink_bridge.source_system_id}, CompID=100 CAMERA)"
        )
        return True

    def stop(self):
        """Stop sending VIDEO_STREAM_INFORMATION"""
        self.running = False
        if self.sender_thread:
            self.sender_thread.join(timeout=2)
            self.sender_thread = None

    def _sender_loop(self):
        """Periodic sender thread"""
        while self.running:
            try:
                # Always send HEARTBEAT to advertise the CAMERA component
                self._send_camera_heartbeat()

                # Send CAMERA_INFORMATION on first connect then every 5 cycles
                self._camera_info_counter += 1
                if self._camera_info_counter >= 5:
                    self._camera_info_counter = 0
                    self._send_camera_information()

                # Only send stream info + status if streaming is active
                if self.gstreamer_service and self.gstreamer_service.is_streaming:
                    self._send_video_stream_information()
                    self._send_video_stream_status()
            except Exception as e:
                print(f"⚠️ VideoStreamInfo error: {e}")

            time.sleep(self.send_interval)

    def _send_camera_heartbeat(self):
        """Send HEARTBEAT from CAMERA component (CompID=100) - NON-BLOCKING"""
        if not self.mavlink_bridge or not self.mavlink_bridge.serial_port:
            return

        try:
            # Create a separate MAVLink sender for CAMERA component (CompID=100)
            mav_sender_camera = mavlink2.MAVLink(None)
            mav_sender_camera.srcSystem = self.mavlink_bridge.source_system_id
            mav_sender_camera.srcComponent = 100  # MAV_COMP_ID_CAMERA

            # Send HEARTBEAT to announce the CAMERA component
            # type: 30 (MAV_TYPE_CAMERA), autopilot: 0 (GENERIC)
            # base_mode: 0, system_status: 4 (ACTIVE)
            msg = mav_sender_camera.heartbeat_encode(
                type=30,  # MAV_TYPE_CAMERA
                autopilot=0,  # MAV_AUTOPILOT_GENERIC
                base_mode=0,
                custom_mode=0,
                system_status=4,  # MAV_STATE_ACTIVE
            )

            try:
                packed_msg = msg.pack(mav_sender_camera)

                acquired = self.mavlink_bridge.serial_lock.acquire(timeout=0.1)
                if acquired:
                    try:
                        if self.mavlink_bridge.serial_port:
                            self.mavlink_bridge.serial_port.write(packed_msg)
                            # Also broadcast to router
                            if self.mavlink_bridge.router:
                                self.mavlink_bridge.router.forward_to_outputs(packed_msg)
                    finally:
                        self.mavlink_bridge.serial_lock.release()
            except Exception:
                # Silent fail - non-critical
                pass

        except Exception:
            # Silently ignore errors
            pass

    def _send_camera_information(self):
        """Send CAMERA_INFORMATION (259) to advertise camera capabilities - NON-BLOCKING.

        This message tells the GCS what camera is available, its capabilities,
        and how many video streams it supports. Mission Planner uses this to
        show the camera in the \"Camera\" tab.
        """
        if not self.mavlink_bridge or not self.mavlink_bridge.serial_port:
            return

        if not self.mavlink_bridge.connected:
            return

        try:
            mav = mavlink2.MAVLink(None)
            mav.srcSystem = self.mavlink_bridge.source_system_id
            mav.srcComponent = 100  # MAV_COMP_ID_CAMERA

            # Determine camera capabilities flags
            # CAMERA_CAP_FLAGS_CAPTURE_VIDEO = 2
            # CAMERA_CAP_FLAGS_HAS_VIDEO_STREAM = 16
            flags = 2 | 16  # Can capture video + has video stream

            # Resolution from current config
            resolution_h = 0
            resolution_v = 0
            if self.gstreamer_service and self.gstreamer_service.video_config:
                resolution_h = self.gstreamer_service.video_config.width or 0
                resolution_v = self.gstreamer_service.video_config.height or 0

            msg = mav.camera_information_encode(
                time_boot_ms=int(time.time() * 1000) & 0xFFFFFFFF,
                vendor_name=self.vendor_name.encode("utf-8")[:32].ljust(32, b"\x00"),
                model_name=self.model_name.encode("utf-8")[:32].ljust(32, b"\x00"),
                firmware_version=self.firmware_version,
                focal_length=self.focal_length,
                sensor_size_h=self.sensor_size_h,
                sensor_size_v=self.sensor_size_v,
                resolution_h=resolution_h,
                resolution_v=resolution_v,
                lens_id=0,
                flags=flags,
                cam_definition_version=0,
                cam_definition_uri=self.cam_definition_uri.encode("utf-8")[:140],
            )

            packed = msg.pack(mav)
            acquired = self.mavlink_bridge.serial_lock.acquire(timeout=0.1)
            if acquired:
                try:
                    if self.mavlink_bridge.serial_port:
                        self.mavlink_bridge.serial_port.write(packed)
                        if self.mavlink_bridge.router:
                            self.mavlink_bridge.router.forward_to_outputs(packed)
                finally:
                    self.mavlink_bridge.serial_lock.release()
        except Exception:
            pass  # Non-critical

    def _send_video_stream_status(self):
        """Send VIDEO_STREAM_STATUS (270) with real-time streaming stats - NON-BLOCKING.

        Unlike VIDEO_STREAM_INFORMATION (static config), this message carries
        **live** metrics: actual framerate, actual bitrate, and resolution.
        The GCS can use this to show real stream health.
        """
        if not self.mavlink_bridge or not self.gstreamer_service:
            return
        if not self.mavlink_bridge.connected or not self.mavlink_bridge.serial_port:
            return

        try:
            video_config = self.gstreamer_service.video_config
            if not video_config:
                return

            # Get real measured stats from the pipeline
            stats = self.gstreamer_service.stats
            real_fps = stats.get("current_fps", 0)
            real_bitrate = stats.get("current_bitrate", 0)

            # If no measured bitrate yet, use configured
            if real_bitrate <= 0:
                real_bitrate = self._get_real_bitrate_kbps(video_config)

            # Flags: RUNNING (1)
            flags = 1  # VIDEO_STREAM_STATUS_FLAGS_RUNNING

            mav = mavlink2.MAVLink(None)
            mav.srcSystem = self.mavlink_bridge.source_system_id
            mav.srcComponent = 100  # MAV_COMP_ID_CAMERA

            msg = mav.video_stream_status_encode(
                stream_id=self.stream_id,
                flags=flags,
                framerate=float(real_fps) if real_fps > 0 else float(video_config.framerate or 30),
                resolution_h=video_config.width or 960,
                resolution_v=video_config.height or 720,
                bitrate=int(real_bitrate),
                rotation=0,
                hfov=0,
            )

            packed = msg.pack(mav)
            acquired = self.mavlink_bridge.serial_lock.acquire(timeout=0.1)
            if acquired:
                try:
                    if self.mavlink_bridge.serial_port:
                        self.mavlink_bridge.serial_port.write(packed)
                        if self.mavlink_bridge.router:
                            self.mavlink_bridge.router.forward_to_outputs(packed)
                finally:
                    self.mavlink_bridge.serial_lock.release()
        except Exception:
            pass  # Non-critical

    def _get_real_bitrate_kbps(self, video_config) -> int:
        """Get the real encoding bitrate instead of raw video bitrate.

        For H.264 codecs, use the configured bitrate.
        For MJPEG, estimate from quality and resolution.
        Falls back to stats-based measurement if streaming.
        """
        codec = video_config.codec.lower() if video_config.codec else "unknown"

        # H.264 codecs: use the configured bitrate directly
        if "h264" in codec:
            return int(video_config.h264_bitrate or 2000)

        # Try to use real measured bitrate from streaming stats
        if self.gstreamer_service and self.gstreamer_service.is_streaming:
            stats = self.gstreamer_service.stats
            current_bitrate = stats.get("current_bitrate", 0)
            if current_bitrate > 0:
                return int(current_bitrate)

        # MJPEG: estimate from quality and resolution
        # Typical MJPEG: quality 85 at 720p30 ≈ 8-12 Mbps
        if codec == "mjpeg":
            quality = video_config.quality or 85
            pixels = (video_config.width or 960) * (video_config.height or 720)
            fps = video_config.framerate or 30
            # Rough estimate: 0.5-2 bits/pixel depending on quality
            bpp = 0.3 + (quality / 100) * 1.7  # 0.3 at q=0, 2.0 at q=100
            return int((pixels * bpp * fps) / 1000)

        # Fallback: conservative estimate
        return 2000

    def _get_companion_ip(self) -> str:
        """Get this companion computer's IP address dynamically."""
        try:
            if self.gstreamer_service:
                return self.gstreamer_service._get_streaming_ip()
        except Exception:
            pass
        # Fallback: try to determine IP from network interfaces
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _send_video_stream_information(self):
        """Build and send VIDEO_STREAM_INFORMATION message - NON-BLOCKING"""
        if not self.mavlink_bridge or not self.gstreamer_service:
            return

        # Quick safety check without locking
        if not self.mavlink_bridge.connected or not self.mavlink_bridge.serial_port:
            return

        try:
            # Get stream parameters from GStreamer service
            video_config = self.gstreamer_service.video_config
            streaming_config = self.gstreamer_service.streaming_config

            # Avoid accessing if None
            if not video_config or not streaming_config:
                return

            # Video codec to encoding
            codec = video_config.codec.lower() if video_config.codec else "unknown"
            if "h264" in codec:
                encoding = 1  # VIDEO_STREAM_ENCODING_H264
            elif codec == "mjpeg":
                encoding = 2  # VIDEO_STREAM_ENCODING_JPEG (allows GCS to pick correct depayloader)
            else:
                encoding = 0  # VIDEO_STREAM_ENCODING_UNKNOWN

            # Stream type: RTP-UDP
            stream_type = 1  # VIDEO_STREAM_TYPE_RTPUDP

            # Flags: RUNNING (1)
            flags = 1  # VIDEO_STREAM_STATUS_FLAGS_RUNNING

            # Build URI based on active streaming mode
            companion_ip = self._get_companion_ip()
            mode = streaming_config.mode if streaming_config.mode else "udp"
            if mode == "rtsp":
                rtsp_url = streaming_config.rtsp_url or f"rtsp://{companion_ip}:8554/fpv"
                # Replace localhost with real IP for GCS
                if "localhost" in rtsp_url:
                    rtsp_url = rtsp_url.replace("localhost", companion_ip)
                uri = rtsp_url
                stream_type = 2  # VIDEO_STREAM_TYPE_RTSP
            elif mode == "multicast":
                uri = f"udp://{streaming_config.multicast_group}:{streaming_config.multicast_port}"
            else:
                uri = f"udp://{companion_ip}:{streaming_config.udp_port}"
            uri_bytes = uri[:160].encode("utf-8")

            # Create a separate MAVLink sender for CAMERA component (CompID=100)
            # This is independent of the ONBOARD_COMPUTER (CompID=191) HEARTBEAT
            mav_sender_camera = mavlink2.MAVLink(None)
            mav_sender_camera.srcSystem = self.mavlink_bridge.source_system_id
            mav_sender_camera.srcComponent = 100  # MAV_COMP_ID_CAMERA

            msg = mav_sender_camera.video_stream_information_encode(
                stream_id=self.stream_id,
                count=self.count,
                type=stream_type,
                flags=flags,
                framerate=float(video_config.framerate or 30),
                resolution_h=video_config.width or 960,
                resolution_v=video_config.height or 720,
                bitrate=self._get_real_bitrate_kbps(video_config),
                rotation=0,
                hfov=0,
                name=self.stream_name.encode("utf-8")[:32],
                uri=uri_bytes,
                encoding=encoding,
            )

            # Try to send with timeout on lock - NON-BLOCKING
            try:
                packed_msg = msg.pack(mav_sender_camera)

                # Debug: log when we send VIDEO_STREAM_INFORMATION

                acquired = self.mavlink_bridge.serial_lock.acquire(timeout=0.1)
                if acquired:
                    try:
                        if self.mavlink_bridge.serial_port:
                            self.mavlink_bridge.serial_port.write(packed_msg)
                            # Also broadcast to router so Mission Planner receives it
                            if self.mavlink_bridge.router:
                                self.mavlink_bridge.router.forward_to_outputs(packed_msg)
                    finally:
                        self.mavlink_bridge.serial_lock.release()
                # If can't acquire lock, just skip this send - don't block
            except Exception:
                # Silent fail - this is just advisory
                pass

        except Exception:
            # Silently ignore errors in this non-critical service
            pass


# Global instance
_video_stream_info_service: Optional[VideoStreamInfoService] = None


def init_video_stream_info_service(
    mavlink_bridge: Optional["MAVLinkBridge"] = None,
    gstreamer_service: Optional["GStreamerService"] = None,
) -> VideoStreamInfoService:
    """Initialize the video stream info service"""
    global _video_stream_info_service
    _video_stream_info_service = VideoStreamInfoService(mavlink_bridge, gstreamer_service)
    return _video_stream_info_service


def get_video_stream_info_service() -> Optional[VideoStreamInfoService]:
    """Get the global video stream info service instance"""
    return _video_stream_info_service
