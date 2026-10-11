# Video tuning: grey frames, stutter and latency

Field notes from tuning the 1080p30 H.264 downlink from the Radxa (LTE modem,
USB-tethered) to a Windows ground station over Tailscale, watched in Mission
Planner. Written so the work can be resumed without re-deriving it.

Status at 1.4.1: **no grey frames, low latency, occasional stutter when the
Tailscale relay oscillates** (accepted for stable flight).

---

## 1. Topology

```
Radxa (LTE, enx*) --UDP 5600--> tailscale0 --(DERP relay "mad")--> PC (100.127.99.44)
                                                                       |
                                                    Mission Planner (GStreamer string)
```

- Video destination: `udp_host = 100.127.99.44` (ground PC), `udp_port = 5600`.
- Companion IP advertised to MAVLink: `100.80.37.49` (Tailscale), so
  `VIDEO_STREAM_INFORMATION` announces `udp://100.80.37.49:5600`.
- `tailscale netcheck`: UDP works, `MappingVariesByDestIP: true` (hard NAT),
  `PortMapping: UPnP`. Direct connection is **never established**; all traffic
  goes through the DERP relay (Madrid).

## 2. Root causes found

| #   | Symptom                                         | Cause                                                                                                                                                                                                           | Fix                                                                                                                                                  |
| --- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Grey frames                                     | RTP packets 1300 B + headers ≈ 1340 B over tailscale0 (MTU 1280) → IP fragmentation. Losing one fragment loses the whole RTP packet → broken H.264 references. Measured `FragCreates` ≈ 551 k at boot, growing. | RTP `mtu` capped to the MTU of the route to the sink host minus 40 B (`_rtp_mtu_for_destination`, `rtp_mtu_limit`). Result: `FragCreates` delta = 0. |
| 2   | Grey frames over time                           | Adaptive bitrate was still **enabled in persisted preferences** (defaults only apply to new installs). Bitrate drifted 3.2 → 3.4 Mbps.                                                                          | Disabled via `POST /api/video/config/auto-adaptive-bitrate` and `…/auto-adaptive-resolution` (`{"enabled": false}`).                                 |
| 3   | Bitrate dropped silently even with adaptive off | `NetworkEventBridge._adjust_bitrate_percent` was called from SINR/jitter/loss events without checking the opt-in. 2000 × 0.7 = 1400 kbps (seen in MPP logs).                                                    | `_auto_bitrate_allowed()` gate in `_adjust_bitrate_percent` (fail-safe: no change if prefs can't be read).                                           |
| 4   | Grey frames at the receiver                     | Mission Planner GStreamer string had no receive socket buffer and no jitter buffer. Keyframe bursts overflow the default socket buffer; relayed paths reorder packets.                                          | Client string now: `udpsrc buffer-size=2097152 … ! rtpjitterbuffer latency=N ! rtph264depay …`.                                                      |
| 5   | Stutter (fast/slow)                             | Tailscale DERP RTT oscillates (150–230 ms earlier, 407–755 ms later). Jitter buffer of 50 ms cannot absorb it.                                                                                                  | Jitter latency raised to 150 ms (`CLIENT_JITTER_LATENCY_MS`).                                                                                        |

Things checked and **ruled out**:

- **Stats probes / `stats_counter`**: the inline `identity stats_counter` is off by default for UDP pipelines (`FPV_VIDEO_STATS_COUNTER` not set). Stats are polled every 250 ms; stats threads use ≈0 % CPU. No pad probes per frame.
- **LTE bufferbloat**: RTT to 1.1.1.1 through the modem with video running: avg 43 ms (min 28, mdev ~11), same as idle. CAKE egress drops: 0 in 20 s.
- **Encoder throughput**: 29–30 fps, `current_bitrate` ≈ target, `errors: 0`.
- **Capture thread**: `source:src` (V4L2) runs at ~90 % of one core, but the encoder keeps 30 fps, so no frames are lost there.
- **RTSP**: no client connected on 8554. Mission Planner is not using TCP RTSP.

## 3. Current configuration (device)

| Setting                          | Value                                                                                   | Where                                          |
| -------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Codec                            | `h264_hardware` (MPP), 1920×1080 @ 30                                                   | video config                                   |
| Bitrate                          | 2000 kbps, VBR, `bps-max` = 1.5×                                                        | `hardware_h264_encoder.py` + video config      |
| GOP                              | 15 frames (IDR every 0.5 s)                                                             | video config `gop_size`                        |
| Adaptive bitrate / resolution    | **off** (opt-in)                                                                        | preferences                                    |
| RTP payloader                    | `rtph264pay`, `config-interval=-1`, `mtu` capped to path MTU − 40 (1240 over Tailscale) | `gstreamer_service.py`                         |
| CAKE (enx)                       | static 10 Mbit, diffserv4                                                               | `network_optimizer.py` (P12: no gateway burst) |
| Video DSCP                       | EF on 5600/5601/8554 (policy routing)                                                   | `network_optimizer.py`                         |
| Client receive (Mission Planner) | jitter latency 150 ms, socket buffer 2 MB, default decoder threads                      | `get_client_pipeline_strings()`                |

Client string in use (Mission Planner, custom GStreamer source):

```
udpsrc port=5600 buffer-size=2097152 caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96" ! rtpjitterbuffer latency=150 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGRA ! appsink name=outsink sync=false
```

## 4. Latency vs smoothness trade-off

| Jitter latency | Decoder         | Result seen                                                    |
| -------------- | --------------- | -------------------------------------------------------------- |
| 100 ms         | auto threads    | Grey frames gone. Small extra latency.                         |
| 50 ms          | `max-threads=1` | Lowest latency, stutter when relay oscillates.                 |
| **150 ms**     | auto threads    | **Chosen.** Smooth, minimal perceived delay for stable flight. |

Where the delay comes from (approximate, relay-dependent):

- Relay DERP: 150–230 ms RTT earlier, 400–750 ms RTT later. This is the dominant and least controllable term.
- LTE: ~40 ms RTT, no queue build-up.
- Receiver jitter buffer: 150 ms (tunable).
- Encoder: 0.5 s GOP does not add latency; it only affects recovery from loss.

## 5. Mission Planner: two different paths

1. **Custom GStreamer source** (the one tuned here): the string above. Jitter and socket buffer apply.
2. **Native URI from MAVLink** (`udp://100.80.37.49:5600`, sent by `video_stream_info.py`): Mission Planner plays it with its own FFmpeg-based player. **None of the receiver tuning above applies to this path.** If the user switches to it, grey frames and stutter may come back.

Keep this in mind when comparing behaviour between sessions.

## 6. Measurement notes (pitfalls already hit)

- `ip -s link show <if>`: the **TX** line is line 6 of the output, not line 4 (line 4 is RX). Earlier conclusions based on the wrong line were wrong.
- `bytes_sent` / `frames_sent` in `/api/video/status` are **estimated** when the stats counter is off. Do not use them as network evidence.
- `FragCreates` in `/proc/net/snmp` only means something when traffic is flowing. Check TX on the interface first.
- `ffplay udp://@:5600` on Windows received nothing while Mission Planner showed video. Most likely the port is consumed by another process or the packets go to the MP socket. Not resolved. Prefer testing with the same GStreamer string MP uses.
- Tailscale `ping` latency varies a lot over time; a single sample says nothing about the relay.

## 7. Knobs and how to change them

| Knob             | How                                                                   | Effect                                                       |
| ---------------- | --------------------------------------------------------------------- | ------------------------------------------------------------ |
| Video bitrate    | `POST /api/video/config/video` `{"h264_bitrate": N}`                  | Lower = less load on LTE uplink, lower quality               |
| GOP              | `POST /api/video/config/video` `{"gop_size": N}`                      | Lower = faster recovery from loss, more bitrate on keyframes |
| Adaptive bitrate | `POST /api/video/config/auto-adaptive-bitrate` `{"enabled": bool}`    | Off = user-managed stream (default for new installs)         |
| Client jitter    | edit the Mission Planner GStreamer string `rtpjitterbuffer latency=N` | 50 = low latency / stutter; 150 = smooth                     |
| Socket buffer    | `CLIENT_UDP_BUFFER_BYTES` in `gstreamer_service.py`                   | Absorbs keyframe bursts                                      |
| RTP MTU          | automatic from route; `rtp_mtu_limit` margin 40 B                     | Avoids fragmentation on tunnels                              |
| WebRTC mode      | `POST /api/video/config/streaming` with `mode: webrtc` (user choice)  | Has NACK/PLI recovery; not used for MP today                 |

Restarting the video: `POST /api/video/restart`. Restarting the service: `sudo systemctl restart fpvcopilot-sky` (privileged helper allows it).

## 8. Open items / next steps

- **Direct path**: would remove the relay from the latency budget. Requires NAT traversal at both ends (hard NAT on at least one). Options: UPnP port mapping on the modem (`PortMapping: UPnP` is available) plus a reachable ground endpoint. Not attempted.
- **Native MP URI**: decide whether to advertise the GStreamer string or to keep the URI; or test MP's native player with the same jitter behaviour.
- **Ground-side loss evidence**: if grey frames return, run a receiver with debug logging (`missing reference picture`, `error while decoding`) to confirm loss vs receiver.
- **RTSP path** (`rtsp_server.py`): TCP, not affected by MTU fragmentation, but subject to head-of-line blocking on the relay. Not used today.
- **Pipeline sender queue**: `queue_post` is leaky with 2 buffers; this is intentional (drop stale frames). Do not enlarge it without measuring.

## 9. Rollback

- Client: go back to the previous string (`latency=100` without `buffer-size`, or the app's original `udpsrc … ! rtph264depay ! avdec_h264 …`).
- Bitrate / GOP: `POST /api/video/config/video` with previous values (2000 kbps / 15 frames is current; previous was 3200 kbps / auto GOP).
- Adaptive: `POST /api/video/config/auto-adaptive-bitrate` `{"enabled": true}` to restore the old behaviour.
- Code: the MTU cap and bridge gate are in 1.4.1; revert the release or the specific commits.
