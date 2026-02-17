"""
GStreamer Video Streaming Service
Supports MJPEG and H.264 encoding with UDP/RTP output for Mission Planner
Optimized for ultra-low latency FPV streaming
Uses provider-based architecture for codec-agnostic encoding
"""

import logging
import os
import threading
import asyncio
import queue
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import numpy (required for OpenCV frame processing)
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

# Check if GStreamer is available
try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    GSTREAMER_AVAILABLE = True
except (ImportError, ValueError):
    GSTREAMER_AVAILABLE = False
    Gst = None
    GLib = None

from .video_config import (  # noqa: E402
    VideoConfig,
    StreamingConfig,
    auto_detect_camera,
)
from .rtsp_server import RTSPServer  # noqa: E402


class GStreamerService:
    """
    GStreamer video streaming service with:
    - UVC camera input
    - MJPEG or H.264 encoding (configurable)
    - UDP/RTP output for Mission Planner
    - Low-latency optimizations
    """

    def __init__(self, websocket_manager=None, event_loop=None, webrtc_service=None):
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop
        self.webrtc_service = webrtc_service

        # Configuration
        self.video_config = VideoConfig()
        self.streaming_config = StreamingConfig()

        # GStreamer state
        self.pipeline: Optional[Any] = None
        self.main_loop: Optional[Any] = None
        self.main_loop_thread: Optional[threading.Thread] = None
        self.is_streaming: bool = False
        self.last_error: Optional[str] = None
        self.stats_thread: Optional[threading.Thread] = None
        self.stats_stop_event = threading.Event()

        # Provider tracking
        self.current_encoder_provider: Optional[str] = None
        self.current_source_provider: Optional[str] = None

        # RTSP Server for RTSP streaming mode
        self.rtsp_server: Optional[RTSPServer] = None
        self._rtsp_stats_thread: Optional[threading.Thread] = None
        self._rtsp_stats_running: bool = False
        self._rtsp_monitor_thread: Optional[threading.Thread] = None
        self._rtsp_monitor_running: bool = False

        # OpenCV service for video processing
        self._opencv_service = None
        self._opencv_thread = None
        self._opencv_running = False
        self._opencv_queue = None
        self._opencv_appsrc = None
        self._opencv_frames_processed = 0
        self._opencv_frames_dropped = 0

        # WebRTC-OpenCV integration
        self._webrtc_opencv_appsink_idx = -1

        # WebRTC integration
        self.webrtc_adapter = None

        # Statistics - counters for real-time metrics
        self.stats = {
            "frames_sent": 0,
            "bytes_sent": 0,
            "errors": 0,
            "start_time": None,
            "last_stats_time": None,
            "last_frames_count": 0,
            "last_bytes_count": 0,
            "current_fps": 0,
            "current_bitrate": 0,
        }

        # Encoder-specific statistics (populated via pad probes)
        self.encoder_stats = {
            "frames_encoded": 0,
            "frames_dropped_pre_encoder": 0,
            "frames_dropped_post_encoder": 0,
            "total_encode_time_ms": 0,
            "avg_encode_time_ms": 0.0,
            "max_encode_time_ms": 0.0,
            "last_frame_size_bytes": 0,
            "keyframes_sent": 0,
            "pframes_sent": 0,
            "avg_frame_size_bytes": 0,
        }

        # Timestamps for encode time calculation
        self._encode_start_time: float = 0
        self._encoder_probe_ids: list = []

        # Thread lock for stats
        import threading as th

        self.stats_lock = th.Lock()

        # IP address cache to avoid excessive logging and recalculation
        self._cached_ip: Optional[str] = None
        self._cached_ip_time: float = 0
        self._cached_ip_ttl: int = 30  # Cache IP for 30 seconds

        # Initialize GStreamer if available
        if GSTREAMER_AVAILABLE:
            Gst.init(None)

    def set_opencv_service(self, opencv_service):
        """Set OpenCV service for video processing"""
        self._opencv_service = opencv_service
        # If RTSP server already exists, connect it
        if self.rtsp_server:
            self.rtsp_server.set_opencv_service(opencv_service)
        print("✅ OpenCV service connected to video stream service")

    def _is_opencv_enabled(self) -> bool:
        """Check if OpenCV processing is enabled and configured (filter or OSD)"""
        if not self._opencv_service:
            return False
        if not self._opencv_service.is_available():
            # OpenCV not installed - silently return False
            return False
        if not self._opencv_service.is_enabled():
            return False
        config = self._opencv_service.get_config()
        filter_type = config.get("filter", "none")
        osd_enabled = config.get("osd_enabled", False)
        return filter_type != "none" or osd_enabled

    def _create_opencv_processing_elements(self, pipeline, width, height, framerate):
        """Create appsink and appsrc elements for OpenCV processing"""
        try:
            # Create appsink to capture frames
            appsink = Gst.ElementFactory.make("appsink", "opencv_sink")
            appsink.set_property("emit-signals", True)
            appsink.set_property("max-buffers", 2)  # Keep queue small
            appsink.set_property("drop", True)  # Drop old frames if processing is slow
            appsink.set_property("sync", False)  # Don't sync to clock

            # Set explicit BGR caps for OpenCV processing
            caps_str = f"video/x-raw,format=BGR,width={width},height={height},framerate={framerate}/1"
            caps = Gst.Caps.from_string(caps_str)
            appsink.set_property("caps", caps)

            print(f"   📥 OpenCV appsink configured: {width}x{height}@{framerate}fps, BGR format")

            # Connect callback
            appsink.connect("new-sample", self._on_opencv_new_sample)

            # Create appsrc to push processed frames
            appsrc = Gst.ElementFactory.make("appsrc", "opencv_src")
            appsrc.set_property("format", Gst.Format.TIME)
            appsrc.set_property("is-live", True)
            appsrc.set_property("do-timestamp", True)  # TRUE for live sources
            # Set explicit BGR caps for proper negotiation
            caps_bgr_str = f"video/x-raw,format=BGR,width={width},height={height},framerate={framerate}/1"
            caps_bgr = Gst.Caps.from_string(caps_bgr_str)
            appsrc.set_property("caps", caps_bgr)
            appsrc.set_property("stream-type", 0)  # GST_APP_STREAM_TYPE_STREAM
            appsrc.set_property("max-bytes", 0)  # No limit
            appsrc.set_property("block", False)  # Non-blocking
            # CRITICAL: Set latency to -1 (unlimited) so it doesn't block preroll
            appsrc.set_property("min-latency", -1)
            appsrc.set_property("max-latency", -1)

            print("   📤 OpenCV appsrc configured with explicit BGR caps")

            pipeline.add(appsink)
            pipeline.add(appsrc)

            self._opencv_appsrc = appsrc

            return appsink, appsrc

        except Exception as e:
            print(f"❌ Failed to create OpenCV elements: {e}")
            import traceback

            traceback.print_exc()
            return None, None

    def _push_initial_frame_to_appsrc(self, width, height):
        """Push an initial black frame to appsrc to unblock pipeline preroll.

        GStreamer requires appsrc to have at least one buffer available during
        the PAUSED state (preroll phase) before it can transition to PLAYING.
        Without this, the pipeline deadlocks waiting for appsrc data.
        """
        if not self._opencv_appsrc or not NUMPY_AVAILABLE:
            return

        try:
            # Create black BGR frame
            black_frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame_bytes = black_frame.tobytes()

            # Create GStreamer buffer
            buf = Gst.Buffer.new_allocate(None, len(frame_bytes), None)
            buf.fill(0, frame_bytes)
            buf.pts = 0
            buf.duration = Gst.CLOCK_TIME_NONE

            # Push buffer to appsrc via push-buffer signal
            self._opencv_appsrc.emit("push-buffer", buf)

        except Exception as e:
            logger.warning(f"Failed to push initial frame: {e}")

    def _on_opencv_new_sample(self, appsink):
        """Callback when new frame is available from appsink"""
        if not NUMPY_AVAILABLE:
            return Gst.FlowReturn.OK

        try:
            sample = appsink.emit("pull-sample")
            if not sample:
                print("❌ No sample from appsink")
                return Gst.FlowReturn.ERROR

            buf = sample.get_buffer()
            caps = sample.get_caps()

            if not buf or not caps:
                print("❌ Invalid buffer or caps")
                return Gst.FlowReturn.ERROR

            # Extract frame data
            success, map_info = buf.map(Gst.MapFlags.READ)
            if not success:
                print("❌ Failed to map buffer")
                return Gst.FlowReturn.ERROR

            # Get dimensions from caps
            struct = caps.get_structure(0)
            width = struct.get_value("width")
            height = struct.get_value("height")

            # Get format info to handle different pixel formats
            format_str = struct.get_value("format")

            # Determine number of channels based on format
            channels = 3
            if format_str in ["RGBA", "BGRA"]:
                channels = 4
            elif format_str in ["RGB", "BGR"]:
                channels = 3
            elif format_str in ["GRAY8"]:
                channels = 1

            # Verify buffer size matches expected
            expected_size = height * width * channels
            actual_size = map_info.size
            if actual_size != expected_size:
                print(f"⚠️ Buffer size mismatch: expected {expected_size}, got {actual_size}")

            # Convert to numpy array with correct dimensions
            frame_data = np.ndarray(shape=(height, width, channels), dtype=np.uint8, buffer=map_info.data)

            # Copy frame data and ensure C-contiguous (important for OpenCV!)
            frame = np.ascontiguousarray(frame_data)

            buf.unmap(map_info)

            # Intelligent frame skipping: prioritize frames with OSD changes
            if self._opencv_queue:
                try:
                    # Check if this frame has important OSD updates
                    has_osd_update = False
                    if self._opencv_service:
                        has_osd_update = self._opencv_service.has_osd_changed()

                    self._opencv_queue.put_nowait(
                        {
                            "frame": frame,
                            "pts": buf.pts,
                            "duration": buf.duration,
                            "timestamp": time.time(),
                            "priority": 1 if has_osd_update else 0,
                        }
                    )
                except queue.Full:
                    # Queue full - apply intelligent frame skipping
                    # If this frame has OSD updates, try to make room by dropping older low-priority frames
                    if self._opencv_service and self._opencv_service.has_osd_changed():
                        # Try to drop a low-priority frame to make room
                        try:
                            old_frame = self._opencv_queue.get_nowait()
                            if old_frame.get("priority", 0) == 0:
                                # Dropped low-priority frame, queue this high-priority one
                                self._opencv_queue.put_nowait(
                                    {
                                        "frame": frame,
                                        "pts": buf.pts,
                                        "duration": buf.duration,
                                        "timestamp": time.time(),
                                        "priority": 1,
                                    }
                                )
                                self._opencv_frames_dropped += 1
                            else:
                                # Both are high priority, put the old one back and drop this one
                                self._opencv_queue.put_nowait(old_frame)
                                self._opencv_frames_dropped += 1
                        except queue.Empty:
                            self._opencv_frames_dropped += 1
                    else:
                        # Low priority frame and queue full - just drop it
                        self._opencv_frames_dropped += 1

            return Gst.FlowReturn.OK

        except Exception as e:
            print(f"❌ Error in OpenCV callback: {e}")
            import traceback

            traceback.print_exc()
            return Gst.FlowReturn.ERROR

    def _opencv_processing_loop(self):
        """Thread loop that processes frames with OpenCV"""
        print("🎨 OpenCV processing thread started")
        frame_count = 0

        while self._opencv_running:
            try:
                # Get frame from queue with timeout
                frame_data = self._opencv_queue.get(timeout=0.5)

                frame = frame_data["frame"]
                pts = frame_data["pts"]
                duration = frame_data["duration"]

                # Validate frame
                if frame is None or not isinstance(frame, np.ndarray):
                    continue

                # Process with OpenCV
                try:
                    processed_frame = self._opencv_service.process_frame(frame)
                except Exception as e:
                    print(f"❌ Frame {frame_count}: Processing failed: {e}")
                    import traceback

                    traceback.print_exc()
                    continue

                # Validate processed frame
                if processed_frame is None or not isinstance(processed_frame, np.ndarray):
                    print(f"❌ Frame {frame_count}: Invalid frame after processing")
                    continue

                print(f"   Frame {frame_count}: Output valid, shape={processed_frame.shape}")

                # Ensure frame is C-contiguous before converting to bytes
                if not processed_frame.flags["C_CONTIGUOUS"]:
                    print(f"   Frame {frame_count}: Making contiguous")
                    processed_frame = np.ascontiguousarray(processed_frame)

                self._opencv_frames_processed += 1

                # Convert back to bytes
                try:
                    frame_bytes = processed_frame.tobytes()
                    print(f"   Frame {frame_count}: Converted to bytes, size={len(frame_bytes)}")
                except Exception as e:
                    print(f"❌ Frame {frame_count}: Failed to convert to bytes: {e}")
                    continue

                # Create GStreamer buffer
                buf = Gst.Buffer.new_allocate(None, len(frame_bytes), None)
                if buf is None:
                    print(f"❌ Frame {frame_count}: Failed to create GStreamer buffer")
                    continue

                buf.fill(0, frame_bytes)
                buf.pts = pts
                buf.duration = duration

                print(f"   Frame {frame_count}: GStreamer buffer created, size={buf.get_size()}")

                # Push to appsrc
                if self._opencv_appsrc:
                    try:
                        ret = self._opencv_appsrc.emit("push-buffer", buf)
                        if ret == Gst.FlowReturn.OK:
                            print(f"   Frame {frame_count}: ✅ Pushed to appsrc")
                        else:
                            print(f"❌ Frame {frame_count}: Failed to push buffer, return code: {ret}")
                    except Exception as e:
                        print(f"❌ Frame {frame_count}: Exception pushing buffer: {e}")
                else:
                    print(f"❌ Frame {frame_count}: appsrc is None")

                frame_count += 1

            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error in OpenCV processing loop: {e}")
                import traceback

                traceback.print_exc()
                time.sleep(0.01)  # Brief pause on error

        print(f"🎨 OpenCV processing thread stopped (processed {frame_count} frames)")

    def _start_opencv_processing_thread(self):
        """Start the OpenCV processing thread"""
        if self._opencv_running:
            return

        self._opencv_queue = queue.Queue(maxsize=2)  # Small queue to minimize latency
        self._opencv_running = True
        self._opencv_frames_processed = 0
        self._opencv_frames_dropped = 0

        self._opencv_thread = threading.Thread(target=self._opencv_processing_loop, daemon=True)
        self._opencv_thread.start()

        print("✅ OpenCV processing thread started")

    def _stop_opencv_processing_thread(self):
        """Stop the OpenCV processing thread"""
        if not self._opencv_running:
            return

        self._opencv_running = False

        if self._opencv_thread and self._opencv_thread.is_alive():
            self._opencv_thread.join(timeout=2)

        if self._opencv_frames_processed > 0:
            processed = self._opencv_frames_processed
            dropped = self._opencv_frames_dropped
            print(f"📊 OpenCV stats: {processed} frames processed, {dropped} dropped")

        self._opencv_thread = None
        self._opencv_queue = None
        self._opencv_appsrc = None

    def is_available(self) -> bool:
        """Check if GStreamer is available"""
        return GSTREAMER_AVAILABLE

    def configure(self, video_config: dict = None, streaming_config: dict = None):
        """Update configuration"""
        if video_config:
            for key, value in video_config.items():
                if hasattr(self.video_config, key):
                    setattr(self.video_config, key, value)
            # Clear last error when config changes
            self.last_error = None

        if streaming_config:
            for key, value in streaming_config.items():
                if hasattr(self.streaming_config, key):
                    setattr(self.streaming_config, key, value)

        print(
            f"📹 Video config updated: "
            f"{self.video_config.width}x{self.video_config.height}@{self.video_config.framerate}fps"
        )

        # Log streaming destination based on mode
        mode = self.streaming_config.mode
        if mode == "udp":
            host = self.streaming_config.udp_host
            port = self.streaming_config.udp_port
            print(f"📡 Streaming mode: UDP unicast → {host}:{port}")
        elif mode == "multicast":
            group = self.streaming_config.multicast_group
            mport = self.streaming_config.multicast_port
            print(f"📡 Streaming mode: UDP multicast → {group}:{mport}")
        elif mode == "rtsp":
            print(f"📡 Streaming mode: RTSP Server → {self.streaming_config.rtsp_url}")
        else:
            print(f"📡 Streaming mode: {mode}")

        # Broadcast updated status
        self._broadcast_status()

    def build_pipeline(self) -> bool:
        """Build the pipeline using provider architecture"""
        if not GSTREAMER_AVAILABLE:
            self.last_error = "GStreamer not available"
            return False

        # Log board detection info at pipeline build
        try:
            from app.providers.board import BoardRegistry

            detected_board = BoardRegistry().get_detected_board()
            if detected_board:
                print(f"\n🎯 Building video pipeline for: {detected_board.board_name}")
                print(f"   - Variant: {detected_board.variant.name}")
                print(f"   - Available encoders: {', '.join([f.value for f in detected_board.variant.video_encoders])}")
                print(f"   - Available sources: {', '.join([f.value for f in detected_board.variant.video_sources])}")
        except Exception as e:
            print(f"   (Board info unavailable: {e})")

        # WebRTC mode uses its own lightweight pipeline (camera → jpegenc → appsink)
        if self.streaming_config.mode == "webrtc":
            return self._build_webrtc_pipeline()

        codec_id = self.video_config.codec.lower()

        # Adapt codec based on board capabilities
        codec_id = self._adapt_codec_to_board(codec_id)

        # Build pipeline using provider
        return self._build_pipeline_from_provider(codec_id)

    # ── WebRTC Pipeline ────────────────────────────────────────────────────

    def _build_webrtc_pipeline(self) -> bool:
        """
        Build a pipeline for WebRTC mode with H264 encoding.

        Pipeline: source → [jpegdec if MJPEG] → videoconvert → x264enc (ultrafast/zerolatency) → h264parse → appsink

        H264 NALUs are pulled from the appsink and fed into the aiortc
        H264PassthroughEncoder for WebRTC transport without re-encoding.

        NOTE: OpenCV processing is NOT supported in WebRTC mode because:
        - WebRTC pipeline sends H.264-encoded data to appsink
        - OpenCV can only process raw video frames, not H.264 streams
        - OSD would need to be applied before encoding, breaking WebRTC H.264 passthrough
        - For OSD/filtering, use UDP Unicast or Multicast modes instead
        """
        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            pipeline = Gst.Pipeline.new("fpv-webrtc-pipeline")

            # ── Find video source provider ──
            source_provider = None
            for source_type in registry.list_video_source_providers():
                sp = registry.get_video_source(source_type)
                if sp and sp.is_available():
                    sources = sp.discover_sources()
                    for src in sources:
                        if src["device"] == self.video_config.device:
                            source_provider = sp
                            break
                    if source_provider:
                        break

            if not source_provider:
                source_provider = registry.get_video_source("v4l2")

            if not source_provider:
                self.last_error = "No video source provider available"
                return False

            self.current_source_provider = source_provider.display_name

            config = {
                "width": self.video_config.width,
                "height": self.video_config.height,
                "framerate": self.video_config.framerate,
                "bitrate": self.video_config.h264_bitrate,
                "quality": self.video_config.quality,
            }

            source_config = source_provider.build_source_element(self.video_config.device, config)
            if not source_config["success"]:
                self.last_error = source_config.get("error", "Failed to build source")
                return False

            # ── Create source element ──
            src_cfg = source_config["source_element"]
            source = Gst.ElementFactory.make(src_cfg["element"], src_cfg["name"])
            if not source:
                self.last_error = f"Failed to create {src_cfg['element']}"
                return False
            for prop, val in src_cfg["properties"].items():
                source.set_property(prop, val)
            pipeline.add(source)
            elements = [source]

            # ── Caps filter (from source provider) ──
            if source_config.get("caps_filter"):
                caps_elem = Gst.ElementFactory.make("capsfilter", "caps_filter")
                caps_elem.set_property("caps", Gst.Caps.from_string(source_config["caps_filter"]))
                pipeline.add(caps_elem)
                elements.append(caps_elem)

            # ── Post-source elements (e.g. videoconvert from source provider) ──
            for elem_cfg in source_config.get("post_elements", []):
                element = Gst.ElementFactory.make(elem_cfg["element"], elem_cfg["name"])
                if not element:
                    self.last_error = f"Failed to create {elem_cfg['element']}"
                    return False
                for prop, val in elem_cfg.get("properties", {}).items():
                    element.set_property(prop, val)
                pipeline.add(element)
                elements.append(element)

            # ── Determine if source is MJPEG — need to decode first ──
            output_format = source_config.get("output_format", "")
            caps_filter_str = source_config.get("caps_filter", "")
            source_is_jpeg = "image/jpeg" in output_format or "image/jpeg" in caps_filter_str

            if source_is_jpeg:
                # MJPEG source → decode JPEG to raw video
                print("   → Source outputs MJPEG, adding jpegdec")
                jpegdec = Gst.ElementFactory.make("jpegdec", "webrtc_jpegdec")
                if not jpegdec:
                    self.last_error = "jpegdec GStreamer plugin not available"
                    return False
                pipeline.add(jpegdec)
                elements.append(jpegdec)

            # ── videoconvert → ensure correct pixel format for encoder ──
            videoconvert = Gst.ElementFactory.make("videoconvert", "webrtc_convert")
            pipeline.add(videoconvert)
            elements.append(videoconvert)

            # ── OpenCV processing layer (BEFORE encoder - works for all streaming modes) ──
            opencv_appsink = None
            opencv_appsrc = None
            opencv_appsink_idx = -1
            if self._is_opencv_enabled():
                print("   → OpenCV processing ENABLED")
                w = self.video_config.width
                h = self.video_config.height
                fps = self.video_config.framerate

                opencv_appsink, opencv_appsrc = self._create_opencv_processing_elements(pipeline, w, h, fps)

                if opencv_appsink and opencv_appsrc:
                    # Add capsfilter to force BGR conversion BEFORE appsink
                    capsfilter_bgr = Gst.ElementFactory.make("capsfilter", "opencv_capsfilter")
                    if capsfilter_bgr:
                        cap_str = f"video/x-raw,format=BGR,width={w},height={h},framerate={fps}/1"
                        caps = Gst.Caps.from_string(cap_str)
                        capsfilter_bgr.set_property("caps", caps)
                        pipeline.add(capsfilter_bgr)
                        elements.append(capsfilter_bgr)
                        print("   🔧 BGR capsfilter inserted before appsink")

                    # Mark position for special linking AFTER adding capsfilter
                    # opencv_appsink_idx points to the appsink element that receives data
                    opencv_appsink_idx = len(elements)
                    elements.append(opencv_appsink)
                    elements.append(opencv_appsrc)

                    # Add videoconvert after appsrc to ensure encoder gets the right format
                    videoconv_post = Gst.ElementFactory.make("videoconvert", "webrtc_opencv_post_conv")
                    if videoconv_post:
                        pipeline.add(videoconv_post)
                        elements.append(videoconv_post)

                    # Start OpenCV processing thread
                    self._start_opencv_processing_thread()
                else:
                    print("   ⚠️  OpenCV elements creation failed, continuing without processing")
                    opencv_appsink = None
                    opencv_appsrc = None
            else:
                print("   → OpenCV processing DISABLED")

            # ── H264 encoder selection: try x264enc first, then openh264enc ──
            bitrate_kbps = self.video_config.h264_bitrate or 1500
            encoder_name = None

            x264enc = Gst.ElementFactory.make("x264enc", "webrtc_h264enc")
            if x264enc:
                encoder_name = "x264enc"
                x264enc.set_property("tune", 0x00000004)  # zerolatency
                x264enc.set_property("speed-preset", 1)  # ultrafast
                x264enc.set_property("bitrate", bitrate_kbps)
                x264enc.set_property("key-int-max", self.video_config.framerate * 2)  # keyframe every 2s
                x264enc.set_property("byte-stream", True)
                pipeline.add(x264enc)
                elements.append(x264enc)
                # Install encoder stats probes
                self._install_encoder_probes(x264enc)
                print(f"   → Using x264enc (ultrafast/zerolatency) @ {bitrate_kbps} kbps")
            else:
                openh264enc = Gst.ElementFactory.make("openh264enc", "webrtc_h264enc")
                if openh264enc:
                    encoder_name = "openh264enc"
                    openh264enc.set_property("bitrate", bitrate_kbps * 1000)
                    openh264enc.set_property("complexity", 0)  # low complexity
                    pipeline.add(openh264enc)
                    elements.append(openh264enc)
                    # Install encoder stats probes
                    self._install_encoder_probes(openh264enc)
                    print(f"   → Using openh264enc @ {bitrate_kbps} kbps")
                else:
                    self.last_error = "No H264 encoder available (need x264enc or openh264enc)"
                    return False

            self.current_encoder_provider = f"WebRTC (H264 {encoder_name}→aiortc)"

            # ── h264parse → normalize NAL format ──
            h264parse = Gst.ElementFactory.make("h264parse", "webrtc_h264parse")
            if h264parse:
                h264parse.set_property("config-interval", -1)  # send SPS/PPS with every keyframe
                pipeline.add(h264parse)
                elements.append(h264parse)

            # ── Appsink — outputs H264 byte-stream ──
            appsink = Gst.ElementFactory.make("appsink", "webrtc_appsink")
            if not appsink:
                self.last_error = "appsink GStreamer plugin not available"
                return False

            appsink.set_property("emit-signals", True)
            appsink.set_property("sync", False)
            appsink.set_property("max-buffers", 3)
            appsink.set_property("drop", True)
            appsink.set_property(
                "caps",
                Gst.Caps.from_string("video/x-h264,stream-format=byte-stream,alignment=au"),
            )
            pipeline.add(appsink)
            elements.append(appsink)

            # ── Link all elements ──
            # Special handling for OpenCV: the appsink ↔ appsrc connection uses callbacks
            # So we skip linking appsink → appsrc, but link everything else normally
            for i in range(len(elements) - 1):
                # Skip ONLY the appsink → appsrc link when OpenCV is enabled
                if opencv_appsink_idx >= 0 and i == opencv_appsink_idx:
                    continue

                src_name = elements[i].get_name()
                dst_name = elements[i + 1].get_name()
                if not elements[i].link(elements[i + 1]):
                    self.last_error = f"Failed to link {src_name} → {dst_name}"
                    logger.error(self.last_error)
                    return False

            # ── Connect appsink signal ──
            appsink.connect("new-sample", self._on_webrtc_appsink_sample)

            # ── GStreamer bus ──
            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)

            self.pipeline = pipeline

            # Push initial frame to appsrc BEFORE starting pipeline (if OpenCV enabled)
            if opencv_appsrc is not None:
                self._push_initial_frame_to_appsrc(config["width"], config["height"])

            decode_step = "jpegdec → " if source_is_jpeg else ""
            print(
                f"✅ WebRTC H264 pipeline built: {src_cfg['element']} → {decode_step}"
                f"videoconvert → {encoder_name} → h264parse → appsink "
                f"({config['width']}x{config['height']}@{config['framerate']}fps @ {bitrate_kbps}kbps)"
            )
            return True

        except Exception as e:
            self.last_error = f"WebRTC pipeline error: {e}"
            print(f"❌ {self.last_error}")
            import traceback

            traceback.print_exc()
            return False

    def force_keyframe(self):
        """Force the GStreamer H264 encoder to produce an IDR keyframe.
        Called when a new WebRTC peer connects so it gets SPS/PPS/IDR."""
        if not self.pipeline or not GSTREAMER_AVAILABLE:
            return False
        try:
            encoder = self.pipeline.get_by_name("webrtc_h264enc")
            if encoder:
                # Send force-keyunit event on the encoder's srcpad (upstream event
                # must be sent on a downstream-facing pad to travel into the encoder)
                result = Gst.Structure.new_from_string("GstForceKeyUnit, all-headers=(boolean)true")
                structure = result[0] if isinstance(result, tuple) else result
                event = Gst.Event.new_custom(Gst.EventType.CUSTOM_UPSTREAM, structure)
                srcpad = encoder.get_static_pad("src")
                success = srcpad.send_event(event)
                print(f"🔑 Force keyframe requested → {success}")
                return success
        except Exception as e:
            print(f"⚠️ Force keyframe failed: {e}")
        return False

    def _install_encoder_probes(self, encoder_element):
        """
        Install GStreamer pad probes on encoder to collect performance metrics.
        Measures: encode time, frame counts, dropped frames.
        """
        if not encoder_element or not GSTREAMER_AVAILABLE:
            return

        try:
            # Probe on encoder sink pad (frame entering encoder)
            sinkpad = encoder_element.get_static_pad("sink")
            if sinkpad:
                probe_id = sinkpad.add_probe(Gst.PadProbeType.BUFFER, self._encoder_sinkpad_probe, None)
                self._encoder_probe_ids.append((sinkpad, probe_id))

            # Probe on encoder src pad (frame leaving encoder)
            srcpad = encoder_element.get_static_pad("src")
            if srcpad:
                probe_id = srcpad.add_probe(Gst.PadProbeType.BUFFER, self._encoder_srcpad_probe, None)
                self._encoder_probe_ids.append((srcpad, probe_id))

            logger.info(f"Encoder probes installed on {encoder_element.get_name()}")
        except Exception as e:
            logger.warning(f"Failed to install encoder probes: {e}")

    def _encoder_sinkpad_probe(self, pad, info, user_data):
        """Probe callback for encoder sink pad - records frame entry time."""
        self._encode_start_time = time.time()
        return Gst.PadProbeReturn.OK

    def _encoder_srcpad_probe(self, pad, info, user_data):
        """
        Probe callback for encoder src pad - calculates encode time and frame stats.
        Also detects keyframes vs P-frames from H264 NAL type.
        """
        try:
            buf = info.get_buffer()
            if not buf:
                return Gst.PadProbeReturn.OK

            # Calculate encode time
            encode_time_ms = 0
            if self._encode_start_time > 0:
                encode_time_ms = (time.time() - self._encode_start_time) * 1000
                self._encode_start_time = 0

            # Get frame size
            frame_size = buf.get_size()

            # Detect frame type (keyframe vs P-frame) from buffer
            is_keyframe = False
            success, map_info = buf.map(Gst.MapFlags.READ)
            if success:
                # Check NAL type in H264 bitstream
                data = bytes(map_info.data[:16]) if map_info.size >= 16 else bytes(map_info.data)
                buf.unmap(map_info)

                # Look for IDR NAL unit (type 5)
                for i in range(len(data) - 4):
                    if data[i : i + 3] == b"\x00\x00\x01":
                        nal_type = data[i + 3] & 0x1F
                        if nal_type == 5:
                            is_keyframe = True
                            break
                    elif data[i : i + 4] == b"\x00\x00\x00\x01":
                        nal_type = data[i + 4] & 0x1F
                        if nal_type == 5:
                            is_keyframe = True
                            break

            # Update encoder stats (thread-safe)
            with self.stats_lock:
                stats = self.encoder_stats
                stats["frames_encoded"] += 1
                stats["last_frame_size_bytes"] = frame_size

                if encode_time_ms > 0:
                    stats["total_encode_time_ms"] += encode_time_ms
                    stats["avg_encode_time_ms"] = stats["total_encode_time_ms"] / stats["frames_encoded"]
                    if encode_time_ms > stats["max_encode_time_ms"]:
                        stats["max_encode_time_ms"] = encode_time_ms

                if is_keyframe:
                    stats["keyframes_sent"] += 1
                else:
                    stats["pframes_sent"] += 1

                # Calculate average frame size
                total_frames = stats["keyframes_sent"] + stats["pframes_sent"]
                if total_frames > 0:
                    # Use exponential moving average for frame size
                    alpha = 0.1
                    stats["avg_frame_size_bytes"] = int(
                        alpha * frame_size + (1 - alpha) * stats["avg_frame_size_bytes"]
                    )

        except Exception as e:
            logger.debug(f"Encoder probe error: {e}")

        return Gst.PadProbeReturn.OK

    def _remove_encoder_probes(self):
        """Remove all installed encoder probes."""
        for pad, probe_id in self._encoder_probe_ids:
            try:
                pad.remove_probe(probe_id)
            except Exception:
                pass
        self._encoder_probe_ids.clear()

    def _install_passthrough_probes(self, rtppay_element):
        """
        Install GStreamer pad probes on RTP payloader for passthrough mode.
        Measures: frame counts, frame sizes (for FPS calculation).
        """
        if not rtppay_element or not GSTREAMER_AVAILABLE:
            return

        try:
            # Probe on RTP payloader sink pad (frames entering payloader)
            sinkpad = rtppay_element.get_static_pad("sink")
            if sinkpad:
                probe_id = sinkpad.add_probe(Gst.PadProbeType.BUFFER, self._passthrough_probe, None)
                self._encoder_probe_ids.append((sinkpad, probe_id))

            logger.info(f"Passthrough probes installed on {rtppay_element.get_name()}")
        except Exception as e:
            logger.warning(f"Failed to install passthrough probes: {e}")

    def _passthrough_probe(self, pad, info, user_data):
        """
        Probe callback for passthrough mode (RTP payloader sink).
        Counts frames for FPS calculation.
        """
        try:
            buf = info.get_buffer()
            if not buf:
                return Gst.PadProbeReturn.OK

            # Get frame size
            frame_size = buf.get_size()

            # Update encoder stats (thread-safe) - reuse same structure
            with self.stats_lock:
                stats = self.encoder_stats
                stats["frames_encoded"] += 1
                stats["last_frame_size_bytes"] = frame_size

                # Detect keyframes (IDR NAL units)
                is_keyframe = False
                success, map_info = buf.map(Gst.MapFlags.READ)
                if success:
                    data = bytes(map_info.data[:16]) if map_info.size >= 16 else bytes(map_info.data)
                    buf.unmap(map_info)

                    # Look for IDR NAL unit (type 5)
                    for i in range(len(data) - 4):
                        if data[i : i + 3] == b"\x00\x00\x01":
                            nal_type = data[i + 3] & 0x1F
                            if nal_type == 5:
                                is_keyframe = True
                                break
                        elif data[i : i + 4] == b"\x00\x00\x00\x01":
                            nal_type = data[i + 4] & 0x1F
                            if nal_type == 5:
                                is_keyframe = True
                                break

                if is_keyframe:
                    stats["keyframes_sent"] += 1
                else:
                    stats["pframes_sent"] += 1

                # Calculate average frame size
                total_frames = stats["keyframes_sent"] + stats["pframes_sent"]
                if total_frames > 0:
                    # Use exponential moving average for frame size
                    alpha = 0.1
                    stats["avg_frame_size_bytes"] = int(
                        alpha * frame_size + (1 - alpha) * stats["avg_frame_size_bytes"]
                    )

        except Exception as e:
            logger.debug(f"Passthrough probe error: {e}")

        return Gst.PadProbeReturn.OK

    def _on_webrtc_appsink_sample(self, appsink):
        """
        Called by GStreamer whenever a new H264 access unit is ready.
        Extracts the H264 bytes and pushes them to the WebRTC service
        (which feeds the aiortc H264PassthroughEncoder for RTP packetization).
        """
        try:
            sample = appsink.emit("pull-sample")
            if not sample:
                return Gst.FlowReturn.OK

            buf = sample.get_buffer()
            if not buf:
                return Gst.FlowReturn.OK

            success, map_info = buf.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.OK

            try:
                h264_data = bytes(map_info.data)

                # Feed to WebRTC service → aiortc H264 passthrough
                if self.webrtc_service:
                    self.webrtc_service.push_video_frame(h264_data)

                # Update stats
                with self.stats_lock:
                    self.stats["frames_sent"] = self.stats.get("frames_sent", 0) + 1
                    self.stats["bytes_sent"] = self.stats.get("bytes_sent", 0) + len(h264_data)
            finally:
                buf.unmap(map_info)

        except Exception as e:
            print(f"⚠️ WebRTC appsink error: {e}")

        return Gst.FlowReturn.OK

    def _adapt_codec_to_board(self, codec_id: str) -> str:
        """
        Adapt requested codec to available board features.

        Smart codec selection:
        1. If user requests 'h264' (generic), auto-upgrade to hardware H.264
           if the board has a V4L2 M2M encoder available.
        2. If user requests a specific HW encoder that's unavailable, fall
           back gracefully: h264_hardware → h264 (x264) → mjpeg.
        3. Board feature list is consulted but the final word comes from
           the provider's is_available() (runtime GStreamer check).

        Args:
            codec_id: Requested codec (e.g., 'h264', 'h264_hardware', 'mjpeg')

        Returns:
            Adapted codec_id that's supported on this board
        """
        try:
            from app.providers.board import BoardRegistry
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            detected_board = BoardRegistry().get_detected_board()

            # ── Gather board feature list (informational) ──
            available_encoders = []
            if detected_board:
                available_encoders = [f.value for f in detected_board.variant.video_encoders]
                print(f"📊 Board supports encoders: {available_encoders}")
            print(f"   User requested: {codec_id}")

            # Normalize aliases
            requested_codec_id = codec_id
            normalized_codec_id = "h264" if requested_codec_id == "x264" else requested_codec_id

            # ── AUTO-UPGRADE: generic h264 → hardware when available ──
            # If the user selected 'h264' (or 'x264') without specifying
            # software/hardware, check if hardware is available and prefer it.
            if requested_codec_id in ("h264", "x264"):
                hw_provider = registry.get_video_encoder("h264_hardware")
                if hw_provider and hw_provider.is_available():
                    print("🚀 Hardware H.264 encoder detected — auto-upgrading from software")
                    return "h264_hardware"

            # If explicitly requesting hardware and it's available, use it
            if requested_codec_id in ("h264_hardware", "h264_hw", "h264_hw_meson"):
                hw_provider = registry.get_video_encoder("h264_hardware")
                if hw_provider and hw_provider.is_available():
                    print("✅ Using hardware H.264 encoder")
                    return "h264_hardware"
                # HW not available — fall back
                print("⚠️ Hardware H.264 encoder not available, falling back to x264")
                sw_provider = registry.get_video_encoder("h264")
                if sw_provider and sw_provider.is_available():
                    return "h264"
                print("⚠️ x264 also unavailable, falling back to MJPEG")
                return "mjpeg"

            # Map codec ID to board feature names for feature-gate check
            codec_to_feature = {
                "h264_hardware": "hardware_h264",
                "h264": "x264",
                "mjpeg": "mjpeg",
                "h264_openh264": "openh264",
            }

            requested_feature = codec_to_feature.get(normalized_codec_id)

            # If board info available, verify codec is in feature list
            if detected_board and requested_feature:
                if requested_feature in available_encoders:
                    print(f"✅ Using {normalized_codec_id} (supported on board)")
                    return normalized_codec_id
                else:
                    # Feature not declared, but the provider might still work
                    provider = registry.get_video_encoder(normalized_codec_id)
                    if provider and provider.is_available():
                        print(f"⚠️ {normalized_codec_id} not in board features but GStreamer reports available")
                        return normalized_codec_id
                    # Fallback chain: h264 → mjpeg
                    if normalized_codec_id != "mjpeg":
                        print(f"⚠️ {requested_codec_id} not available, falling back to mjpeg")
                        return "mjpeg"

            # No board detection — trust the requested codec
            return normalized_codec_id

        except Exception as e:
            print(f"⚠️ Board adaptation error: {e}, using requested codec")
            return codec_id

    def _build_pipeline_from_provider(self, codec_id: str) -> bool:  # noqa: C901
        """
        Build pipeline using video encoder provider.
        Returns True if successful, False otherwise.
        """
        try:
            # Import here to avoid circular dependency
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            provider = registry.get_video_encoder(codec_id)

            if not provider:
                print(f"⚠️ No provider found for codec: {codec_id}")
                return False

            if not provider.is_available():
                print(f"⚠️ Provider {codec_id} not available on system")
                return False

            # Get video source provider FIRST to determine source format
            registry = get_provider_registry()

            # Find which source provider handles this device
            source_provider = None

            for source_type in registry.list_video_source_providers():
                sp = registry.get_video_source(source_type)
                if sp and sp.is_available():
                    # Check if this provider can handle the device
                    sources = sp.discover_sources()
                    for src in sources:
                        if src["device"] == self.video_config.device:
                            source_provider = sp
                            break
                    if source_provider:
                        break

            # Fallback to v4l2 if no provider found (backward compatibility)
            if not source_provider:
                source_provider = registry.get_video_source("v4l2")

            # Store source provider name for status reporting
            if source_provider:
                self.current_source_provider = source_provider.display_name

            if not source_provider:
                print(f"❌ No video source provider available for {self.video_config.device}")
                self.last_error = "No video source provider available"
                return False

            # Build config dict from video_config
            config = {
                "width": self.video_config.width,
                "height": self.video_config.height,
                "framerate": self.video_config.framerate,
                "bitrate": self.video_config.h264_bitrate,
                "quality": self.video_config.quality,
                "gop_size": self.video_config.gop_size,
                "opencv_enabled": self._is_opencv_enabled(),  # For HW decoder optimization
            }

            # ═══════════════════════════════════════════════════════════════
            # BOARD-SPECIFIC PIPELINE HINTS
            # Apply hardware-aware defaults from the detected board so
            # encoders can pick optimal formats, queue depths, and GOP.
            # ═══════════════════════════════════════════════════════════════
            try:
                from app.providers.board import BoardRegistry

                detected_board = BoardRegistry().get_detected_board()
                if detected_board:
                    hints = detected_board.get_pipeline_hints()
                    config["board_hints"] = hints
                    # Use board-recommended GOP if user hasn't explicitly set one
                    if not self.video_config.gop_size or self.video_config.gop_size <= 0:
                        config["gop_size"] = hints.get("recommended_gop", 30)
                        print(f"   📋 Board hint: gop_size={config['gop_size']}")
            except Exception:
                pass  # Board hints are optional optimizations

            # If passthrough is requested, force H264 format from the camera
            if codec_id == "h264_passthrough":
                config["format"] = "H264"

            # ═══════════════════════════════════════════════════════════════
            # VALIDATE SOURCE CONFIG BEFORE BUILDING PIPELINE
            # Check that the requested resolution/fps is supported by the
            # camera. Adjust automatically if not, to prevent pipeline
            # failures with cryptic GStreamer errors.
            # ═══════════════════════════════════════════════════════════════
            validation = source_provider.validate_config(self.video_config.device, config)
            if validation and not validation.get("valid", True):
                errors = validation.get("errors", [])
                self.last_error = "; ".join(errors) if errors else "Invalid video configuration for this camera"
                print(f"❌ Source validation failed: {self.last_error}")
                return False
            if validation:
                for warning in validation.get("warnings", []):
                    print(f"⚠️ Source config: {warning}")
                adjusted = validation.get("adjusted_config")
                if adjusted:
                    # Apply auto-corrected values (e.g. nearest supported resolution)
                    for key in ("width", "height", "framerate"):
                        if key in adjusted and adjusted[key] != config.get(key):
                            print(f"   ↳ Auto-adjusted {key}: {config[key]} → {adjusted[key]}")
                            config[key] = adjusted[key]
                            setattr(self.video_config, key, adjusted[key])

            # Build source element from provider to get source format
            source_config_result = source_provider.build_source_element(self.video_config.device, config)

            if not source_config_result["success"]:
                print(f"❌ Failed to build source element: {source_config_result.get('error')}")
                self.last_error = source_config_result.get("error", "Unknown error")
                return False

            # Add source format to config for encoder (H.264, MJPEG, etc)
            config["source_format"] = source_config_result.get("output_format", "image/jpeg")

            # ═══════════════════════════════════════════════════════════════
            # AUTO-DETECT H.264 PASSTHROUGH OPPORTUNITY
            # If camera outputs native H.264 and user requested H.264 encoding,
            # automatically use passthrough mode (no decode/re-encode)
            # ═══════════════════════════════════════════════════════════════
            source_format = config["source_format"]
            is_h264_camera = "video/x-h264" in source_format

            if is_h264_camera and codec_id in ["h264", "x264"]:
                # Check if passthrough encoder is available
                passthrough_provider = registry.get_video_encoder("h264_passthrough")
                if passthrough_provider and passthrough_provider.is_available():
                    print("🚀 Camera outputs native H.264, using passthrough mode (ultra low latency)")
                    codec_id = "h264_passthrough"
                    provider = passthrough_provider
                    # Update encoder provider name
                    self.current_encoder_provider = provider.display_name
            # ═══════════════════════════════════════════════════════════════

            # Validate config
            validation = provider.validate_config(config)
            if not validation["valid"]:
                print(f"❌ Invalid config: {validation['errors']}")
                self.last_error = "; ".join(validation["errors"])
                return False

            if validation["warnings"]:
                for warning in validation["warnings"]:
                    print(f"⚠️ {warning}")

            # Get pipeline elements from provider
            pipeline_config = provider.build_pipeline_elements(config)
            if not pipeline_config["success"]:
                print(f"❌ Failed to build pipeline elements: {pipeline_config.get('error', 'Unknown error')}")
                self.last_error = pipeline_config.get("error", "Unknown error")
                return False

            # Create GStreamer pipeline
            print(f"🔧 Building pipeline with encoder: {provider.display_name}")
            pipeline = Gst.Pipeline.new(f"fpv-{codec_id}-pipeline")

            # Store encoder provider name for status reporting
            self.current_encoder_provider = provider.display_name

            # Create source element
            source_cfg = source_config_result["source_element"]
            source = Gst.ElementFactory.make(source_cfg["element"], source_cfg["name"])
            if not source:
                print(f"❌ Failed to create source element: {source_cfg['element']}")
                return False

            # Set source properties
            for prop, value in source_cfg["properties"].items():
                source.set_property(prop, value)

            pipeline.add(source)
            elements_list = [source]

            # Add caps filter if provided
            if source_config_result["caps_filter"]:
                caps_filter = Gst.ElementFactory.make("capsfilter", "caps_filter")
                caps_filter.set_property("caps", Gst.Caps.from_string(source_config_result["caps_filter"]))
                pipeline.add(caps_filter)
                elements_list.append(caps_filter)

            # Add any post-source elements from provider
            for elem_config in source_config_result.get("post_elements", []):
                element = Gst.ElementFactory.make(elem_config["element"], elem_config["name"])
                if not element:
                    print(f"❌ Failed to create post-source element: {elem_config['element']}")
                    return False

                for prop, value in elem_config.get("properties", {}).items():
                    element.set_property(prop, value)

                pipeline.add(element)
                elements_list.append(element)

            # ══════════════════════════════════════════════════════════════
            # OPENCV PROCESSING INJECTION POINT
            # ══════════════════════════════════════════════════════════════
            opencv_appsink_idx = -1
            opencv_enabled = self._is_opencv_enabled()

            # Check if source outputs MJPEG (image/jpeg) - need to decode before OpenCV
            caps_filter_str = source_config_result.get("caps_filter", "")
            output_format = source_config_result.get("output_format", "")
            is_jpeg_source = "image/jpeg" in caps_filter_str or "image/jpeg" in output_format
            is_h264_source = "video/x-h264" in caps_filter_str or "video/x-h264" in output_format

            if opencv_enabled:
                print("🎨 OpenCV processing enabled - inserting into pipeline")

                if is_jpeg_source:
                    print("   → Detected MJPEG source, adding jpegdec + videoconvert")
                    # Add jpegdec to decode MJPEG
                    jpegdec = Gst.ElementFactory.make("jpegdec", "opencv_jpegdec")
                    if jpegdec:
                        pipeline.add(jpegdec)
                        elements_list.append(jpegdec)

                    # Add videoconvert to ensure BGR format for OpenCV
                    videoconv = Gst.ElementFactory.make("videoconvert", "opencv_videoconv")
                    if videoconv:
                        pipeline.add(videoconv)
                        elements_list.append(videoconv)
                elif is_h264_source:
                    print("   → Detected H.264 source, adding avdec_h264 + videoconvert")
                    # Add avdec_h264 to decode H.264
                    h264dec = Gst.ElementFactory.make("avdec_h264", "opencv_h264dec")
                    if h264dec:
                        pipeline.add(h264dec)
                        elements_list.append(h264dec)

                    # Add videoconvert to ensure BGR format for OpenCV
                    videoconv = Gst.ElementFactory.make("videoconvert", "opencv_videoconv")
                    if videoconv:
                        pipeline.add(videoconv)
                        elements_list.append(videoconv)

                # Create OpenCV processing elements
                appsink, appsrc = self._create_opencv_processing_elements(
                    pipeline, config["width"], config["height"], config["framerate"]
                )

                if appsink and appsrc:
                    # Add capsfilter to force BGR conversion BEFORE appsink
                    capsfilter_bgr = Gst.ElementFactory.make("capsfilter", "opencv_capsfilter_udp")
                    if capsfilter_bgr:
                        w, h, fps = config["width"], config["height"], config["framerate"]
                        cap_str = f"video/x-raw,format=BGR,width={w},height={h},framerate={fps}/1"
                        caps = Gst.Caps.from_string(cap_str)
                        capsfilter_bgr.set_property("caps", caps)
                        pipeline.add(capsfilter_bgr)
                        elements_list.append(capsfilter_bgr)
                        print("   🔧 BGR capsfilter inserted before appsink")

                    # Mark position for special linking AFTER adding capsfilter
                    opencv_appsink_idx = len(elements_list)
                    elements_list.append(appsink)
                    elements_list.append(appsrc)

                    # Add videoconvert after appsrc to ensure encoder gets the right format
                    videoconv_post = Gst.ElementFactory.make("videoconvert", "videoconv_opencv_post")
                    pipeline.add(videoconv_post)
                    elements_list.append(videoconv_post)

                    # Start OpenCV processing thread
                    self._start_opencv_processing_thread()
                else:
                    print("⚠️ Failed to create OpenCV elements, continuing without processing")
                    opencv_enabled = False
                    opencv_appsink_idx = -1
            # ══════════════════════════════════════════════════════════════

            # Add encoder elements
            encoder_element = None
            for elem_config in pipeline_config["elements"]:
                # Skip decoder if OpenCV is enabled and we already decoded (MJPEG or H.264)
                if opencv_enabled and elem_config["name"] == "decoder" and (is_jpeg_source or is_h264_source):
                    continue

                element = Gst.ElementFactory.make(elem_config["element"], elem_config["name"])
                if not element:
                    print(f"❌ Failed to create element: {elem_config['element']}")
                    return False

                # Set properties
                for prop, value in elem_config["properties"].items():
                    try:
                        # Handle capsfilter caps property specially
                        if prop == "caps" and isinstance(value, str):
                            element.set_property(prop, Gst.Caps.from_string(value))
                        else:
                            element.set_property(prop, value)
                    except Exception as e:
                        print(f"⚠️ Failed to set property {prop}={value} on {elem_config['name']}: {e}")

                pipeline.add(element)
                elements_list.append(element)

                # Track encoder element for stats probes
                if elem_config["name"] == "encoder":
                    encoder_element = element

            # Install encoder stats probes
            if encoder_element:
                self._install_encoder_probes(encoder_element)
            else:
                # No encoder (passthrough mode) - install probe on RTP payloader instead
                print("📊 Passthrough mode: Installing probe on RTP payloader for stats")

            # Add RTP payloader
            rtppay = Gst.ElementFactory.make(pipeline_config["rtp_payloader"], "rtppay")
            if not rtppay:
                print(f"❌ Failed to create RTP payloader: {pipeline_config['rtp_payloader']}")
                return False

            for prop, value in pipeline_config["rtp_payloader_properties"].items():
                rtppay.set_property(prop, value)

            pipeline.add(rtppay)
            elements_list.append(rtppay)

            # Install passthrough probe on RTP payloader if no encoder
            if not encoder_element:
                self._install_passthrough_probes(rtppay)

            # Create sink based on streaming mode
            sink = self._create_sink_for_mode()
            if not sink:
                print(f"❌ Failed to create sink for mode: {self.streaming_config.mode}")
                return False

            pipeline.add(sink)
            elements_list.append(sink)

            # Link all elements in order
            # Special handling for OpenCV: don't link appsink → appsrc
            # (they communicate via callbacks)
            opencv_skip_start = opencv_appsink_idx if opencv_appsink_idx >= 0 else -1

            for i in range(len(elements_list) - 1):
                # Skip ONLY the appsink → appsrc link (they communicate via callbacks)
                if opencv_skip_start >= 0 and i == opencv_skip_start:
                    continue

                src_name = elements_list[i].get_name()
                dst_name = elements_list[i + 1].get_name()
                if not elements_list[i].link(elements_list[i + 1]):
                    logger.error(f"Failed to link {src_name} → {dst_name}")
                    return False

            # WebRTC mode: add tee + appsink branch for JPEG frames to aiortc
            if self.streaming_config.mode == "webrtc" and self.webrtc_service:
                self._attach_webrtc_appsink(pipeline, elements_list)

            # Setup bus for messages
            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)

            self.pipeline = pipeline
            print(f"✅ Pipeline built successfully using provider: {provider.display_name}")
            return True

        except Exception as e:
            print(f"❌ Exception building pipeline from provider: {e}")
            import traceback

            traceback.print_exc()
            self.last_error = str(e)
            return False

    def _create_sink_for_mode(self):
        """
        Create appropriate sink element based on streaming mode.
        Returns GStreamer sink element or None on error.
        """
        mode = self.streaming_config.mode
        print(f"📡 Creating sink for mode: {mode}")

        try:
            if mode == "udp":
                # Mode 1: Direct UDP (unicast) - Default for single client
                sink = Gst.ElementFactory.make("udpsink", "sink")
                if not sink:
                    return None
                sink.set_property("host", self.streaming_config.udp_host)
                sink.set_property("port", self.streaming_config.udp_port)
                sink.set_property("sync", False)
                sink.set_property("async", False)
                print(f"   → UDP unicast to {self.streaming_config.udp_host}:{self.streaming_config.udp_port}")
                return sink

            elif mode == "multicast":
                # Mode 3: UDP Multicast - Multiple clients on LAN
                sink = Gst.ElementFactory.make("udpsink", "sink")
                if not sink:
                    return None
                sink.set_property("host", self.streaming_config.multicast_group)
                sink.set_property("port", self.streaming_config.multicast_port)
                sink.set_property("auto-multicast", True)
                sink.set_property("ttl", self.streaming_config.multicast_ttl)
                sink.set_property("sync", False)
                sink.set_property("async", False)
                group = self.streaming_config.multicast_group
                mport = self.streaming_config.multicast_port
                print(f"   → UDP multicast to {group}:{mport}")
                return sink

            elif mode == "webrtc":
                # Mode 4: WebRTC — pipeline sinks to fakesink;
                # actual video is sent via aiortc from the appsink branch
                sink = Gst.ElementFactory.make("fakesink", "sink")
                if not sink:
                    return None
                sink.set_property("sync", False)
                sink.set_property("async", False)
                print("   → WebRTC mode (fakesink + appsink for aiortc)")
                return sink

            else:
                print(f"⚠️ Unknown streaming mode: {mode}, falling back to UDP")
                return self._create_fallback_udp_sink()

        except Exception as e:
            print(f"❌ Error creating sink for mode {mode}: {e}")
            return None

    def _create_fallback_udp_sink(self):
        """Create fallback UDP sink when preferred sink is not available"""
        sink = Gst.ElementFactory.make("udpsink", "sink")
        if sink:
            sink.set_property("host", self.streaming_config.udp_host)
            sink.set_property("port", self.streaming_config.udp_port)
            sink.set_property("sync", False)
            sink.set_property("async", False)
            print(f"   → Fallback to UDP: {self.streaming_config.udp_host}:{self.streaming_config.udp_port}")
        return sink

    def _setup_stats_probes(self):
        """Setup probes to count frames and bytes"""
        if not GSTREAMER_AVAILABLE or not self.pipeline:
            return

        try:
            probe_types = Gst.PadProbeType.BUFFER | Gst.PadProbeType.BUFFER_LIST

            # Count encoded frames (one buffer per frame)
            # Try encoder first (for x264, openh264, etc)
            encoder = self.pipeline.get_by_name("encoder")
            if encoder:
                pad = encoder.get_static_pad("src")
                if pad:
                    pad.add_probe(probe_types, self._on_frame_probe)
            else:
                # No encoder (passthrough mode) - count frames from h264parse src pad
                h264parse = self.pipeline.get_by_name("h264parse")
                if h264parse:
                    pad = h264parse.get_static_pad("src")
                    if pad:
                        pad.add_probe(probe_types, self._on_frame_probe)
                        print("📊 Passthrough: Counting FPS from h264parse")

            # Count bytes on the wire from sink pad
            sink = self.pipeline.get_by_name("sink")
            if sink:
                pad = sink.get_static_pad("sink")
                if pad:
                    pad.add_probe(probe_types, self._on_bytes_probe)
            else:
                # Fallback: count bytes at RTP payloader if sink is unavailable
                rtppay = self.pipeline.get_by_name("rtppay")
                if rtppay:
                    pad = rtppay.get_static_pad("src")
                    if pad:
                        pad.add_probe(probe_types, self._on_bytes_probe)
        except Exception as e:
            print(f"⚠️ Failed to setup stats probes: {e}")

    def _update_rates_locked(self, now: float) -> None:
        if self.stats["last_stats_time"] is None:
            self.stats["last_stats_time"] = now
            return

        elapsed = now - self.stats["last_stats_time"]
        if elapsed < 0.5:
            return

        frames_delta = self.stats["frames_sent"] - self.stats["last_frames_count"]
        bytes_delta = self.stats["bytes_sent"] - self.stats["last_bytes_count"]

        self.stats["current_fps"] = int(frames_delta / elapsed)
        self.stats["current_bitrate"] = int((bytes_delta * 8) / (elapsed * 1000))

        self.stats["last_stats_time"] = now
        self.stats["last_frames_count"] = self.stats["frames_sent"]
        self.stats["last_bytes_count"] = self.stats["bytes_sent"]

    def _on_frame_probe(self, pad, info):
        """Pad probe callback to count encoded frames"""
        try:
            # Filtra el tipo de probe para evitar assertions
            if info.type & Gst.PadProbeType.BUFFER_LIST:
                buffer_list = info.get_buffer_list()
                with self.stats_lock:
                    if buffer_list:
                        self.stats["frames_sent"] += buffer_list.length()
                    import time

                    self._update_rates_locked(time.time())
            elif info.type & Gst.PadProbeType.BUFFER:
                buffer = info.get_buffer()
                with self.stats_lock:
                    if buffer:
                        self.stats["frames_sent"] += 1
                    import time

                    self._update_rates_locked(time.time())
        except Exception as e:
            print(f"⚠️ Error in frame probe: {e}")

        return Gst.PadProbeReturn.OK

    def _on_bytes_probe(self, pad, info):
        """Pad probe callback to count transmitted bytes"""
        try:
            # Filtra el tipo de probe para evitar assertions
            if info.type & Gst.PadProbeType.BUFFER_LIST:
                buffer_list = info.get_buffer_list()
                with self.stats_lock:
                    if buffer_list:
                        total = 0
                        for i in range(buffer_list.length()):
                            buf = buffer_list.get(i)
                            if buf:
                                total += buf.get_size()
                        self.stats["bytes_sent"] += total
                    import time

                    self._update_rates_locked(time.time())
            elif info.type & Gst.PadProbeType.BUFFER:
                buffer = info.get_buffer()
                with self.stats_lock:
                    if buffer:
                        self.stats["bytes_sent"] += buffer.get_size()
                    import time

                    self._update_rates_locked(time.time())
        except Exception as e:
            print(f"⚠️ Error in bytes probe: {e}")

        return Gst.PadProbeReturn.OK

    def _on_bus_message(self, bus, message):
        """Handle GStreamer bus messages"""
        if not GSTREAMER_AVAILABLE:
            return True

        t = message.type

        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self.last_error = str(err)
            self.stats["errors"] += 1
            print(f"❌ GStreamer Error: {err}")
            if debug:
                print(f"   Debug: {debug}")
            # Print element that caused the error
            if message.src:
                print(f"   Element: {message.src.get_name()}")
            self._broadcast_status()
            # Auto-stop to clean up pipeline state
            try:
                self.stop()
            except Exception as e:
                print(f"⚠️ Error during auto-stop after pipeline error: {e}")

        elif t == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            print(f"⚠️ GStreamer Warning: {warn}")
            if debug:
                print(f"   Debug: {debug}")
            if message.src:
                print(f"   Element: {message.src.get_name()}")

        elif t == Gst.MessageType.EOS:
            print("📹 End of stream")
            self.stop()

        elif t == Gst.MessageType.ASYNC_DONE:
            pass  # Pipeline preroll complete

        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    self.is_streaming = True
                    self._broadcast_status()
                elif new_state == Gst.State.NULL:
                    self.is_streaming = False
                    self._broadcast_status()

        return True

    def _optimize_for_streaming(self):
        """Optimize system for video streaming performance"""
        try:
            # Try to set CPU governor to performance mode without sudo
            # Only works if running as root or permissions are pre-configured
            governor_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
            if os.path.exists(governor_path):
                try:
                    with open(governor_path, "w") as f:
                        f.write("performance")
                except PermissionError:
                    # Don't block on sudo - just skip this optimization
                    pass
        except Exception:
            pass  # CPU optimization skipped

    def _restore_cpu_mode(self):
        """Restore CPU to power-saving mode"""
        try:
            governor_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
            if os.path.exists(governor_path):
                try:
                    with open(governor_path, "w") as f:
                        f.write("ondemand")
                    print("💤 CPU governor restored to ONDEMAND mode")
                except PermissionError:
                    pass
        except Exception:
            pass

    def start(self) -> Dict[str, Any]:
        """Start video streaming"""
        if not GSTREAMER_AVAILABLE:
            return {"success": False, "message": "GStreamer not available"}

        if self.is_streaming:
            return {"success": False, "message": "Already streaming"}

        # Auto-detect camera if device is not configured or doesn't exist
        if not self.video_config.device or not os.path.exists(self.video_config.device):
            detected = auto_detect_camera()
            if detected and os.path.exists(detected):
                old_device = self.video_config.device
                self.video_config.device = detected
                if old_device:
                    print(f"⚠️ Camera {old_device} not found, using detected: {detected}")
                else:
                    print(f"📷 Auto-detected camera: {detected}")

                # Save detected device to preferences for persistence
                if self.preferences_service:
                    try:
                        self.preferences_service.update_video_source_device(detected)
                        print(f"💾 Saved detected device to preferences: {detected}")
                    except Exception as e:
                        print(f"⚠️ Failed to save device to preferences: {e}")
            else:
                msg = (
                    f"Camera not found: {self.video_config.device}"
                    if self.video_config.device
                    else "No camera configured or detected"
                )
                return {"success": False, "message": msg}

        # Check if using RTSP Server mode
        if self.streaming_config.mode == "rtsp":
            return self._start_rtsp_server()

        # Activate WebRTC service if in webrtc mode
        if self.streaming_config.mode == "webrtc" and self.webrtc_service:
            try:
                self.webrtc_service.activate()
                # Give WebRTC service a back-reference for keyframe requests
                self.webrtc_service._gstreamer_service = self
                print("\u2705 WebRTC service activated")
            except Exception as e:
                print(f"\u26a0\ufe0f WebRTC activation error: {e}")

        # Validate streaming configuration for UDP/multicast modes (skip for webrtc)
        if self.streaming_config.mode not in ("webrtc",) and not self.streaming_config.udp_host:
            return {
                "success": False,
                "message": "No destination IP configured for streaming",
            }

        # ═══════════════════════════════════════════════════════════════
        # WARNING: UDP over 4G without VPN
        # UDP unicast over cellular NAT will likely fail. Warn the user
        # and suggest WebRTC or VPN for 4G connectivity.
        # ═══════════════════════════════════════════════════════════════
        if self.streaming_config.mode == "udp":
            try:
                from app.services.network_event_bridge import detect_primary_interface
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, schedule and don't block
                    async def _check_and_warn():
                        try:
                            iface_info = await detect_primary_interface()
                            if iface_info.get("type") == "modem":
                                warning_msg = (
                                    "UDP streaming over 4G/LTE detected. "
                                    "Packets may not reach the client due to carrier NAT. "
                                    "Consider using WebRTC mode or a VPN (Tailscale/ZeroTier) "
                                    "for reliable 4G streaming."
                                )
                                print(f"⚠️ {warning_msg}")
                                if self.websocket_manager and self.event_loop:
                                    await self.websocket_manager.broadcast(
                                        "video_warning",
                                        {"type": "udp_over_4g", "message": warning_msg},
                                    )
                        except Exception:
                            pass

                    asyncio.run_coroutine_threadsafe(_check_and_warn(), self.event_loop)
                # If no loop running, skip - non-critical warning
            except Exception:
                pass  # Non-critical: don't block streaming start

        # Build pipeline
        if not self.build_pipeline():
            return {
                "success": False,
                "message": self.last_error or "Failed to build pipeline",
            }

        # Setup stats probes for metrics
        self._setup_stats_probes()

        # Optimize system
        self._optimize_for_streaming()

        # Start GLib main loop in background thread
        self.main_loop = GLib.MainLoop()
        self.main_loop_thread = threading.Thread(target=self.main_loop.run, daemon=True, name="GLibMainLoop")
        self.main_loop_thread.start()

        # Start pipeline
        import time

        # Reset stats counters for new stream
        with self.stats_lock:
            self.stats["start_time"] = time.time()
            self.stats["frames_sent"] = 0
            self.stats["bytes_sent"] = 0
            self.stats["last_stats_time"] = None
            self.stats["last_frames_count"] = 0
            self.stats["last_bytes_count"] = 0
            self.stats["current_fps"] = 0
            self.stats["current_bitrate"] = 0

            # Reset encoder stats
            self.encoder_stats = {
                "frames_encoded": 0,
                "frames_dropped_pre_encoder": 0,
                "frames_dropped_post_encoder": 0,
                "total_encode_time_ms": 0,
                "avg_encode_time_ms": 0.0,
                "max_encode_time_ms": 0.0,
                "last_frame_size_bytes": 0,
                "keyframes_sent": 0,
                "pframes_sent": 0,
                "avg_frame_size_bytes": 0,
            }

        ret = self.pipeline.set_state(Gst.State.PLAYING)

        if ret == Gst.StateChangeReturn.FAILURE:
            self.last_error = "Failed to start pipeline"
            return {"success": False, "message": self.last_error}

        # Wait for pipeline to reach PLAYING state and check for errors
        state_change = self.pipeline.get_state(timeout=2 * Gst.SECOND)
        if state_change[0] == Gst.StateChangeReturn.FAILURE:
            self.last_error = "Pipeline state change failed"
            logger.error(self.last_error)
            return {"success": False, "message": self.last_error}

        self.is_streaming = True

        self._start_stats_broadcast()

        self._broadcast_status()

        return {
            "success": True,
            "message": "Streaming started",
            "codec": self.video_config.codec,
            "resolution": f"{self.video_config.width}x{self.video_config.height}",
            "destination": f"{self.streaming_config.udp_host}:{self.streaming_config.udp_port}",
        }

    def _start_rtsp_server(self) -> Dict[str, Any]:
        """Start RTSP server for RTSP streaming mode"""
        import time

        print("📡 Starting RTSP Server mode...")

        # Create RTSP server if not exists
        if not self.rtsp_server:
            self.rtsp_server = RTSPServer(port=8554, mount_point="/fpv")
            # Connect OpenCV service if available
            if self._opencv_service:
                self.rtsp_server.set_opencv_service(self._opencv_service)

        # Start server with video configuration
        try:
            self.rtsp_server.start(
                device=self.video_config.device,
                codec=self.video_config.codec,
                width=self.video_config.width,
                height=self.video_config.height,
                framerate=self.video_config.framerate,
                bitrate=self.video_config.h264_bitrate,
                quality=self.video_config.quality,
            )

            self.is_streaming = True

            # Set provider info for RTSP mode
            encoder_name = self.rtsp_server._encoder_display_name or self.video_config.codec
            self.current_encoder_provider = f"RTSP Server ({encoder_name})"
            self.current_source_provider = f"{self.video_config.device}"

            # Initialize stats for RTSP mode (keep at 0 - RTSP only streams when clients connect)
            with self.stats_lock:
                self.stats["start_time"] = time.time()
                self.stats["frames_sent"] = 0
                self.stats["bytes_sent"] = 0
                self.stats["last_stats_time"] = None
                self.stats["last_frames_count"] = 0
                self.stats["last_bytes_count"] = 0
                self.stats["current_fps"] = 0
                self.stats["current_bitrate"] = 0

            # Start RTSP client monitor - will activate stats when clients connect
            self._start_rtsp_client_monitor()

            # Get streaming IP
            ip_address = self._get_streaming_ip()
            rtsp_url = self.rtsp_server.get_url(ip_address)

            print("✅ RTSP Server started successfully")
            print(f"   📺 Connect with VLC: {rtsp_url}")

            self._broadcast_status()

            return {
                "success": True,
                "message": "RTSP Server started",
                "codec": self.video_config.codec,
                "resolution": f"{self.video_config.width}x{self.video_config.height}",
                "url": rtsp_url,
            }
        except Exception as e:
            print(f"❌ Failed to start RTSP Server: {e}")
            return {"success": False, "message": f"Failed to start RTSP Server: {str(e)}"}

    def stop(self) -> Dict[str, Any]:
        """Stop video streaming"""
        # Stop RTSP monitors if running
        if hasattr(self, "_rtsp_monitor_running") and self._rtsp_monitor_running:
            self._stop_rtsp_client_monitor()
        if hasattr(self, "_rtsp_stats_running") and self._rtsp_stats_running:
            self._stop_rtsp_stats_estimator()

        # Check if RTSP server is running
        if self.rtsp_server and self.rtsp_server.is_running():
            print("🛑 Stopping RTSP Server...")
            self.rtsp_server.stop()
            self.rtsp_server = None
            self.is_streaming = False
            self._broadcast_status()
            return {"success": True, "message": "RTSP Server stopped"}

        if not self.is_streaming and not self.pipeline:
            return {"success": False, "message": "Not streaming"}

        print("🛑 Stopping video stream...")

        # Stop WebRTC adapter if active
        if self.webrtc_adapter:
            try:
                self.webrtc_adapter.detach()
                self.webrtc_adapter = None
                print("✅ WebRTC adapter stopped")
            except Exception as e:
                print(f"⚠️ Error stopping WebRTC adapter: {e}")

        # Deactivate WebRTC service if active
        if self.webrtc_service and self.webrtc_service.is_active:
            try:
                self.webrtc_service.deactivate()
            except Exception as e:
                print(f"⚠️ Error deactivating WebRTC service: {e}")

        # Stop OpenCV processing thread if running
        self._stop_opencv_processing_thread()

        # Remove encoder stats probes before stopping pipeline
        self._remove_encoder_probes()

        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        if self.main_loop and self.main_loop.is_running():
            self.main_loop.quit()

        self.is_streaming = False
        self.current_encoder_provider = None
        self.current_source_provider = None
        self._stop_stats_broadcast()
        self._restore_cpu_mode()

        self._broadcast_status()

        return {"success": True, "message": "Streaming stopped"}

    def _start_rtsp_client_monitor(self):
        """Start monitoring RTSP clients and manage stats estimation"""
        import threading

        self._rtsp_monitor_running = True

        def monitor_clients():
            """Monitor RTSP clients and start/stop stats estimator accordingly"""
            import time

            stats_active = False

            while self._rtsp_monitor_running and self.is_streaming:
                time.sleep(1.0)  # Check every second

                if not self.is_streaming or not self.rtsp_server:
                    break

                # Get number of clients from RTSP server
                rtsp_stats = self.rtsp_server.get_stats()
                clients = rtsp_stats.get("clients_connected", 0)

                # Start stats when first client connects
                if clients > 0 and not stats_active:
                    print("📊 First RTSP client connected, starting stats estimation")
                    self._start_rtsp_stats_estimator()
                    stats_active = True

                # Stop stats when all clients disconnect
                elif clients == 0 and stats_active:
                    print("⏹️  All RTSP clients disconnected, stopping stats estimation")
                    self._stop_rtsp_stats_estimator()
                    stats_active = False
                    # Reset stats to 0
                    with self.stats_lock:
                        self.stats["frames_sent"] = 0
                        self.stats["bytes_sent"] = 0
                        self.stats["current_fps"] = 0
                        self.stats["current_bitrate"] = 0
                        self.stats["last_stats_time"] = None

        self._rtsp_monitor_thread = threading.Thread(target=monitor_clients, daemon=True)
        self._rtsp_monitor_thread.start()

    def _stop_rtsp_client_monitor(self):
        """Stop the RTSP client monitor thread"""
        if hasattr(self, "_rtsp_monitor_running"):
            self._rtsp_monitor_running = False
        if hasattr(self, "_rtsp_monitor_thread") and self._rtsp_monitor_thread:
            self._rtsp_monitor_thread.join(timeout=2)

    def _start_rtsp_stats_estimator(self):
        """Start a background thread to estimate RTSP statistics.

        RTSP mode runs its own internal GStreamer pipeline inside the RTSP
        server, so we cannot attach pad probes from outside.  Instead we
        estimate bytes/frames from configured parameters and use real
        RTSP session-pool data (client count) to only count stats when
        at least one client is actually receiving data.
        """
        import threading

        self._rtsp_stats_running = True

        def estimate_stats():
            import time

            with self.stats_lock:
                self.stats["last_stats_time"] = time.time()

            while self._rtsp_stats_running and self.is_streaming:
                time.sleep(1.0)

                if not self.is_streaming:
                    break

                # Only accumulate stats when there are active RTSP clients
                clients = 0
                if self.rtsp_server:
                    rtsp_info = self.rtsp_server.get_stats()
                    clients = rtsp_info.get("clients_connected", 0)

                if clients <= 0:
                    # No clients — zero out rate but don't accumulate
                    with self.stats_lock:
                        now = time.time()
                        self.stats["current_fps"] = 0
                        self.stats["current_bitrate"] = 0
                        self.stats["last_stats_time"] = now
                    continue

                with self.stats_lock:
                    # Use configured values as estimate (RTSP internal pipeline)
                    fps = self.video_config.framerate or 30
                    self.stats["frames_sent"] += fps

                    # Estimate bitrate from config, codec-aware
                    codec = (self.video_config.codec or "mjpeg").lower()
                    if "h264" in codec:
                        bps = (self.video_config.h264_bitrate or 2000) * 1000
                    else:
                        # MJPEG: estimate from quality + resolution + fps
                        quality = self.video_config.quality or 85
                        pixels = (self.video_config.width or 960) * (self.video_config.height or 720)
                        bpp = 0.3 + (quality / 100) * 1.7
                        bps = int(pixels * bpp * fps)

                    self.stats["bytes_sent"] += bps // 8

                    now = time.time()
                    self._update_rates_locked(now)

        self._rtsp_stats_thread = threading.Thread(target=estimate_stats, daemon=True)
        self._rtsp_stats_thread.start()

    def _stop_rtsp_stats_estimator(self):
        """Stop the RTSP statistics estimator thread"""
        if hasattr(self, "_rtsp_stats_running"):
            self._rtsp_stats_running = False
        if hasattr(self, "_rtsp_stats_thread") and self._rtsp_stats_thread:
            self._rtsp_stats_thread.join(timeout=2)

    def update_live_property(self, property_name: str, value) -> Dict[str, Any]:
        """Update a pipeline element property without restarting using provider info"""
        if not self.is_streaming or not self.pipeline:
            return {"success": False, "message": "Not streaming"}

        encoder = self.pipeline.get_by_name("encoder")
        if not encoder:
            return {"success": False, "message": "Encoder element not found"}

        codec_id = self.video_config.codec.lower()

        try:
            # Import here to avoid circular dependency
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            provider = registry.get_video_encoder(codec_id)

            if provider:
                # Use provider to get live adjustable properties
                adjustable = provider.get_live_adjustable_properties()

                if property_name not in adjustable:
                    allowed = ", ".join(adjustable.keys()) if adjustable else "none"
                    return {
                        "success": False,
                        "message": f"Cannot change '{property_name}' live with {codec_id}. Allowed: {allowed}",
                    }

                prop_info = adjustable[property_name]

                # Clamp value to allowed range
                value = max(prop_info["min"], min(prop_info["max"], int(value)))

                # Apply multiplier if needed (e.g., OpenH264 uses bps instead of kbps)
                actual_value = value * prop_info.get("multiplier", 1)

                # Set the property on the encoder
                encoder.set_property(prop_info["property"], actual_value)

                # Update config
                if property_name == "quality":
                    self.video_config.quality = value
                elif property_name == "bitrate" or property_name == "h264_bitrate":
                    self.video_config.h264_bitrate = value

                print(f"🎛️ Live update ({provider.display_name}): {property_name} → {value}")
                self._broadcast_status()

                return {
                    "success": True,
                    "message": f"{prop_info['description']}: {value}",
                    "property": property_name,
                    "value": value,
                }

        except Exception as e:
            error_msg = f"Failed to update property: {e}"
            print(f"❌ {error_msg}")
            return {"success": False, "message": error_msg}

    def restart(self) -> Dict[str, Any]:
        """Restart video streaming with current configuration"""
        self.stop()
        import time

        time.sleep(0.5)
        return self.start()

    def get_status(self) -> Dict[str, Any]:
        """Get current streaming status with detailed metrics"""
        import time

        uptime = None
        if self.stats["start_time"] and self.is_streaming:
            uptime = int(time.time() - self.stats["start_time"])

        # Thread-safe stats copy
        with self.stats_lock:
            stats_copy = dict(self.stats)

        # Format stats for frontend
        stats_formatted = {
            "uptime": uptime,
            "uptime_formatted": self._format_uptime(uptime) if uptime else "-",
            "errors": stats_copy.get("errors", 0),
            "frames_sent": stats_copy.get("frames_sent", 0),
            "bytes_sent": stats_copy.get("bytes_sent", 0),
            "bytes_sent_mb": round(stats_copy.get("bytes_sent", 0) / (1024 * 1024), 2),
            "current_fps": stats_copy.get("current_fps", 0),
            "current_bitrate": stats_copy.get("current_bitrate", 0),
            "current_bitrate_formatted": f"{stats_copy.get('current_bitrate', 0)} kbps",
            "health": self._calculate_health(
                stats_copy.get("errors", 0),
                stats_copy.get("current_fps", 0),
                self.video_config.framerate,
            ),
        }

        return {
            "available": GSTREAMER_AVAILABLE,
            "streaming": self.is_streaming,
            "enabled": self.streaming_config.enabled,
            "config": {
                "device": self.video_config.device,
                "codec": self.video_config.codec,
                "width": self.video_config.width,
                "height": self.video_config.height,
                "framerate": self.video_config.framerate,
                "quality": self.video_config.quality,
                "h264_bitrate": self.video_config.h264_bitrate,
                "auto_start": self.streaming_config.auto_start,
                # Streaming mode configuration
                "mode": self.streaming_config.mode,
                "udp_host": self.streaming_config.udp_host,
                "udp_port": self.streaming_config.udp_port,
                "multicast_group": self.streaming_config.multicast_group,
                "multicast_port": self.streaming_config.multicast_port,
                "multicast_ttl": self.streaming_config.multicast_ttl,
                "rtsp_enabled": self.streaming_config.rtsp_enabled,
                "rtsp_url": self.streaming_config.rtsp_url,
                "rtsp_transport": self.streaming_config.rtsp_transport,
            },
            "stats": stats_formatted,
            "providers": {
                "encoder": self.current_encoder_provider,
                "source": self.current_source_provider,
            },
            "last_error": self.last_error,
            "pipeline_string": self.get_pipeline_string(),
            "rtsp_server": {
                "running": self.rtsp_server.is_running() if self.rtsp_server else False,
                "url": (
                    self.rtsp_server.get_url(self._get_streaming_ip())
                    if self.rtsp_server and self.rtsp_server.is_running()
                    else None
                ),
                "clients_connected": (
                    self.rtsp_server.get_stats().get("clients_connected", 0)
                    if self.rtsp_server and self.rtsp_server.is_running()
                    else 0
                ),
            },
            "webrtc": {
                "available": self.webrtc_service is not None,
                "adapter_active": self.webrtc_adapter is not None,
                "service_active": (self.webrtc_service.is_active if self.webrtc_service else False),
                "peers_connected": (
                    self.webrtc_service.global_stats.get("active_peers", 0) if self.webrtc_service else 0
                ),
            },
            "encoder_stats": self.encoder_stats.copy(),
        }

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime in seconds to HH:MM:SS format"""
        if not seconds:
            return "-"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _calculate_health(self, errors: int, current_fps: int, target_fps: int) -> str:
        """Calculate holistic stream health from FPS, errors, encoder stats,
        and (when available) the NetworkQualityScore from the event bridge.

        Returns ``'good'``, ``'fair'``, or ``'poor'``.
        """
        # --- 1. Pipeline component (0-100) ---
        if target_fps > 0:
            fps_pct = current_fps / target_fps * 100
        else:
            fps_pct = 100
        error_penalty = min(errors * 3, 30)  # up to -30
        pipeline_score = max(0, min(100, fps_pct - error_penalty))

        # --- 2. Encoder component (0-100) ---
        enc = self.encoder_stats
        encode_ms = enc.get("avg_encode_time_ms", 0.0)
        # Budget: ~33 ms at 30 fps, ~16 ms at 60 fps
        budget_ms = (1000 / target_fps * 0.8) if target_fps > 0 else 33
        if budget_ms > 0:
            enc_load = min(encode_ms / budget_ms, 1.0)
        else:
            enc_load = 0
        dropped = enc.get("frames_dropped_pre_encoder", 0) + enc.get("frames_dropped_post_encoder", 0)
        drop_penalty = min(dropped * 2, 20)
        encoder_score = max(0, 100 - int(enc_load * 50) - drop_penalty)

        # --- 3. Network component (0-100) — optional ---
        network_score: float = 75  # neutral default when bridge is not running
        try:
            from app.services.network_event_bridge import get_network_event_bridge

            bridge = get_network_event_bridge()
            if bridge._monitoring:
                network_score = bridge._quality_score.score
        except Exception:
            pass

        # --- Weighted composite ---
        composite = 0.45 * pipeline_score + 0.25 * encoder_score + 0.30 * network_score

        if composite >= 70:
            return "good"
        elif composite >= 40:
            return "fair"
        else:
            return "poor"

    # ------------------------------------------------------------------
    # Client receive-pipeline helpers
    # ------------------------------------------------------------------

    def get_client_pipeline_strings(self) -> Dict[str, Any]:
        """Return ready-to-paste GStreamer receive pipelines for every mode.

        Provides pipeline strings for UDP unicast, multicast, and RTSP so
        that Mission Planner / QGC users can quickly connect.
        """
        codec_id = self.video_config.codec.lower()
        ip = self._get_streaming_ip()
        udp_port = self.streaming_config.udp_port
        mc_group = self.streaming_config.multicast_group
        mc_port = self.streaming_config.multicast_port
        rtsp_url = self.streaming_config.rtsp_url or f"rtsp://{ip}:8554/fpv"

        result: Dict[str, Any] = {
            "active_mode": self.streaming_config.mode,
            "codec": codec_id,
            "pipelines": {},
        }

        # Determine depay / decode / encoding-name per codec family
        if "h265" in codec_id:
            enc_name, depay, parse, dec, pt = "H265", "rtph265depay", "h265parse", "avdec_h265", 96
        elif "h264" in codec_id:
            enc_name, depay, parse, dec, pt = "H264", "rtph264depay", "h264parse", "avdec_h264", 96
        else:
            enc_name, depay, parse, dec, pt = "JPEG", "rtpjpegdepay", None, "jpegdec", 26

        sink = "videoconvert ! video/x-raw,format=BGRA ! appsink name=outsink sync=false"
        sink_low_lat = (
            "videoconvert ! video/x-raw,format=BGRA ! appsink name=outsink sync=false max-buffers=1 drop=true"
        )

        # --- UDP unicast ---
        caps = (
            f'"application/x-rtp, media=(string)video, '
            f'clock-rate=(int)90000, encoding-name=(string){enc_name}, payload=(int){pt}"'
        )
        parse_elem = f" ! {parse}" if parse else ""
        result["pipelines"]["udp"] = {
            "description": f"UDP unicast on port {udp_port}",
            "pipeline": f"udpsrc port={udp_port} caps={caps} ! {depay}{parse_elem} ! {dec} ! {sink}",
        }

        # --- Multicast ---
        result["pipelines"]["multicast"] = {
            "description": f"Multicast {mc_group}:{mc_port}",
            "pipeline": (
                f"udpsrc multicast-group={mc_group} port={mc_port} auto-multicast=true "
                f"caps={caps} ! {depay}{parse_elem} ! {dec} ! {sink}"
            ),
        }

        # --- RTSP ---
        transport = (self.streaming_config.rtsp_transport or "tcp").lower()
        result["pipelines"]["rtsp"] = {
            "description": f"RTSP ({transport}) at {rtsp_url}",
            "pipeline": (
                f"rtspsrc location={rtsp_url} latency=20 protocols={transport} ! "
                f"{depay}{parse_elem} ! {dec} ! {sink_low_lat}"
            ),
        }

        return result

    def get_pipeline_string(self) -> str:
        """Get GStreamer pipeline string for Mission Planner using provider"""
        codec_id = self.video_config.codec.lower()
        port = self.streaming_config.udp_port
        mode = self.streaming_config.mode

        # If using RTSP Server, generate RTSP pipeline string
        if mode == "rtsp":
            return self._get_rtsp_pipeline_string()

        # Default UDP/multicast mode
        try:
            # Import here to avoid circular dependency
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            provider = registry.get_video_encoder(codec_id)

            if provider:
                if mode == "multicast":
                    mc_group = self.streaming_config.multicast_group
                    mc_port = self.streaming_config.multicast_port
                    return provider.get_pipeline_string_for_client(mc_port, multicast_group=mc_group)
                return provider.get_pipeline_string_for_client(port)

        except Exception as e:
            print(f"⚠️ Failed to get pipeline string from provider: {e}")

        # Should never reach here if providers are properly configured
        return f"udpsrc port={port} ! fakesink"

    def _get_rtsp_pipeline_string(self) -> str:
        """
        Generate RTSP pipeline string for RTSP server mode.
        Optimized for low-latency FPV streaming.
        """
        # Get appropriate IP address
        ip_address = self._get_streaming_ip()

        # Get RTSP URL from config or build default
        rtsp_url = self.streaming_config.rtsp_url
        if not rtsp_url or rtsp_url in ["rtsp://localhost:8554/fpv", "rtsp://localhost:8554/fpv/"]:
            # Replace localhost with actual IP
            rtsp_url = f"rtsp://{ip_address}:8554/fpv"

        # Remove trailing slash if present
        if rtsp_url.endswith("/"):
            rtsp_url = rtsp_url[:-1]

        # Get codec info
        codec_id = self.video_config.codec.lower()

        # Get transport protocol (tcp or udp)
        transport = self.streaming_config.rtsp_transport.lower() if self.streaming_config.rtsp_transport else "tcp"

        # Build RTSP pipeline based on codec
        if codec_id in ["h264", "h264_openh264", "h264_x264", "h264_omx", "h264_v4l2"]:
            # H.264 RTSP pipeline - compatible with Mission Planner
            # Note: Mission Planner requires explicit depay/parse/decode chain
            return (
                f"rtspsrc location={rtsp_url} "
                f"latency=20 protocols={transport} ! "
                f"rtph264depay ! "
                f"h264parse ! "
                f"avdec_h264 ! "
                f"videoconvert ! "
                f"video/x-raw,format=BGRx ! "
                f"appsink name=outsink sync=false max-buffers=1 drop=true"
            )
        elif codec_id in ["h265", "h265_x265"]:
            # H.265 RTSP pipeline
            return (
                f"rtspsrc location={rtsp_url} "
                f"latency=20 protocols={transport} ! "
                f"rtph265depay ! "
                f"h265parse ! "
                f"avdec_h265 ! "
                f"videoconvert ! "
                f"video/x-raw,format=BGRx ! "
                f"appsink name=outsink sync=false max-buffers=1 drop=true"
            )
        else:  # MJPEG
            # MJPEG RTSP pipeline - compatible with Mission Planner
            return (
                f"rtspsrc location={rtsp_url} "
                f"latency=20 protocols={transport} ! "
                f"rtpjpegdepay ! "
                f"jpegdec ! "
                f"videoconvert ! "
                f"video/x-raw,format=BGRx ! "
                f"appsink name=outsink sync=false max-buffers=1 drop=true"
            )

    def _get_streaming_ip(self) -> str:
        """
        Get the appropriate IP address for streaming.
        Priority: VPN IP (Tailscale) > Local WiFi IP > Fallback
        Uses caching to avoid excessive recalculation and logging.
        """
        import subprocess
        import time

        # Check cache first
        current_time = time.time()
        if self._cached_ip and (current_time - self._cached_ip_time) < self._cached_ip_ttl:
            return self._cached_ip

        old_ip = self._cached_ip
        new_ip = None

        try:
            # Check for Tailscale VPN interface
            result = subprocess.run(
                ["ip", "-o", "-4", "addr", "show", "tailscale0"], capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0 and result.stdout:
                # Extract IP from: "5: tailscale0    inet 100.x.x.x/32 ..."
                parts = result.stdout.split()
                for i, part in enumerate(parts):
                    if part == "inet" and i + 1 < len(parts):
                        new_ip = parts[i + 1].split("/")[0]
                        break
        except Exception:
            pass

        if not new_ip:
            try:
                # Get local WiFi/Ethernet IP (exclude loopback and docker)
                result = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        # Skip loopback, docker, and local interfaces
                        if any(iface in line for iface in ["lo:", "docker", "veth"]):
                            continue
                        if "inet " in line:
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if part == "inet" and i + 1 < len(parts):
                                    ip = parts[i + 1].split("/")[0]
                                    # Skip 127.x.x.x and 172.17.x.x (docker)
                                    if not ip.startswith("127.") and not ip.startswith("172.17."):
                                        new_ip = ip
                                        break
                            if new_ip:
                                break
            except Exception:
                pass

        # Fallback to localhost if nothing found
        if not new_ip:
            new_ip = "localhost"

        # Update cache
        self._cached_ip = new_ip
        self._cached_ip_time = current_time

        # Only log if IP changed or first time
        if old_ip != new_ip:
            if "tailscale0" in str(new_ip) or new_ip.startswith("100."):
                print(f"📡 Using VPN IP for streaming: {new_ip}")
            elif new_ip == "localhost":
                print("⚠️ Using fallback IP: localhost")
            else:
                print(f"📡 Using local IP for streaming: {new_ip}")

        return new_ip

    def _broadcast_status(self):
        """Broadcast status via WebSocket"""
        if not self.websocket_manager or not self.event_loop:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("video_status", self.get_status()),
                self.event_loop,
            )
        except Exception:
            pass

    def _broadcast_stats_fast(self):
        """Broadcast lightweight numeric stats at high frequency.

        Sends only the fields needed for a responsive UI gauge:
        fps, bitrate, encode_time, health.  Keeps the full
        ``video_status`` message at 1 Hz for compatibility.
        """
        if not self.websocket_manager or not self.event_loop:
            return

        try:
            with self.stats_lock:
                fps = self.stats.get("current_fps", 0)
                bitrate = self.stats.get("current_bitrate", 0)

            payload = {
                "fps": fps,
                "bitrate_kbps": bitrate,
                "avg_encode_time_ms": self.encoder_stats.get("avg_encode_time_ms", 0.0),
                "keyframes_sent": self.encoder_stats.get("keyframes_sent", 0),
            }
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("video_stats_fast", payload),
                self.event_loop,
            )
        except Exception:
            pass

    def _start_stats_broadcast(self):
        if self.stats_thread and self.stats_thread.is_alive():
            return

        self.stats_stop_event.clear()

        def _loop():
            import time

            tick = 0
            while not self.stats_stop_event.is_set():
                if self.is_streaming:
                    # High-frequency lightweight stats every ~250 ms (4 Hz)
                    self._broadcast_stats_fast()
                    # Full status every 1 s (every 4th tick)
                    if tick % 4 == 0:
                        self._broadcast_status()
                    tick += 1
                time.sleep(0.25)

        self.stats_thread = threading.Thread(target=_loop, daemon=True, name="VideoStatsBroadcast")
        self.stats_thread.start()

    def _stop_stats_broadcast(self):
        self.stats_stop_event.set()
        if self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=1.0)
        self.stats_thread = None

    def shutdown(self):
        """Cleanup on shutdown"""
        self.stop()
        print("🛑 GStreamer service shutdown")


# Global instance
_gstreamer_service: Optional[GStreamerService] = None


def get_gstreamer_service() -> Optional[GStreamerService]:
    """Get the global GStreamer service instance"""
    return _gstreamer_service


def init_gstreamer_service(websocket_manager=None, event_loop=None, webrtc_service=None) -> GStreamerService:
    """Initialize the global GStreamer service"""
    global _gstreamer_service
    _gstreamer_service = GStreamerService(websocket_manager, event_loop, webrtc_service)
    return _gstreamer_service
