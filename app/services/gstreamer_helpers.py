"""
Pure helpers extracted from GStreamerService.

These functions have no GStreamer or hardware dependency, so they can be unit
tested in CI (the service itself is excluded from coverage).
"""

from typing import Dict


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
