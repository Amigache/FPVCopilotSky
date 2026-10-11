"""Receive pipelines handed to Mission Planner / QGC (UDP and multicast)."""

from unittest.mock import MagicMock

from app.services import gstreamer_service as gs


def _service():
    svc = gs.GStreamerService.__new__(gs.GStreamerService)
    svc.video_config = MagicMock(codec="h264_hardware")
    svc.streaming_config = MagicMock(
        udp_port=5600,
        multicast_group="239.1.1.1",
        multicast_port=5600,
        mode="udp",
        rtsp_url="rtsp://10.0.0.1:8554/fpv",
        rtsp_transport="tcp",
    )
    svc._get_streaming_ip = lambda: "10.0.0.1"
    return svc


class TestClientPipelineStrings:
    def test_udp_has_socket_buffer_and_jitter_buffer(self):
        p = _service().get_client_pipeline_strings()["pipelines"]["udp"]["pipeline"]
        assert f"buffer-size={gs.CLIENT_UDP_BUFFER_BYTES}" in p
        assert f"rtpjitterbuffer latency={gs.CLIENT_JITTER_LATENCY_MS}" in p
        assert p.index("rtpjitterbuffer") < p.index("rtph264depay")

    def test_multicast_has_socket_buffer_and_jitter_buffer(self):
        p = _service().get_client_pipeline_strings()["pipelines"]["multicast"]["pipeline"]
        assert "auto-multicast=true" in p
        assert f"buffer-size={gs.CLIENT_UDP_BUFFER_BYTES}" in p
        assert "rtpjitterbuffer" in p

    def test_rtsp_pipeline_unchanged(self):
        p = _service().get_client_pipeline_strings()["pipelines"]["rtsp"]["pipeline"]
        assert "rtspsrc" in p
        assert "rtpjitterbuffer" not in p
