"""
Command whitelist for the privileged helper (``fpvcopilot-privd``).

The helper runs as root and executes a small set of exact command shapes needed
by the application. This module is the single source of truth for that policy
and is pure (no side effects) so it can be unit-tested.

A command is allowed when its program basename is listed and the space-joined
arguments match one of the program's full-match regular expressions.
"""

import re
from typing import Dict, List

# program basename -> list of regex patterns matched against the joined args
_RULES: Dict[str, List[str]] = {
    "systemctl": [
        r"(restart|start|stop|status) fpvcopilot-sky(\.service)?",
        r"(restart|status|reload) nginx(\.service)?",
        r"(start|stop|status|restart|enable) dnsmasq(\.service)?",
        r"start --no-block fpvcopilot-update(\.service)?",
    ],
    "journalctl": [r"-u fpvcopilot-sky(\.service)?( .*)?"],
    "tailscale": [r"up( .*)?", r"down", r"logout", r"status( .*)?"],
    "iw": [r"dev \S+ scan( .*)?", r"dev \S+ link"],
    "nmcli": [
        r"device wifi connect .+",
        r"device wifi disconnect( \S+)?",
        r"device wifi rescan",
        r"dev wifi rescan",
        r"connection (up|down|show)( .*)?",
    ],
    "ip": [
        r"route (add|del|change|replace|show)( .*)?",
        r"link (set|show)( .*)?",
        r"addr show( .*)?",
        r"(-o|-o -4|-4) addr show( .*)?",
        r"rule( .*)?",
        r"-force -batch( -)?",
    ],
    "tc": [r"(-s )?(qdisc|class|filter)( .*)?"],
    "iptables": [r"-t mangle( .*)?"],
    "iptables-save": [r"(-t mangle)?"],
    "iptables-restore": [r"(--noflush)?"],
    "sysctl": [
        r"-w (net\.ipv4\.tcp_congestion_control|net\.core\.rmem_max|net\.core\.wmem_max|"
        r"net\.ipv4\.tcp_window_scaling|net\.ipv4\.tcp_timestamps)=[^ ]+"
    ],
    "ethtool": [r"-s \S+ wol d"],
    "wg": [r"show( all)?( .*)?"],
    "tee": [r"(-a )?(/etc/dnsmasq\.d/fpvcopilot\.conf|/etc/resolv\.conf|/etc/iproute2/rt_tables)"],
    "mkdir": [r"-p /etc/dnsmasq\.d"],
    "cp": [
        r"(-f )?/etc/resolv\.conf /etc/resolv\.conf\.backup",
        r"(-f )?/etc/resolv\.conf\.backup /etc/resolv\.conf",
    ],
    "killall": [r"-(USR1|HUP) dnsmasq"],
    "apt-get": [r"update", r"install -y dnsmasq"],
    "ping": [r".*"],
    "modprobe": [r"ifb numifbs=1"],
}

_COMPILED: Dict[str, List["re.Pattern[str]"]] = {
    program: [re.compile(pattern) for pattern in patterns] for program, patterns in _RULES.items()
}


def allowed_programs() -> List[str]:
    """Return the list of allowed program basenames."""
    return sorted(_COMPILED)


def is_allowed(argv: List[str]) -> bool:
    """Return True if *argv* matches the privileged whitelist."""
    if not argv:
        return False
    program = str(argv[0]).rsplit("/", 1)[-1]
    patterns = _COMPILED.get(program)
    if not patterns:
        return False
    args = " ".join(str(arg) for arg in argv[1:])
    return any(pattern.fullmatch(args) for pattern in patterns)
