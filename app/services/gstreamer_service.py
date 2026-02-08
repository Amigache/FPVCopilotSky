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
    get_available_cameras,
)


class GStreamerService:
    """
    GStreamer video streaming service with:
    - UVC camera input
    - MJPEG or H.264 encoding (configurable)
    - UDP/RTP output for Mission Planner
    - Low-latency optimizations
    """

    def __init__(self, websocket_manager=None, event_loop=None):
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop

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
        print(f"📡 Streaming to: {self.streaming_config.udp_host}:{self.streaming_config.udp_port}")

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

        codec_id = self.video_config.codec.lower()

        # Adapt codec based on board capabilities
        codec_id = self._adapt_codec_to_board(codec_id)

        # Build pipeline using provider
        return self._build_pipeline_from_provider(codec_id)

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

    def _build_pipeline_from_provider(self, codec_id: str) -> bool:
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

            # Add UDP sink
            udpsink = Gst.ElementFactory.make("udpsink", "udpsink")
            udpsink.set_property("host", self.streaming_config.udp_host)
            udpsink.set_property("port", self.streaming_config.udp_port)
            udpsink.set_property("sync", False)
            udpsink.set_property("async", False)

            pipeline.add(udpsink)
            elements_list.append(udpsink)

            # Link all elements in order
            for i in range(len(elements_list) - 1):
                if not elements_list[i].link(elements_list[i + 1]):
                    src_name = elements_list[i].get_name()
                    dst_name = elements_list[i + 1].get_name()
                    print(f"❌ Failed to link {src_name} → {dst_name}")
                    return False

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

            # Count bytes on the wire from udpsink sink pad
            udpsink = self.pipeline.get_by_name("udpsink")
            if udpsink:
                pad = udpsink.get_static_pad("sink")
                if pad:
                    pad.add_probe(probe_types, self._on_bytes_probe)
            else:
                # Fallback: count bytes at RTP payloader if udpsink is unavailable
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
            self._broadcast_status()

        elif t == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            print(f"⚠️ GStreamer Warning: {warn}")

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

        # Validate streaming configuration
        if not self.streaming_config.udp_host:
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

    def stop(self) -> Dict[str, Any]:
        """Stop video streaming"""
        if not self.is_streaming and not self.pipeline:
            return {"success": False, "message": "Not streaming"}

        print("🛑 Stopping video stream...")

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
                "udp_host": self.streaming_config.udp_host,
                "udp_port": self.streaming_config.udp_port,
                "auto_start": self.streaming_config.auto_start,
            },
            "stats": stats_formatted,
            "providers": {
                "encoder": self.current_encoder_provider,
                "source": self.current_source_provider,
            },
            "last_error": self.last_error,
            "pipeline_string": self.get_pipeline_string(),
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

    def get_cameras(self) -> list:
        """Get available cameras"""
        return get_available_cameras()

    def get_pipeline_string(self) -> str:
        """Get GStreamer pipeline string for Mission Planner using provider"""
        codec_id = self.video_config.codec.lower()
        port = self.streaming_config.udp_port

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


def init_gstreamer_service(websocket_manager=None, event_loop=None) -> GStreamerService:
    """Initialize the global GStreamer service"""
    global _gstreamer_service
    _gstreamer_service = GStreamerService(websocket_manager, event_loop)
    return _gstreamer_service
