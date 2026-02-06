# VIDEO_STREAM_INFORMATION MAVLink Integration

## Overview

FPV Copilot Sky now sends the **VIDEO_STREAM_INFORMATION** MAVLink message (ID 269) to autopilots, which allows GCS applications like Mission Planner to automatically detect and display your video stream in the "Pop-Out or within Map" feature.

## How It Works

1. **Automatic Detection**: When video stream is active, FPV Copilot Sky sends `VIDEO_STREAM_INFORMATION` messages every 1 second
2. **Mission Planner Integration**: Mission Planner reads these messages and populates the "Detected Streams" dropdown
3. **One-Click Selection**: No need to manually enter GStreamer pipeline - just select from detected streams

## Using with Mission Planner

### Step 1: Start Video Stream
1. Open FPV Copilot Sky web interface
2. Go to **Video** tab
3. Configure your video settings (camera, resolution, FPS, codec, etc.)
4. Click **▶️ Start** to begin streaming

### Step 2: Connect to Mission Planner
1. In Mission Planner, go to **Data** screen
2. Right-click on the map area
3. Select **Gimbal Video** → **Pop Out** (or **Full Sized** or **Mini**)
4. You should see "No Video" in the new window
5. Right-click on "No Video" and select **Video Stream**

### Step 3: Auto-Detect Stream
The "VideoStreamSelector" window will appear with:
- **Detected Streams** dropdown - should show "FPV Camera" and other available streams
- **Stream Type**: Shows detected stream type (RTP/UDP in our case)
- **URI**: Automatically populated with the stream location

### Step 4: Start Watching
1. Select the stream from "Detected Streams"
2. The video should start playing automatically
3. You can control gimbal movements with left-click and keyboard shortcuts

## Message Content

The `VIDEO_STREAM_INFORMATION` message includes:

| Field | Value | Description |
|-------|-------|-------------|
| stream_id | 1 | First (primary) stream |
| count | 1 | Total number of available streams |
| type | 1 | RTP-UDP stream type |
| flags | 1 | Stream is running |
| framerate | Configured FPS | e.g., 30 Hz |
| resolution_h | Width | e.g., 960 px |
| resolution_v | Height | e.g., 720 px |
| bitrate | Estimated | Calculated from resolution × FPS |
| rotation | 0 | No image rotation |
| hfov | 0 | Horizontal FOV (unknown) |
| name | "FPV Camera" | Descriptive stream name |
| uri | "udp://IP:PORT" | Destination network address |
| encoding | H.264 or Unknown | Based on selected codec |
| camera_device_id | 0 | MAVLink camera (not autopilot-attached) |

## Troubleshooting

### Stream Not Detected
- **Ensure MAVLink connection is active**: Connect to autopilot first
- **Check video is streaming**: Confirm "▶️ Streaming" status in web UI
- **Verify UDP port is open**: Firewall may be blocking the port
- **Check destination IP**: Must match your ground station IP

### Stream Shows but Won't Play
- **Verify network connectivity**: Can you ping the drone/vehicle?
- **Check GStreamer pipeline**: Manually verify by right-clicking and entering GStreamer pipeline
- **Monitor firewall**: Some firewalls drop video traffic

### Multiple Streams
Currently, FPV Copilot Sky advertises 1 stream. Future versions may support:
- Multiple camera types (thermal, normal, infrared)
- Different resolutions/codecs simultaneously
- Stream-specific recording settings

## Advanced: Custom Stream Name

To customize the stream name shown in Mission Planner:

1. Connect to FPV Copilot Sky via SSH or file editor
2. Edit `app/services/video_stream_info.py`
3. Change line:
   ```python
   self.stream_name: str = "FPV Camera"
   ```
8. Restart FPV Copilot Sky service

## Protocol Details

**MAVLink Message 269 - VIDEO_STREAM_INFORMATION**

Reference: https://mavlink.io/en/messages/common.html#VIDEO_STREAM_INFORMATION

The message is broadcast periodically to:
- Autopilot (via serial/MAVLink)
- Any connected GCS/telemetry clients
- Network clients listening on MAVLink ports

**Send Frequency**: Every 1 second when streaming is active

**Stream Types Supported**:
- `VIDEO_STREAM_TYPE_RTPUDP` → RTP over UDP (our implementation)
- Also compatible with RTSP (could be extended)

**Encodings**:
- `VIDEO_STREAM_ENCODING_H264` → H.264 codec
- `VIDEO_STREAM_ENCODING_UNKNOWN` → MJPEG or other

## Integration with Other Tools

This MAVLink message standard is also supported by:
- **ArduPlanner** (ArduPilot ground station)
- **QGroundControl** (with VIDEO_STREAM_INFORMATION support)
- **Custom GCS applications** that implement MAVLink video discovery

## See Also

- [ArduPilot Live Video Documentation](https://ardupilot.org/planner/docs/live-video.html)
- [VIDEO_STREAM_INFORMATION MAVLink Spec](https://mavlink.io/en/messages/common.html#VIDEO_STREAM_INFORMATION)
- [MAVLink Camera Protocol](https://mavlink.io/en/services/camera.html)
