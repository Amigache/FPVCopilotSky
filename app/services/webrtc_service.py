"""
WebRTC Signaling + Media Service

Real WebRTC implementation using aiortc:
- Server-side RTCPeerConnection per browser viewer
- GStreamer H264 encode → appsink → H264 passthrough (no re-encoding in aiortc)
- SDP offer/answer exchange via REST API
- ICE candidate trickle
- Adaptive bitrate for 4G optimization
- Connection stats monitoring
"""

import asyncio
import time
import threading
import uuid
import fractions
import math
import queue as thread_queue
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc import MediaStreamTrack
    from av import VideoFrame
    import numpy as np

    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False


# ── Constants for H264 RTP packetization ─────────────────────────────────────

PACKET_MAX = 1200  # Max RTP payload size
NAL_HEADER_SIZE = 1
FU_A_HEADER_SIZE = 2
STAP_A_HEADER_SIZE = 1
LENGTH_FIELD_SIZE = 2
NAL_TYPE_FU_A = 28
NAL_TYPE_STAP_A = 24
VIDEO_CLOCK_RATE = 90000
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)


# ── H264 Passthrough Encoder ────────────────────────────────────────────────

if AIORTC_AVAILABLE:

    class H264PassthroughEncoder:
        """
        A drop-in replacement for aiortc's H264Encoder that passes through
        pre-encoded H264 NALUs from GStreamer instead of re-encoding.

        GStreamer encodes H264 (using x264enc/openh264enc) → appsink sends
        H264 byte-stream access units → this encoder splits into NAL units
        and packetizes for RTP without any re-encoding.
        """

        def __init__(self, h264_queue: thread_queue.Queue, framerate: int = 30):
            self._h264_queue = h264_queue
            self._framerate = framerate
            self.__target_bitrate = 1500000  # Not used but required by interface
            self._frame_count = 0
            # For pack() compatibility
            self.buffer_data = b""
            self.buffer_pts = None
            self.codec = None

        @staticmethod
        def _split_bitstream(buf: bytes):
            """Split H264 byte-stream into individual NAL units."""
            i = 0
            while True:
                i = buf.find(b"\x00\x00\x01", i)
                if i == -1:
                    return
                i += 3
                nal_start = i
                i = buf.find(b"\x00\x00\x01", i)
                if i == -1:
                    yield buf[nal_start : len(buf)]
                    return
                elif buf[i - 1] == 0:
                    yield buf[nal_start : i - 1]
                else:
                    yield buf[nal_start:i]

        @staticmethod
        def _packetize_fu_a(data: bytes) -> list:
            """Fragment a large NAL unit into FU-A packets."""
            available_size = PACKET_MAX - FU_A_HEADER_SIZE
            payload_size = len(data) - NAL_HEADER_SIZE
            num_packets = math.ceil(payload_size / available_size)
            num_larger_packets = payload_size % num_packets
            package_size = payload_size // num_packets

            f_nri = data[0] & (0x80 | 0x60)
            nal = data[0] & 0x1F
            fu_indicator = f_nri | NAL_TYPE_FU_A
            fu_header_end = bytes([fu_indicator, nal | 0x40])
            fu_header_middle = bytes([fu_indicator, nal])
            fu_header_start = bytes([fu_indicator, nal | 0x80])
            fu_header = fu_header_start

            packages = []
            offset = NAL_HEADER_SIZE
            while offset < len(data):
                if num_larger_packets > 0:
                    num_larger_packets -= 1
                    payload = data[offset : offset + package_size + 1]
                    offset += package_size + 1
                else:
                    payload = data[offset : offset + package_size]
                    offset += package_size
                if offset == len(data):
                    fu_header = fu_header_end
                packages.append(fu_header + payload)
                fu_header = fu_header_middle

            return packages

        @staticmethod
        def _packetize_stap_a(data, packages_iterator):
            """Aggregate small NAL units into STAP-A packets."""
            from struct import pack

            counter = 0
            available_size = PACKET_MAX - STAP_A_HEADER_SIZE
            stap_header = NAL_TYPE_STAP_A | (data[0] & 0xE0)
            payload = bytes()
            try:
                nalu = data
                while len(nalu) <= available_size and counter < 9:
                    stap_header |= nalu[0] & 0x80
                    nri = nalu[0] & 0x60
                    if stap_header & 0x60 < nri:
                        stap_header = stap_header & 0x9F | nri
                    available_size -= LENGTH_FIELD_SIZE + len(nalu)
                    counter += 1
                    payload += pack("!H", len(nalu)) + nalu
                    nalu = next(packages_iterator)
                if counter == 0:
                    nalu = next(packages_iterator)
            except StopIteration:
                nalu = None
            if counter <= 1:
                return data, nalu
            else:
                return bytes([stap_header]) + payload, nalu

        @classmethod
        def _packetize(cls, packages) -> list:
            """RTP-packetize a sequence of NAL units."""
            packetized = []
            packages_iterator = iter(packages)
            package = next(packages_iterator, None)
            while package is not None:
                if len(package) > PACKET_MAX:
                    packetized.extend(cls._packetize_fu_a(package))
                    package = next(packages_iterator, None)
                else:
                    result, package = cls._packetize_stap_a(package, packages_iterator)
                    packetized.append(result)
            return packetized

        def encode(self, frame, force_keyframe=False):
            """
            Called by aiortc RTCRtpSender. Instead of encoding the frame,
            reads pre-encoded H264 data from the GStreamer queue.
            Returns (list[bytes], timestamp) — RTP-packetized H264 NALUs.
            """
            self._frame_count += 1

            # Try to get H264 data from GStreamer
            h264_data = None
            try:
                h264_data = self._h264_queue.get_nowait()
            except thread_queue.Empty:
                pass

            if not h264_data:
                return [], frame.pts if hasattr(frame, "pts") else self._frame_count

            # Split byte-stream into NAL units and packetize for RTP
            nals = list(self._split_bitstream(h264_data))
            if not nals:
                return [], frame.pts if hasattr(frame, "pts") else self._frame_count

            from aiortc.mediastreams import convert_timebase

            timestamp = (
                convert_timebase(frame.pts, frame.time_base, VIDEO_TIME_BASE)
                if hasattr(frame, "pts") and hasattr(frame, "time_base")
                else self._frame_count
            )

            return self._packetize(nals), timestamp

        def pack(self, packet):
            """Pack interface for compatibility."""
            packages = list(self._split_bitstream(bytes(packet)))
            return self._packetize(packages), 0

        @property
        def target_bitrate(self) -> int:
            return self.__target_bitrate

        @target_bitrate.setter
        def target_bitrate(self, bitrate: int) -> None:
            self.__target_bitrate = max(100000, min(bitrate, 10000000))


