"""
GStreamer Video Streaming Service
Supports MJPEG and H.264 encoding with UDP/RTP output for Mission Planner
Optimized for ultra-low latency FPV streaming
"""

import os
import subprocess
import threading
import asyncio
from typing import Optional, Dict, Any, Callable

# Check if GStreamer is available
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
    GSTREAMER_AVAILABLE = True
except (ImportError, ValueError):
    GSTREAMER_AVAILABLE = False
    Gst = None
    GLib = None

from .video_config import VideoConfig, StreamingConfig, auto_detect_camera, get_available_cameras


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
        
        # Statistics
        self.stats = {
            "frames_sent": 0,
            "bytes_sent": 0,
            "errors": 0,
            "start_time": None
        }
        
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
        
        print(f"📹 Video config updated: {self.video_config.width}x{self.video_config.height}@{self.video_config.framerate}fps")
        print(f"📡 Streaming to: {self.streaming_config.udp_host}:{self.streaming_config.udp_port}")
        
        # Broadcast updated status
        self._broadcast_status()
    
    def _build_mjpeg_pipeline(self) -> Any:
        """
        Build MJPEG pipeline for ultra-low latency
        Pipeline: v4l2src → jpegdec → jpegenc → rtpjpegpay → udpsink
        """
        if not GSTREAMER_AVAILABLE:
            return None
        
        print("🔧 Building MJPEG pipeline...")
        
        pipeline = Gst.Pipeline.new("fpv-mjpeg-pipeline")
        
        # Source: UVC camera
        source = Gst.ElementFactory.make("v4l2src", "source")
        source.set_property("device", self.video_config.device)
        source.set_property("do-timestamp", True)
        
        # Caps filter - request MJPEG from camera
        caps_str = (
            f"image/jpeg,width={self.video_config.width},"
            f"height={self.video_config.height},"
            f"framerate={self.video_config.framerate}/1"
        )
        caps_filter = Gst.ElementFactory.make("capsfilter", "caps_filter")
        caps_filter.set_property("caps", Gst.Caps.from_string(caps_str))
        
        # MJPEG decoder
        decoder = Gst.ElementFactory.make("jpegdec", "decoder")
        
        # Queue - minimal buffering for low latency
        queue_pre = Gst.ElementFactory.make("queue", "queue_pre")
        queue_pre.set_property("max-size-buffers", 2)
        queue_pre.set_property("max-size-time", 0)
        queue_pre.set_property("max-size-bytes", 0)
        queue_pre.set_property("leaky", 2)  # Leak downstream (drop old frames)
        
        # Video conversion
        videoconvert = Gst.ElementFactory.make("videoconvert", "videoconvert")
        
        # MJPEG encoder
        encoder = Gst.ElementFactory.make("jpegenc", "encoder")
        encoder.set_property("quality", self.video_config.quality)
        
        # Queue for UDP output
        queue_udp = Gst.ElementFactory.make("queue", "queue_udp")
        queue_udp.set_property("max-size-buffers", 3)
        queue_udp.set_property("max-size-time", 0)
        queue_udp.set_property("max-size-bytes", 0)
        queue_udp.set_property("leaky", 2)
        
        # RTP payloader for MJPEG
        rtppay = Gst.ElementFactory.make("rtpjpegpay", "rtppay")
        rtppay.set_property("pt", 26)  # Payload type 26 for JPEG
        rtppay.set_property("mtu", 1400)
        
        # UDP sink
        udpsink = Gst.ElementFactory.make("udpsink", "udpsink")
        udpsink.set_property("host", self.streaming_config.udp_host)
        udpsink.set_property("port", self.streaming_config.udp_port)
        udpsink.set_property("sync", False)
        udpsink.set_property("async", False)
        
        # Add elements
        elements = [source, caps_filter, decoder, queue_pre, videoconvert, encoder, queue_udp, rtppay, udpsink]
        for element in elements:
            if not element:
                print(f"❌ Failed to create GStreamer element")
                return None
            pipeline.add(element)
        
        # Link elements
        links = [
            (source, caps_filter),
            (caps_filter, decoder),
            (decoder, queue_pre),
            (queue_pre, videoconvert),
            (videoconvert, encoder),
            (encoder, queue_udp),
            (queue_udp, rtppay),
            (rtppay, udpsink)
        ]
        
        for src, dst in links:
            if not src.link(dst):
                print(f"❌ Failed to link {src.get_name()} → {dst.get_name()}")
                return None
        
        print("✅ MJPEG pipeline built successfully")
        return pipeline
    
    def _build_h264_pipeline(self) -> Any:
        """
        Build H.264 pipeline for better compression
        Pipeline: v4l2src → jpegdec → x264enc → rtph264pay → udpsink
        """
        if not GSTREAMER_AVAILABLE:
            return None
        
        print("🔧 Building H.264 pipeline...")
        
        pipeline = Gst.Pipeline.new("fpv-h264-pipeline")
        
        # Source: UVC camera
        source = Gst.ElementFactory.make("v4l2src", "source")
        source.set_property("device", self.video_config.device)
        source.set_property("do-timestamp", True)
        
        # Caps filter - request MJPEG from camera
        caps_str = (
            f"image/jpeg,width={self.video_config.width},"
            f"height={self.video_config.height},"
            f"framerate={self.video_config.framerate}/1"
        )
        caps_filter = Gst.ElementFactory.make("capsfilter", "caps_filter")
        caps_filter.set_property("caps", Gst.Caps.from_string(caps_str))
        
        # MJPEG decoder
        decoder = Gst.ElementFactory.make("jpegdec", "decoder")
        
        # Video conversion
        videoconvert = Gst.ElementFactory.make("videoconvert", "videoconvert")
        
        # Video scaling
        videoscale = Gst.ElementFactory.make("videoscale", "videoscale")
        
        # Caps filter for encoder input (I420 format)
        encoder_caps_str = (
            f"video/x-raw,format=I420,width={self.video_config.width},"
            f"height={self.video_config.height},"
            f"framerate={self.video_config.framerate}/1"
        )
        encoder_caps = Gst.ElementFactory.make("capsfilter", "encoder_caps")
        encoder_caps.set_property("caps", Gst.Caps.from_string(encoder_caps_str))
        
        # H.264 encoder - optimized for low latency
        encoder = Gst.ElementFactory.make("x264enc", "encoder")
        encoder.set_property("bitrate", self.video_config.h264_bitrate)
        encoder.set_property("speed-preset", self.video_config.h264_preset)
        encoder.set_property("tune", 0x00000004)  # zerolatency
        encoder.set_property("key-int-max", self.video_config.framerate * 2)
        encoder.set_property("bframes", 0)
        encoder.set_property("threads", 2)
        encoder.set_property("sliced-threads", True)
        
        # H.264 parser
        h264parse = Gst.ElementFactory.make("h264parse", "h264parse")
        h264parse.set_property("config-interval", -1)
        
        # RTP payloader for H.264
        rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
        rtppay.set_property("pt", 96)
        rtppay.set_property("mtu", 1400)
        rtppay.set_property("config-interval", -1)
        
        # UDP sink
        udpsink = Gst.ElementFactory.make("udpsink", "udpsink")
        udpsink.set_property("host", self.streaming_config.udp_host)
        udpsink.set_property("port", self.streaming_config.udp_port)
        udpsink.set_property("sync", False)
        udpsink.set_property("async", False)
        
        # Add elements
        elements = [
            source, caps_filter, decoder, videoconvert, videoscale,
            encoder_caps, encoder, h264parse, rtppay, udpsink
        ]
        for element in elements:
            if not element:
                print(f"❌ Failed to create GStreamer element")
                return None
            pipeline.add(element)
        
        # Link elements
        links = [
            (source, caps_filter),
            (caps_filter, decoder),
            (decoder, videoconvert),
            (videoconvert, videoscale),
            (videoscale, encoder_caps),
            (encoder_caps, encoder),
            (encoder, h264parse),
            (h264parse, rtppay),
            (rtppay, udpsink)
        ]
        
        for src, dst in links:
            if not src.link(dst):
                print(f"❌ Failed to link {src.get_name()} → {dst.get_name()}")
                return None
        
        print("✅ H.264 pipeline built successfully")
        return pipeline
    
    def build_pipeline(self) -> bool:
        """Build the pipeline based on codec selection"""
        if not GSTREAMER_AVAILABLE:
            self.last_error = "GStreamer not available"
            return False
        
        codec = self.video_config.codec.lower()
        
        if codec == "h264":
            self.pipeline = self._build_h264_pipeline()
        else:
            self.pipeline = self._build_mjpeg_pipeline()
        
        if self.pipeline:
            # Setup bus for messages
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)
            return True
        
        return False
    
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
                    with open(governor_path, 'w') as f:
                        f.write('performance')
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
                    with open(governor_path, 'w') as f:
                        f.write('ondemand')
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
        
        # Auto-detect camera if needed
        if not os.path.exists(self.video_config.device):
            detected = auto_detect_camera()
            if os.path.exists(detected):
                self.video_config.device = detected
                print(f"📷 Auto-detected camera: {detected}")
            else:
                return {"success": False, "message": f"Camera not found: {self.video_config.device}"}
        
        # Build pipeline
        if not self.build_pipeline():
            return {"success": False, "message": self.last_error or "Failed to build pipeline"}
        
        # Optimize system
        self._optimize_for_streaming()
        
        # Start GLib main loop in background thread
        self.main_loop = GLib.MainLoop()
        self.main_loop_thread = threading.Thread(
            target=self.main_loop.run,
            daemon=True,
            name="GLibMainLoop"
        )
        self.main_loop_thread.start()
        
        # Start pipeline
        import time
        self.stats["start_time"] = time.time()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        
        if ret == Gst.StateChangeReturn.FAILURE:
            self.last_error = "Failed to start pipeline"
            return {"success": False, "message": self.last_error}
        
        self.is_streaming = True
        print(f"🎥 Video streaming started: {self.video_config.codec.upper()} → {self.streaming_config.udp_host}:{self.streaming_config.udp_port}")
        
        self._broadcast_status()
        
        return {
            "success": True, 
            "message": "Streaming started",
            "codec": self.video_config.codec,
            "resolution": f"{self.video_config.width}x{self.video_config.height}",
            "destination": f"{self.streaming_config.udp_host}:{self.streaming_config.udp_port}"
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
        self._restore_cpu_mode()
        
        self._broadcast_status()
        
        return {"success": True, "message": "Streaming stopped"}
    
    def restart(self) -> Dict[str, Any]:
        """Restart video streaming with current configuration"""
        self.stop()
        import time
        time.sleep(0.5)
        return self.start()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current streaming status"""
        import time
        
        uptime = None
        if self.stats["start_time"] and self.is_streaming:
            uptime = int(time.time() - self.stats["start_time"])
        
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
                "auto_start": self.streaming_config.auto_start
            },
            "stats": {
                "uptime": uptime,
                "errors": self.stats["errors"]
            },
            "last_error": self.last_error,
            "pipeline_string": self.get_pipeline_string()
        }
    
    def get_cameras(self) -> list:
        """Get available cameras"""
        return get_available_cameras()
    
    def get_pipeline_string(self) -> str:
        """Get GStreamer pipeline string for Mission Planner"""
        codec = self.video_config.codec.lower()
        port = self.streaming_config.udp_port
        
        if codec == "h264":
            return (
                f'udpsrc port={port} caps="application/x-rtp, media=(string)video, '
                f'clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96" ! '
                f'rtph264depay ! avdec_h264 ! videoconvert ! '
                f'video/x-raw,format=BGRA ! appsink name=outsink sync=false'
            )
        else:
            return (
                f'udpsrc port={port} caps="application/x-rtp, media=(string)video, '
                f'clock-rate=(int)90000, encoding-name=(string)JPEG, payload=(int)26" ! '
                f'rtpjpegdepay ! jpegdec ! videoconvert ! '
                f'video/x-raw,format=BGRA ! appsink name=outsink sync=false'
            )
    
    def _broadcast_status(self):
        """Broadcast status via WebSocket"""
        if not self.websocket_manager or not self.event_loop:
            return
        
        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("video_status", self.get_status()),
                self.event_loop
            )
        except Exception:
            pass
    
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
