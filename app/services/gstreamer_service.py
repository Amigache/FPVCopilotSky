"""
GStreamer Video Streaming Service
Supports MJPEG and H.264 encoding with UDP/RTP output for Mission Planner
Optimized for ultra-low latency FPV streaming
Uses provider-based architecture for codec-agnostic encoding
"""

import os
import threading
import asyncio
from typing import Optional, Dict, Any

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

from .video_config import (
    VideoConfig,
    StreamingConfig,
    auto_detect_camera,
)
from .rtsp_server import RTSPServer


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
            print("✅ GStreamer initialized")
        else:
            print("⚠️ GStreamer not available - video streaming disabled")

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
            from providers.board import BoardRegistry

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
                print(f"   → Using x264enc (ultrafast/zerolatency) @ {bitrate_kbps} kbps")
            else:
                openh264enc = Gst.ElementFactory.make("openh264enc", "webrtc_h264enc")
                if openh264enc:
                    encoder_name = "openh264enc"
                    openh264enc.set_property("bitrate", bitrate_kbps * 1000)
                    openh264enc.set_property("complexity", 0)  # low complexity
                    pipeline.add(openh264enc)
                    elements.append(openh264enc)
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
            for i in range(len(elements) - 1):
                if not elements[i].link(elements[i + 1]):
                    src_name = elements[i].get_name()
                    dst_name = elements[i + 1].get_name()
                    self.last_error = f"Failed to link {src_name} → {dst_name}"
                    print(f"❌ {self.last_error}")
                    return False

            # ── Connect appsink signal ──
            appsink.connect("new-sample", self._on_webrtc_appsink_sample)

            # ── GStreamer bus ──
            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)

            self.pipeline = pipeline
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

        E.g., if user requests HW H.264 but board doesn't support it,
        fallback to x264 software encoder.

        Args:
            codec_id: Requested codec (e.g., 'h264_hw', 'x264', 'mjpeg')

        Returns:
            Adapted codec_id that's supported on this board
        """
        try:
            from providers.board import BoardRegistry

            detected_board = BoardRegistry().get_detected_board()
            if not detected_board:
                # No board detection, use requested codec as-is
                return codec_id

            # Check available encoders on this board
            available_encoders = [f.value for f in detected_board.variant.video_encoders]

            print(f"📊 Board supports encoders: {available_encoders}")
            print(f"   User requested: {codec_id}")

            # Normalize UI/alias codec IDs to registry codec IDs
            requested_codec_id = codec_id
            normalized_codec_id = "h264" if requested_codec_id == "x264" else requested_codec_id

            # Map codec ID to board feature names
            codec_to_feature = {
                "h264_hw": "hardware_h264",
                "h264": "hardware_h264",
                "h264_hw_meson": "hardware_h264",
                "x264": "x264",
                "mjpeg": "mjpeg",
                "openh264": "openh264",
            }

            requested_feature = codec_to_feature.get(requested_codec_id)

            # If requested codec is supported, use it
            if requested_feature and requested_feature in available_encoders:
                print(f"✅ Using requested {requested_codec_id} (supported on board)")
                return normalized_codec_id

            # If not supported, fallback strategy:
            # hardware_h264 → x264 → mjpeg
            if requested_feature == "hardware_h264" and "x264" in available_encoders:
                print(f"⚠️ {requested_codec_id} not supported, falling back to x264")
                return "h264"

            if requested_feature in ["hardware_h264", "x264"] and "mjpeg" in available_encoders:
                print(f"⚠️ {requested_codec_id} not supported, falling back to mjpeg")
                return "mjpeg"

            # If we got here, just use what was requested
            # Provider will handle errors if truly not available
            print(f"⚠️ {requested_codec_id} not in board features, attempting anyway")
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

            # Build config dict from video_config
            config = {
                "width": self.video_config.width,
                "height": self.video_config.height,
                "framerate": self.video_config.framerate,
                "bitrate": self.video_config.h264_bitrate,
                "quality": self.video_config.quality,
                "gop_size": self.video_config.gop_size,
            }

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

            # Get video source provider
            registry = get_provider_registry()

            # Find which source provider handles this device
            source_provider = None
            source_config_result = None

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

            # Build source element from provider
            source_config_result = source_provider.build_source_element(self.video_config.device, config)

            if not source_config_result["success"]:
                print(f"❌ Failed to build source element: {source_config_result.get('error')}")
                self.last_error = source_config_result.get("error", "Unknown error")
                return False

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

            for elem_config in pipeline_config["elements"]:
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

            # Add RTP payloader
            rtppay = Gst.ElementFactory.make(pipeline_config["rtp_payloader"], "rtppay")
            if not rtppay:
                print(f"❌ Failed to create RTP payloader: {pipeline_config['rtp_payloader']}")
                return False

            for prop, value in pipeline_config["rtp_payloader_properties"].items():
                rtppay.set_property(prop, value)

            pipeline.add(rtppay)
            elements_list.append(rtppay)

            # Create sink based on streaming mode
            sink = self._create_sink_for_mode()
            if not sink:
                print(f"❌ Failed to create sink for mode: {self.streaming_config.mode}")
                return False

            pipeline.add(sink)
            elements_list.append(sink)

            # Link all elements in order
            for i in range(len(elements_list) - 1):
                if not elements_list[i].link(elements_list[i + 1]):
                    src_name = elements_list[i].get_name()
                    dst_name = elements_list[i + 1].get_name()
                    print(f"❌ Failed to link {src_name} → {dst_name}")
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

            # Count encoded frames (one buffer per frame) from encoder src pad
            encoder = self.pipeline.get_by_name("encoder")
            if encoder:
                pad = encoder.get_static_pad("src")
                if pad:
                    pad.add_probe(probe_types, self._on_frame_probe)

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

        elif t == Gst.MessageType.EOS:
            print("📹 End of stream")
            self.stop()

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
                    print("⚡ CPU governor set to PERFORMANCE mode")
                except PermissionError:
                    # Don't block on sudo - just skip this optimization
                    print("ℹ️ CPU governor optimization skipped (no root access)")
        except Exception as e:
            print(f"ℹ️ CPU governor optimization skipped: {e}")

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

        ret = self.pipeline.set_state(Gst.State.PLAYING)

        if ret == Gst.StateChangeReturn.FAILURE:
            self.last_error = "Failed to start pipeline"
            return {"success": False, "message": self.last_error}

        self.is_streaming = True
        print(
            f"🎥 Video streaming started: {self.video_config.codec.upper()} → "
            f"{self.streaming_config.udp_host}:{self.streaming_config.udp_port}"
        )

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
        """Start a background thread to estimate RTSP statistics"""
        import threading

        self._rtsp_stats_running = True

        def estimate_stats():
            """Estimate statistics based on configured framerate and bitrate"""
            import time

            # Initialize timing
            with self.stats_lock:
                self.stats["last_stats_time"] = time.time()

            while self._rtsp_stats_running and self.is_streaming:
                time.sleep(1.0)  # Update every second

                if not self.is_streaming:
                    break

                with self.stats_lock:
                    # Estimate frames: framerate per second
                    self.stats["frames_sent"] += self.video_config.framerate

                    # Estimate bytes: (bitrate in kbps * 1000 / 8) bytes per second
                    bytes_per_second = (self.video_config.h264_bitrate * 1000) // 8
                    self.stats["bytes_sent"] += bytes_per_second

                    # Update rates
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
        """Calculate stream health status: 'good', 'fair', or 'poor'"""
        if errors > 10:
            return "poor"
        fps_rate = (current_fps / target_fps * 100) if target_fps > 0 else 100
        if fps_rate >= 95 and errors <= 2:
            return "good"
        elif fps_rate >= 80 or errors <= 5:
            return "fair"
        else:
            return "poor"

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

    def _start_stats_broadcast(self):
        if self.stats_thread and self.stats_thread.is_alive():
            return

        self.stats_stop_event.clear()

        def _loop():
            import time

            while not self.stats_stop_event.is_set():
                if self.is_streaming:
                    self._broadcast_status()
                time.sleep(1.0)

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