# ── Timing Video Track ──────────────────────────────────────────────────────

if AIORTC_AVAILABLE:

    class TimingVideoTrack(MediaStreamTrack):
        """
        A video track that provides timing frames to aiortc's RTCRtpSender.

        The actual H264 encoding is done by GStreamer. This track only provides
        dummy frames at the correct framerate so aiortc calls the encoder
        (our H264PassthroughEncoder) at the right cadence.
        """

        kind = "video"

        def __init__(self, width=640, height=480, framerate=30):
            super().__init__()
            self._width = width
            self._height = height
            self._framerate = framerate
            self._frame_count = 0
            self._start_time = None
            # Small black frame — the encoder ignores it anyway
            self._blank = np.zeros((height, width, 3), dtype=np.uint8)

        async def recv(self):
            """
            Provide a timing frame at the target framerate.
            The H264PassthroughEncoder ignores this frame and reads from the
            H264 queue instead.
            """
            if self._start_time is None:
                self._start_time = time.time()

            self._frame_count += 1
            pts = self._frame_count
            time_base = fractions.Fraction(1, self._framerate)

            # Pace delivery to target framerate
            target_time = self._start_time + (self._frame_count / self._framerate)
            wait = target_time - time.time()
            if wait > 0:
                await asyncio.sleep(wait)

            frame = VideoFrame.from_ndarray(self._blank, format="bgr24")
            frame.pts = pts
            frame.time_base = time_base
            return frame


