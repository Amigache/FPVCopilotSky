"""
Huawei HiLink Modem Constants
Centralized configuration for Huawei E3372h provider
"""

# Network Configuration
HILINK_MODEM_URL = "http://192.168.8.1/"
HILINK_CONNECTION_TIMEOUT = 5  # seconds
HILINK_WRITE_TIMEOUT = 15  # seconds

# Latency Testing Configuration
LATENCY_TEST_HOST = "8.8.8.8"
LATENCY_TEST_COUNT = 3

# Network Mode Mappings
NETWORK_MODE_NAMES = {
    "00": "Auto (4G/3G/2G)",
    "01": "2G Only",
    "02": "3G Only",
    "03": "4G Only",
}

# Connection Status Mappings
CONNECTION_STATUS_CODES = {
    "900": "Connecting",
    "901": "Connected",
    "902": "Disconnected",
    "903": "Disconnecting",
}

# Radio Access Technology Mappings
RAT_TYPE_NAMES = {"0": "GSM", "2": "WCDMA", "7": "LTE", "12": "5G NR"}

# Band Presets for Huawei E3372h
BAND_PRESETS = {
    "global": {
        "name": "Global 4G",
        "description": "Todas las bandas LTE globales",
        "mask": 0x7FFFFFFFFFFFFFFF,  # All bands
    },
    "europe": {
        "name": "Europa",
        "description": "Bandas 3, 7, 8, 20 (principales Europa)",
        "mask": 0x84,  # B3, B7, B8, B20
    },
    "america": {
        "name": "América",
        "description": "Bandas 2, 4, 12, 17 (principales América)",
        "mask": 0x1002A,  # B2, B4, B12, B17
    },
    "asia": {
        "name": "Asia-Pacífico",
        "description": "Bandas 1, 3, 8, 40, 41 (principales Asia)",
        "mask": 0x10000000085,  # B1, B3, B8, B40, B41
    },
}


# API Endpoints - relative to HILINK_MODEM_URL
class HilinkEndpoints:
    DEVICE_INFO = "api/device/information"
    MONITORING_STATUS = "api/monitoring/status"
    NET_MODE = "api/net/net-mode"
    MONITORING_CHECK_NOTIFICATIONS = "api/monitoring/check-notifications"
    MONITORING_TRAFFIC_STATISTICS = "api/monitoring/traffic-statistics"
    GLOBAL_CONFIG = "api/global/config"
    SIGNAL = "api/device/signal"
    NET_CURRENT_PLMN = "api/net/current-plmn"
    NET_REG_STATUS = "api/net/registration"
    DIALUP_CONNECTION = "api/dialup/connection"
    GLOBAL_REBOOT = "api/global/reboot"
