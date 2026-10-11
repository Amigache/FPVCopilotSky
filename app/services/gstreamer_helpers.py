"""
Pure helpers extracted from GStreamerService.

These functions have no GStreamer or hardware dependency, so they can be unit
tested in CI (the service itself is excluded from coverage).
"""

from typing import Dict, Optional

# IPv4 (20) + UDP (8) headers, plus headroom for tunnel encapsulation (Tailscale/WireGuard).
RTP_PATH_MARGIN = 40


def parse_route_device(route_output: str) -> Optional[str]:
    """Return the egress device from `ip -o route get <host>` output."""
    parts = route_output.split()
    if "dev" in parts:
        idx = parts.index("dev")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def rtp_mtu_limit(path_mtu: int, configured: int) -> int:
    """Largest RTP packet size that avoids IP fragmentation on the path."""
    return max(576, min(configured, path_mtu - RTP_PATH_MARGIN))


def format_uptime(seconds: int) -> str:
    """Format uptime in seconds to HH:MM:SS (or '-' when falsy)."""
    if not seconds:
        return "-"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def calculate_health(
    *,
    errors: int,
    current_fps: int,
    target_fps: int,
    encoder_stats: Dict,
    network_score: float = 75,
) -> str:
    """Weighted stream health from FPS, errors, encoder stats and network score.

    Returns ``'good'``, ``'fair'`` or ``'poor'``.
    """
    # --- Pipeline component (0-100) ---
    fps_pct = (current_fps / target_fps * 100) if target_fps > 0 else 100
    error_penalty = min(errors * 3, 30)  # up to -30
    pipeline_score = max(0, min(100, fps_pct - error_penalty))

    # --- Encoder component (0-100) ---
    encode_ms = encoder_stats.get("avg_encode_time_ms", 0.0)
    budget_ms = (1000 / target_fps * 0.8) if target_fps > 0 else 33
    enc_load = min(encode_ms / budget_ms, 1.0) if budget_ms > 0 else 0
    dropped = encoder_stats.get("frames_dropped_pre_encoder", 0) + encoder_stats.get("frames_dropped_post_encoder", 0)
    drop_penalty = min(dropped * 2, 20)
    encoder_score = max(0, 100 - int(enc_load * 50) - drop_penalty)

    # --- Weighted composite ---
    composite = 0.45 * pipeline_score + 0.25 * encoder_score + 0.30 * network_score
    if composite >= 70:
        return "good"
    if composite >= 40:
        return "fair"
    return "poor"
