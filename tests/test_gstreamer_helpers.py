"""Tests for the pure GStreamer helpers."""

from app.services.gstreamer_helpers import calculate_health, format_uptime


class TestFormatUptime:
    def test_none_like_returns_dash(self):
        assert format_uptime(0) == "-"
        assert format_uptime(None) == "-"

    def test_formats_hh_mm_ss(self):
        assert format_uptime(3661) == "01:01:01"
        assert format_uptime(59) == "00:00:59"
        assert format_uptime(3600) == "01:00:00"


class TestCalculateHealth:
    def test_good_when_fps_matches_and_no_errors(self):
        assert calculate_health(errors=0, current_fps=30, target_fps=30, encoder_stats={}, network_score=90) == "good"

    def test_poor_with_low_fps_and_errors(self):
        assert calculate_health(errors=10, current_fps=2, target_fps=30, encoder_stats={}, network_score=20) == "poor"

    def test_fair_mid_range(self):
        assert calculate_health(errors=0, current_fps=15, target_fps=30, encoder_stats={}, network_score=50) == "fair"

    def test_encoder_drops_and_slow_encoding_worsen_health(self):
        clean = calculate_health(errors=0, current_fps=20, target_fps=30, encoder_stats={}, network_score=0)
        stressed = calculate_health(
            errors=0,
            current_fps=20,
            target_fps=30,
            encoder_stats={"avg_encode_time_ms": 1000, "frames_dropped_pre_encoder": 15},
            network_score=0,
        )
        assert clean == "fair"
        assert stressed == "poor"

    def test_zero_target_fps_is_not_a_division_error(self):
        assert calculate_health(errors=0, current_fps=0, target_fps=0, encoder_stats={}) in {"good", "fair", "poor"}
