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
    Periodically sends VIDEO_STREAM_INFORMATION MAVLink message to advertise
    video stream parameters. This allows Mission Planner and other GCS to
    automatically detect and display video streams.
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

                # Only send VIDEO_STREAM_INFORMATION if streaming is active
                if self.gstreamer_service and self.gstreamer_service.is_streaming:
                    self._send_video_stream_information()
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
            # system_type: 0 (GENERIC), autopilot: 0 (GENERIC)
            # base_mode: 0, system_status: 4 (ACTIVE)
            msg = mav_sender_camera.heartbeat_encode(
                type=0,  # MAV_TYPE_GENERIC
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
            if codec == "h264":
                encoding = 1  # VIDEO_STREAM_ENCODING_H264
            else:
                encoding = 0  # VIDEO_STREAM_ENCODING_UNKNOWN

            # Stream type: RTP-UDP
            stream_type = 1  # VIDEO_STREAM_TYPE_RTPUDP

            # Flags: RUNNING (1)
            flags = 1  # VIDEO_STREAM_STATUS_FLAGS_RUNNING

            # Build URI - use the companion computer's IP address, not the client's
            # Mission Planner will connect back to this address
            companion_ip = "192.168.1.145"  # This companion's IP
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
                bitrate=int(
                    ((video_config.width or 960) * (video_config.height or 720) * (video_config.framerate or 30) * 12)
                    / 1000
                ),
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
                # print(f"📹 Sending VIDEO_STREAM_INFORMATION from CompID=100: {self.stream_name}, URI={uri}")

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
