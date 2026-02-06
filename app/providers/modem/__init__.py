"""
Modem Providers
Implementations for various modem types:
- HiLink modems (Huawei E3372h, etc.)
- Router gateway modems (TP-Link M7200, etc.)
- USB dongle modems (Generic)
"""

from .hilink import HuaweiE3372hProvider

__all__ = [
    'HuaweiE3372hProvider',
]
