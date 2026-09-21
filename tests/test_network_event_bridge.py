"""Unit tests for NetworkEventBridge event-detection logic (no monitoring loop)."""

import pytest

from app.services.network_event_bridge import EventBridgeConfig, NetworkEvent, NetworkEventBridge


@pytest.fixture
def bridge():
    return NetworkEventBridge(config=EventBridgeConfig())


class TestDetectJitter:
    def test_high_jitter_on_crossing(self, bridge):
        events = bridge._detect_jitter_events({"jitter": 50.0})
        assert events[0][0] == NetworkEvent.HIGH_JITTER
        assert events[0][1]["severity"] == "high"

    def test_critical_jitter(self, bridge):
        events = bridge._detect_jitter_events({"jitter": 100.0})
        assert events[0][1]["severity"] == "critical"

    def test_no_event_while_staying_high(self, bridge):
        bridge._last_jitter_ms = 50.0
        assert bridge._detect_jitter_events({"jitter": 55.0}) == []

    def test_recovery_event(self, bridge):
        bridge._last_jitter_ms = 50.0
        events = bridge._detect_jitter_events({"jitter": 10.0})
        assert events[0][0] == NetworkEvent.JITTER_RECOVERY

    def test_updates_last_value(self, bridge):
        bridge._detect_jitter_events({"jitter": 12.0})
        assert bridge._last_jitter_ms == 12.0


class TestDetectRtt:
    def test_high_rtt(self, bridge):
        events = bridge._detect_rtt_events({"avg_rtt": 300.0})
        assert events[0][0] == NetworkEvent.HIGH_RTT
        assert events[0][1]["critical"] is False

    def test_rtt_critical_flag(self, bridge):
        events = bridge._detect_rtt_events({"avg_rtt": bridge.config.rtt_critical_ms + 1})
        assert events[0][1]["critical"] is True

    def test_rtt_recovery(self, bridge):
        bridge._last_rtt_ms = 300.0
        events = bridge._detect_rtt_events({"avg_rtt": 10.0})
        assert events[0][0] == NetworkEvent.RTT_RECOVERY


class TestDetectPacketLoss:
    def test_packet_loss_high(self, bridge):
        events = bridge._detect_packet_loss_events({"packet_loss": bridge.config.packet_loss_high + 1})
        assert events[0][0] == NetworkEvent.PACKET_LOSS

    def test_packet_loss_critical_severity(self, bridge):
        events = bridge._detect_packet_loss_events({"packet_loss": bridge.config.packet_loss_critical + 1})
        assert events[0][1]["severity"] == "critical"

    def test_packet_loss_recovery(self, bridge):
        bridge._last_packet_loss = bridge.config.packet_loss_high + 1
        events = bridge._detect_packet_loss_events({"packet_loss": 0.0})
        assert events[0][0] == NetworkEvent.PACKET_LOSS_RECOVERY


class TestDetectSinr:
    def test_no_event_without_sinr(self, bridge):
        assert bridge._detect_sinr_events({}) == []

    def test_sinr_drop(self, bridge):
        for value in (25.0, 24.0, 23.0):
            bridge._detect_sinr_events({"sinr": value})
        events = bridge._detect_sinr_events({"sinr": 10.0})
        assert any(event[0] == NetworkEvent.SINR_DROP for event in events)

    def test_sinr_recovery(self, bridge):
        events = []
        for value in (5.0, 6.0, 7.0, 20.0, 21.0, 22.0):
            events = bridge._detect_sinr_events({"sinr": value})
        assert any(event[0] == NetworkEvent.SINR_RECOVERY for event in events)


class TestQualityScore:
    def test_modem_with_good_cell_and_latency(self, bridge):
        bridge._primary_type = "modem"
        bridge._update_quality_score(
            {"sinr": 25.0, "rsrq": -8.0},
            {"jitter": 2.0, "packet_loss": 0.0, "avg_rtt": 30.0},
        )
        score = bridge._quality_score
        assert score.score >= 60
        assert score.quality_label in {"Bueno", "Excelente"}
        assert score.recommended_bitrate_kbps > 0

    def test_wifi_uses_latency_only(self, bridge):
        bridge._primary_type = "wifi"
        bridge._update_quality_score(None, {"jitter": 5.0, "packet_loss": 0.0, "avg_rtt": 20.0})
        score = bridge._quality_score
        # WiFi marks SINR/RSRQ as N/A.
        assert score.sinr_component == 0
        assert score.score > 50

    def test_all_pings_failed_is_penalised(self, bridge):
        bridge._primary_type = "wifi"
        bridge._update_quality_score(None, {"jitter": 0.0, "packet_loss": 100.0, "avg_rtt": 0.0})
        # Jitter/RTT are not rewarded when nothing responded.
        assert bridge._quality_score.jitter_component == 0

    def test_wifi_without_latency_keeps_previous_score(self, bridge):
        bridge._primary_type = "wifi"
        before = bridge._quality_score.score
        bridge._update_quality_score(None, None)
        assert bridge._quality_score.score == before

    def test_hardware_encoder_inactive_without_service(self, bridge):
        assert bridge._is_hardware_encoder_active() is False


class TestStatusAndEvents:
    def test_get_status_shape(self, bridge):
        status = bridge.get_status()
        assert isinstance(status, dict)
        assert "active" in status
        assert "events_total" in status

    def test_event_history_and_clear(self, bridge):
        assert bridge.get_event_history() == []
        bridge.clear_events()
        assert bridge.get_event_history() == []