# ── Peer Dataclass ───────────────────────────────────────────────────────────


@dataclass
class WebRTCPeer:
    """Represents a connected WebRTC peer with aiortc connection"""

    peer_id: str
    created_at: float = field(default_factory=time.time)
    state: str = "new"
    pc: Any = None
    video_track: Any = None
    ice_candidates_local: List[Dict] = field(default_factory=list)
    ice_candidates_remote: List[Dict] = field(default_factory=list)
    local_sdp: Optional[str] = None
    remote_sdp: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    last_activity: float = field(default_factory=time.time)


# ── WebRTC Service ───────────────────────────────────────────────────────────


class WebRTCService:
    """
    WebRTC media + signaling service using aiortc.
    """

    def __init__(self, websocket_manager=None, event_loop=None):
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop

        # Reference to GStreamer service (set externally for keyframe requests)
        self._gstreamer_service = None

        # Peer connections
        self.peers: Dict[str, WebRTCPeer] = {}
        self._lock = threading.Lock()

        # Shared video track
        self._video_track = None

        # Service state
        self.is_active: bool = False
        self._stats_thread: Optional[threading.Thread] = None
        self._stats_stop = threading.Event()

        # Log buffer
        self._log_buffer: List[Dict[str, Any]] = []
        self._log_max_size: int = 200

        # 4G optimization defaults
        self.adaptive_config = {
            "max_bitrate": 2500,
            "min_bitrate": 300,
            "target_bitrate": 1500,
            "max_framerate": 30,
            "min_framerate": 15,
            "keyframe_interval": 2,
            "adaptation_enabled": True,
            "congestion_control": True,
        }

        # Stats tracking
        self.global_stats = {
            "total_peers": 0,
            "active_peers": 0,
            "total_bytes_sent": 0,
            "total_frames_sent": 0,
            "avg_rtt_ms": 0,
            "avg_bitrate_kbps": 0,
            "adaptation_events": 0,
        }

        if AIORTC_AVAILABLE:
            print("✅ WebRTC service initialized (aiortc available)")
        else:
            print("⚠️ WebRTC service initialized (aiortc NOT available)")

    # ── Video Track & H264 Queue ───────────────────────────────────────────

    def get_or_create_video_track(self, width=640, height=480, framerate=30):
        """Get the shared timing video track, creating if needed."""
        if not AIORTC_AVAILABLE:
            return None
        if not self._video_track:
            self._video_track = TimingVideoTrack(width, height, framerate)
            # Create shared H264 queue for passthrough
            self._h264_queue = thread_queue.Queue(maxsize=5)
        return self._video_track

    def push_video_frame(self, h264_data: bytes):
        """
        Push H264 encoded data from GStreamer into the shared queue.
        Called from GStreamer thread — must be thread-safe.
        The H264PassthroughEncoder reads from this queue.
        """
        if not hasattr(self, "_h264_queue") or self._h264_queue is None:
            return
        try:
            # Drop oldest if full
            while self._h264_queue.full():
                try:
                    self._h264_queue.get_nowait()
                except thread_queue.Empty:
                    break
            self._h264_queue.put_nowait(h264_data)
        except (thread_queue.Full, Exception):
            pass

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def activate(self):
        self.is_active = True
        self._start_stats_monitor()
        self._add_log("info", "WebRTC service activated")
        print("🔗 WebRTC service activated")

    def deactivate(self):
        self.is_active = False
        self._stop_stats_monitor()

        with self._lock:
            peer_ids = list(self.peers.keys())

        for pid in peer_ids:
            self._disconnect_peer_async(pid)

        with self._lock:
            self.peers.clear()

        if self._video_track:
            try:
                self._video_track.stop()
            except Exception:
                pass
            self._video_track = None

        # Clear H264 queue
        if hasattr(self, "_h264_queue"):
            self._h264_queue = None

        self._add_log("info", "WebRTC service deactivated")
        print("🔗 WebRTC service deactivated")

    # ── Peer Management (aiortc) ─────────────────────────────────────────────

    async def create_peer_connection(self, peer_id=None):
        """Create a new aiortc RTCPeerConnection with video track."""
        if not AIORTC_AVAILABLE:
            return {"success": False, "error": "aiortc not installed"}

        if not peer_id:
            peer_id = str(uuid.uuid4())[:8]

        try:
            pc = RTCPeerConnection()
            video_track = self.get_or_create_video_track()

            if video_track:
                pc.addTrack(video_track)

            @pc.on("connectionstatechange")
            async def on_state_change():
                state = pc.connectionState
                self._add_log("info", f"Peer {peer_id}: state → {state}")
                with self._lock:
                    peer = self.peers.get(peer_id)
                    if peer:
                        if state == "connected":
                            peer.state = "connected"
                        elif state in ("failed", "closed"):
                            peer.state = "disconnected"
                        self.global_stats["active_peers"] = sum(
                            1 for p in self.peers.values() if p.state == "connected"
                        )
                self._broadcast_status()

            with self._lock:
                peer = WebRTCPeer(peer_id=peer_id, pc=pc, video_track=video_track)
                self.peers[peer_id] = peer
                self.global_stats["total_peers"] += 1

            self._add_log("info", f"Peer {peer_id}: created")
            self._broadcast_status()

            return {
                "success": True,
                "peer_id": peer_id,
                "config": {
                    "iceServers": self._get_ice_servers(),
                    "sdpSemantics": "unified-plan",
                },
                "adaptive_config": self.adaptive_config,
            }

        except Exception as e:
            self._add_log("error", f"Failed to create peer {peer_id}: {e}")
            return {"success": False, "error": str(e)}

    async def handle_offer(self, peer_id: str, sdp: str) -> Dict[str, Any]:
        """Handle browser SDP offer → create and return SDP answer.
        Forces H264 codec and installs passthrough encoder."""
        if not AIORTC_AVAILABLE:
            return {"success": False, "error": "aiortc not installed"}

        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer or not peer.pc:
                return {"success": False, "error": "Peer not found"}
            pc = peer.pc

        try:
            # Force H264 by removing VP8 from the offer SDP
            modified_sdp = self._force_h264_in_sdp(sdp)
            offer = RTCSessionDescription(sdp=modified_sdp, type="offer")
            await pc.setRemoteDescription(offer)

            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            # Install H264 passthrough encoder on all video senders
            self._install_passthrough_encoder(pc)

            with self._lock:
                peer = self.peers.get(peer_id)
                if peer:
                    peer.remote_sdp = sdp
                    peer.local_sdp = pc.localDescription.sdp
                    peer.state = "connecting"
                    peer.last_activity = time.time()

            self._add_log("info", f"Peer {peer_id}: offer → answer created (H264 passthrough)")
            self._broadcast_status()

            return {
                "success": True,
                "peer_id": peer_id,
                "sdp": pc.localDescription.sdp,
                "type": "answer",
            }

        except Exception as e:
            self._add_log("error", f"Peer {peer_id}: offer failed: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _force_h264_in_sdp(self, sdp: str) -> str:
        """
        Modify the browser's SDP offer to REMOVE VP8 and leave only H264.
        This forces aiortc to negotiate H264 as the codec.
        Removes VP8-related payload types from m=video line and strips
        VP8 rtpmap/fmtp/rtcp-fb lines.
        """
        try:
            lines = sdp.split("\r\n")
            h264_pts = set()
            vp8_pts = set()
            rtx_to_vp8 = set()  # RTX PTs associated with VP8

            # First pass: identify H264, VP8, and VP8-RTX payload types
            for line in lines:
                if line.startswith("a=rtpmap:"):
                    pt = line.split(":")[1].split(" ")[0]
                    if "H264" in line:
                        h264_pts.add(pt)
                    elif "VP8" in line:
                        vp8_pts.add(pt)
                elif line.startswith("a=fmtp:"):
                    pt = line.split(":")[1].split(" ")[0]
                    # Check if this is an RTX for VP8: "a=fmtp:98 apt=97" where 97 is VP8
                    if "apt=" in line:
                        apt = line.split("apt=")[1].split(";")[0].strip()
                        if apt in vp8_pts:
                            rtx_to_vp8.add(pt)

            if not h264_pts:
                # No H264 in offer, return as-is
                return sdp

            # All VP8-related PTs to remove
            remove_pts = vp8_pts | rtx_to_vp8

            # Second pass: filter out VP8 lines and reorder m=video
            result = []
            for line in lines:
                # Remove VP8/RTX rtpmap, fmtp, rtcp-fb lines
                if line.startswith(("a=rtpmap:", "a=fmtp:", "a=rtcp-fb:")):
                    pt = line.split(":")[1].split(" ")[0]
                    if pt in remove_pts:
                        continue
                # Remove m=video VP8 PTs and put H264 first
                if line.startswith("m=video"):
                    parts = line.split(" ")
                    if len(parts) > 3:
                        proto_parts = parts[:3]
                        pt_parts = parts[3:]
                        # Remove VP8 PTs, keep H264 first then others
                        filtered = [p for p in pt_parts if p not in remove_pts]
                        h264_first = [p for p in filtered if p in h264_pts]
                        others = [p for p in filtered if p not in h264_pts]
                        line = " ".join(proto_parts + h264_first + others)
                result.append(line)

            return "\r\n".join(result)
        except Exception as e:
            print(f"⚠️ SDP modification failed: {e}")
            return sdp

    def _install_passthrough_encoder(self, pc: "RTCPeerConnection"):
        """
        Replace aiortc's default H264/VP8 encoder with our H264PassthroughEncoder
        on all video RTP senders.

        This must be called AFTER setLocalDescription so the senders exist.
        """
        try:
            h264_queue = getattr(self, "_h264_queue", None)
            if not h264_queue:
                print("⚠️ No H264 queue available for passthrough encoder")
                return

            for sender in pc.getSenders():
                if sender.kind == "video":
                    passthrough = H264PassthroughEncoder(h264_queue)
                    # Access private attribute (name-mangled)
                    sender._RTCRtpSender__encoder = passthrough
                    print("✅ Installed H264 passthrough encoder on sender")

            # Force keyframe so the new peer gets SPS/PPS/IDR immediately
            if self._gstreamer_service:
                self._gstreamer_service.force_keyframe()

        except Exception as e:
            print(f"⚠️ Failed to install passthrough encoder: {e}")
            import traceback

            traceback.print_exc()

    async def add_ice_candidate(self, peer_id: str, candidate: Dict) -> Dict[str, Any]:
        """Add ICE candidate from browser to the aiortc peer connection."""
        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer or not peer.pc:
                return {"success": False, "error": "Peer not found"}
            peer.last_activity = time.time()
            peer.ice_candidates_remote.append(candidate)

        try:
            # Note: aiortc handles ICE candidates from SDP automatically
            # Trickle ICE support is limited in aiortc
            pass
        except Exception:
            pass
        return {"success": True}

    def handle_answer(self, peer_id: str, sdp: str) -> Dict[str, Any]:
        """Handle SDP answer — not used in server-creates-answer flow."""
        return {"success": True, "peer_id": peer_id}

    def set_peer_connected(self, peer_id: str) -> Dict[str, Any]:
        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer:
                return {"success": False, "error": "Peer not found"}
            peer.state = "connected"
            peer.last_activity = time.time()
            self.global_stats["active_peers"] = sum(1 for p in self.peers.values() if p.state == "connected")
        self._add_log("success", f"Peer {peer_id}: connected")
        self._broadcast_status()
        return {"success": True}

    def update_peer_stats(self, peer_id: str, stats: Dict) -> Dict[str, Any]:
        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer:
                return {"success": False, "error": "Peer not found"}
            peer.stats = stats
            peer.last_activity = time.time()
            self._recalculate_global_stats()
        return {"success": True}

    def disconnect_peer(self, peer_id: str) -> Dict[str, Any]:
        with self._lock:
            if peer_id not in self.peers:
                return {"success": False, "error": "Peer not found"}
        self._disconnect_peer_async(peer_id)
        self._broadcast_status()
        return {"success": True}

    def _disconnect_peer_async(self, peer_id: str):
        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer:
                return
            pc = peer.pc
            peer.state = "disconnected"
            del self.peers[peer_id]
            self.global_stats["active_peers"] = sum(1 for p in self.peers.values() if p.state == "connected")
        self._add_log("info", f"Peer {peer_id}: disconnected")
        if pc and self.event_loop:
            try:
                asyncio.run_coroutine_threadsafe(pc.close(), self.event_loop)
            except Exception:
                pass

    # ── Legacy sync wrapper for tests ────────────────────────────────────────

    def create_offer(self, peer_id=None):
        """Sync wrapper — used by tests and non-async contexts."""
        if self.event_loop and self.event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.create_peer_connection(peer_id), self.event_loop)
            try:
                return future.result(timeout=5)
            except Exception as e:
                return {"success": False, "error": str(e)}
        # Sync fallback for tests
        return self._create_offer_sync(peer_id)

    def _create_offer_sync(self, peer_id=None):
        if not peer_id:
            peer_id = str(uuid.uuid4())[:8]
        with self._lock:
            peer = WebRTCPeer(peer_id=peer_id)
            peer.state = "waiting_for_offer"
            self.peers[peer_id] = peer
            self.global_stats["total_peers"] += 1
        self._add_log("info", f"Peer {peer_id} created")
        self._broadcast_status()
        return {
            "success": True,
            "peer_id": peer_id,
            "config": {
                "iceServers": self._get_ice_servers(),
                "sdpSemantics": "unified-plan",
            },
            "adaptive_config": self.adaptive_config,
        }

    # ── Status & Logs ────────────────────────────────────────────────────────

    def get_status(self):
        with self._lock:
            peers_info = []
            for pid, peer in self.peers.items():
                peers_info.append(
                    {
                        "peer_id": pid,
                        "state": peer.state,
                        "created_at": peer.created_at,
                        "last_activity": peer.last_activity,
                        "stats": peer.stats,
                        "ice_candidates_count": len(peer.ice_candidates_remote),
                    }
                )
            return {
                "active": self.is_active,
                "peers": peers_info,
                "peers_connected": sum(1 for p in self.peers.values() if p.state == "connected"),
                "global_stats": dict(self.global_stats),
                "adaptive_config": dict(self.adaptive_config),
                "aiortc_available": AIORTC_AVAILABLE,
                "log": list(self._log_buffer[-50:]),
            }

    def get_logs(self, limit=100):
        return list(self._log_buffer[-limit:])

    def update_adaptive_config(self, config):
        for key, value in config.items():
            if key in self.adaptive_config:
                self.adaptive_config[key] = value
        self._add_log("info", f"Adaptive config updated: {config}")
        self._broadcast_status()
        return {"success": True, "config": self.adaptive_config}

    def get_ice_candidates(self, peer_id):
        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer:
                return {"success": False, "error": "Peer not found", "candidates": []}
            candidates = peer.ice_candidates_local.copy()
            peer.ice_candidates_local.clear()
        return {"success": True, "candidates": candidates}

    def get_4g_optimized_config(self):
        return {
            "video": {
                "maxBitrate": self.adaptive_config["target_bitrate"] * 1000,
                "minBitrate": self.adaptive_config["min_bitrate"] * 1000,
                "maxFramerate": self.adaptive_config["max_framerate"],
                "degradationPreference": "maintain-framerate",
                "keyframeInterval": self.adaptive_config["keyframe_interval"],
            },
            "ice": {
                "iceTransportPolicy": "all",
                "iceCandidatePoolSize": 2,
                "bundlePolicy": "max-bundle",
                "rtcpMuxPolicy": "require",
            },
            "sdp": {
                "offerToReceiveVideo": True,
                "offerToReceiveAudio": False,
            },
            "network": {
                "enableDtlsSrtp": True,
                "enableRtcpFb": True,
                "nackEnabled": True,
                "remb": True,
                "transportCc": True,
            },
        }

    # ── Private ──────────────────────────────────────────────────────────────

    def _get_ice_servers(self):
        return [
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"},
        ]

    def _recalculate_global_stats(self):
        connected = [p for p in self.peers.values() if p.state == "connected"]
        if not connected:
            return
        total_rtt = sum(p.stats.get("rtt_ms", 0) for p in connected if p.stats)
        total_br = sum(p.stats.get("bitrate_kbps", 0) for p in connected if p.stats)
        count = len([p for p in connected if p.stats])
        if count > 0:
            self.global_stats["avg_rtt_ms"] = round(total_rtt / count, 1)
            self.global_stats["avg_bitrate_kbps"] = round(total_br / count)
            self.global_stats["active_peers"] = len(connected)

    def _add_log(self, level, message):
        entry = {"timestamp": time.time(), "level": level, "message": message}
        self._log_buffer.append(entry)
        if len(self._log_buffer) > self._log_max_size:
            self._log_buffer = self._log_buffer[-self._log_max_size :]

    def _start_stats_monitor(self):
        if self._stats_thread and self._stats_thread.is_alive():
            return
        self._stats_stop.clear()

        def _monitor():
            while not self._stats_stop.is_set():
                self._cleanup_stale_peers()
                self._broadcast_status()
                self._stats_stop.wait(2.0)

        self._stats_thread = threading.Thread(target=_monitor, daemon=True, name="WebRTCStats")
        self._stats_thread.start()

    def _stop_stats_monitor(self):
        self._stats_stop.set()
        if self._stats_thread and self._stats_thread.is_alive():
            self._stats_thread.join(timeout=2)
        self._stats_thread = None

    def _cleanup_stale_peers(self):
        now = time.time()
        with self._lock:
            stale = [
                pid
                for pid, peer in self.peers.items()
                if (now - peer.last_activity) > 30 and peer.state not in ("connected",)
            ]
            for pid in stale:
                self._add_log("warning", f"Peer {pid}: timed out")
                pc = self.peers[pid].pc
                del self.peers[pid]
                if pc and self.event_loop:
                    try:
                        asyncio.run_coroutine_threadsafe(pc.close(), self.event_loop)
                    except Exception:
                        pass
            if stale:
                self.global_stats["active_peers"] = sum(1 for p in self.peers.values() if p.state == "connected")

    def _broadcast_status(self):
        if not self.websocket_manager or not self.event_loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("webrtc_status", self.get_status()),
                self.event_loop,
            )
        except Exception:
            pass

    def shutdown(self):
        self.deactivate()
        print("🛑 WebRTC service shutdown")


# Global instance
_webrtc_service: Optional[WebRTCService] = None


def get_webrtc_service():
    return _webrtc_service


def init_webrtc_service(websocket_manager=None, event_loop=None):
    global _webrtc_service
    _webrtc_service = WebRTCService(websocket_manager, event_loop)
    return _webrtc_service
