"""Tests for CAKE calibration/DSCP consistency and per-interface IFB naming."""

from unittest.mock import MagicMock

from app.services.network_optimizer import NetworkOptimizer


def commands(call_args_list):
    return [call.args[0] for call in call_args_list]


def test_ifb_name_is_per_interface_and_short():
    opt = NetworkOptimizer()
    assert opt._ifb_for_interface("wlan0") == "ifbwlan0"
    assert opt._ifb_for_interface("eth1") == "ifbeth1"
    assert opt._ifb_for_interface("wwan0.1") == "ifbwwan0_1"
    assert len(opt._ifb_for_interface("a-very-long-interface-name")) <= 15


def test_cake_egress_honors_dscp_and_is_not_washed():
    opt = NetworkOptimizer()
    opt._run_command = MagicMock(return_value=("", "", 0))

    assert opt._configure_cake("eth1") is True

    cmds = commands(opt._run_command.call_args_list)
    egress = next(c for c in cmds if "cake" in c and "root" in c and "eth1" in c)
    assert "diffserv4" in egress
    assert "wash" not in egress  # must not erase the EF(46) mark
    assert "overhead" in egress


def test_cake_uses_per_interface_ifb_not_shared():
    opt = NetworkOptimizer()
    opt._run_command = MagicMock(return_value=("", "", 0))

    opt._configure_cake("wwan0")
    cmds = commands(opt._run_command.call_args_list)

    assert any("ifbwwan0" in c for c in cmds)
    assert not any("ifb0" in c for c in cmds)
    # The per-interface IFB must be created (it is not ifb0..N from modprobe).
    assert ["sudo", "ip", "link", "add", "ifbwwan0", "type", "ifb"] in cmds


def test_cake_disable_uses_per_interface_ifb():
    opt = NetworkOptimizer()
    opt._run_command = MagicMock(return_value=("", "", 0))

    opt._configure_cake("wwan0", enable=False)
    cmds = commands(opt._run_command.call_args_list)

    assert any("ifbwwan0" in c for c in cmds)
    assert not any("ifb0" in c for c in cmds)


def test_cake_besteffort_washes_when_diffserv_disabled():
    opt = NetworkOptimizer()
    opt.config.cake_diffserv = False
    opt._run_command = MagicMock(return_value=("", "", 0))

    opt._configure_cake("eth1")
    cmds = commands(opt._run_command.call_args_list)
    egress = next(c for c in cmds if "cake" in c and "root" in c and "eth1" in c)

    assert "besteffort" in egress
    assert "wash" in egress


def test_get_vpn_interface_detects_tailscale():
    opt = NetworkOptimizer()
    opt._run_command = MagicMock(
        return_value=("3: tailscale0: <POINTOPOINT,UP> mtu 1280\n4: eth1: <BROADCAST> mtu 1420", "", 0)
    )
    assert opt._get_vpn_interface() == "tailscale0"


def test_set_vpn_mtu_applies_to_vpn_interface():
    opt = NetworkOptimizer()
    opt._run_command = MagicMock(return_value=("5: tailscale0: <POINTOPOINT,UP> mtu 1500", "", 0))

    assert opt._set_vpn_mtu(1280) is True

    applied = [call.args[0] for call in opt._run_command.call_args_list]
    assert ["sudo", "ip", "link", "set", "tailscale0", "mtu", "1280"] in applied


def test_set_vpn_mtu_without_vpn_returns_false():
    opt = NetworkOptimizer()
    opt._run_command = MagicMock(return_value=("1: lo: <LOOPBACK> mtu 65536\n2: eth0: <BROADCAST> mtu 1500", "", 0))
    assert opt._set_vpn_mtu(1280) is False
