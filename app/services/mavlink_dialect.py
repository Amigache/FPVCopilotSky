"""
MAVLink Dialect Service
Provides access to ArduPilot MAVLink enums, modes, and parameter metadata
"""

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as apm
from typing import Dict, List, Optional


class MAVLinkDialect:
    """Service for accessing MAVLink dialect information"""

    # Flight modes for different vehicle types
    PLANE_MODES = {
        0: "MANUAL",
        1: "CIRCLE",
        2: "STABILIZE",
        3: "TRAINING",
        4: "ACRO",
        5: "FBWA",  # Fly By Wire A
        6: "FBWB",  # Fly By Wire B
        7: "CRUISE",
        8: "AUTOTUNE",
        10: "AUTO",
        11: "RTL",
        12: "LOITER",
        13: "TAKEOFF",
        14: "AVOID_ADSB",
        15: "GUIDED",
        16: "INITIALISING",
        17: "QSTABILIZE",
        18: "QHOVER",
        19: "QLOITER",
        20: "QLAND",
        21: "QRTL",
        22: "QAUTOTUNE",
        23: "QACRO",
        24: "THERMAL",
        25: "LOITER2QLAND",
        26: "AUTOLAND",
    }

    COPTER_MODES = {
        0: "STABILIZE",
        1: "ACRO",
        2: "ALT_HOLD",
        3: "AUTO",
        4: "GUIDED",
        5: "LOITER",
        6: "RTL",
        7: "CIRCLE",
        9: "LAND",
        11: "DRIFT",
        13: "SPORT",
        14: "FLIP",
        15: "AUTOTUNE",
        16: "POSHOLD",
        17: "BRAKE",
        18: "THROW",
        19: "AVOID_ADSB",
        20: "GUIDED_NOGPS",
        21: "SMART_RTL",
        22: "FLOWHOLD",
        23: "FOLLOW",
        24: "ZIGZAG",
        25: "SYSTEMID",
        26: "AUTOROTATE",
        27: "AUTO_RTL",
        28: "TURTLE",
        29: "RATE_ACRO",
    }

    ROVER_MODES = {
        0: "MANUAL",
        1: "ACRO",
        3: "STEERING",
        4: "HOLD",
        5: "LOITER",
        6: "FOLLOW",
        7: "SIMPLE",
        8: "DOCK",
        9: "CIRCLE",
        10: "AUTO",
        11: "RTL",
        12: "SMART_RTL",
        15: "GUIDED",
        16: "INITIALISING",
    }

    SUB_MODES = {
        0: "STABILIZE",
        1: "ACRO",
        2: "ALT_HOLD",
        3: "AUTO",
        4: "GUIDED",
        7: "CIRCLE",
        9: "SURFACE",
        16: "POSHOLD",
        19: "MANUAL",
        20: "MOTORDETECT",
        21: "SURFTRAK",
    }

    TRACKER_MODES = {0: "MANUAL", 1: "STOP", 2: "SCAN", 3: "SERVO_TEST", 4: "GUIDED", 10: "AUTO", 16: "INITIALISING"}

    # MAV_TYPE to mode mapping
    MAV_TYPE_MODES = {
        1: PLANE_MODES,  # MAV_TYPE_FIXED_WING
        2: COPTER_MODES,  # MAV_TYPE_QUADROTOR
        10: ROVER_MODES,  # MAV_TYPE_GROUND_ROVER
        12: COPTER_MODES,  # MAV_TYPE_HEXAROTOR
        13: COPTER_MODES,  # MAV_TYPE_OCTOROTOR
        14: COPTER_MODES,  # MAV_TYPE_TRICOPTER
        19: PLANE_MODES,  # MAV_TYPE_VTOL
        20: SUB_MODES,  # MAV_TYPE_SUBMARINE
        26: TRACKER_MODES,  # MAV_TYPE_ANTENNA_TRACKER
    }

    # System status messages
    MAV_STATE = {
        0: "UNINIT",
        1: "BOOT",
        2: "CALIBRATING",
        3: "STANDBY",
        4: "ACTIVE",
        5: "CRITICAL",
        6: "EMERGENCY",
        7: "POWEROFF",
        8: "FLIGHT_TERMINATION",
    }

    # Autopilot types
    MAV_AUTOPILOT = {
        0: "GENERIC",
        1: "RESERVED",
        2: "SLUGS",
        3: "ARDUPILOTMEGA",
        4: "OPENPILOT",
        5: "GENERIC_WAYPOINTS_ONLY",
        6: "GENERIC_WAYPOINTS_AND_SIMPLE_NAVIGATION_ONLY",
        7: "GENERIC_MISSION_FULL",
        8: "INVALID",
        9: "PPZ",
        10: "UDB",
        11: "FP",
        12: "PX4",
        13: "SMACCMPILOT",
        14: "AUTOQUAD",
        15: "ARMAZILA",
        16: "AEROB",
        17: "ASLUAV",
        18: "SMARTAP",
        19: "AIRRAILS",
        20: "REFLEX",
    }

    # Vehicle types
    MAV_TYPE = {
        0: "GENERIC",
        1: "FIXED_WING",
        2: "QUADROTOR",
        3: "COAXIAL",
        4: "HELICOPTER",
        5: "ANTENNA_TRACKER",
        6: "GCS",
        7: "AIRSHIP",
        8: "FREE_BALLOON",
        9: "ROCKET",
        10: "GROUND_ROVER",
        11: "SURFACE_BOAT",
        12: "SUBMARINE",
        13: "HEXAROTOR",
        14: "OCTOROTOR",
        15: "TRICOPTER",
        16: "FLAPPING_WING",
        17: "KITE",
        18: "ONBOARD_CONTROLLER",
        19: "VTOL_DUOROTOR",
        20: "VTOL_QUADROTOR",
        21: "VTOL_TILTROTOR",
        22: "VTOL_RESERVED2",
        23: "VTOL_RESERVED3",
        24: "VTOL_RESERVED4",
        25: "VTOL_RESERVED5",
        26: "GIMBAL",
        27: "ADSB",
        28: "PARAFOIL",
        29: "DODECAROTOR",
        30: "CAMERA",
        31: "CHARGING_STATION",
        32: "FLARM",
        33: "SERVO",
        34: "ODID",
        35: "DECAROTOR",
        36: "BATTERY",
        37: "PARACHUTE",
        38: "LOG",
        39: "OSD",
        40: "IMU",
        41: "GPS",
        42: "WINCH",
    }

    @staticmethod
    def get_mode_string(mav_type: int, custom_mode: int) -> str:
        """
        Get human-readable flight mode string

        Args:
            mav_type: MAV_TYPE from heartbeat
            custom_mode: Custom mode from heartbeat

        Returns:
            Mode name as string
        """
        modes = MAVLinkDialect.MAV_TYPE_MODES.get(mav_type, {})
        return modes.get(custom_mode, f"UNKNOWN({custom_mode})")

    @staticmethod
    def get_state_string(system_status: int) -> str:
        """Get human-readable system status string"""
        return MAVLinkDialect.MAV_STATE.get(system_status, f"UNKNOWN({system_status})")

    @staticmethod
    def get_autopilot_string(autopilot: int) -> str:
        """Get human-readable autopilot type string"""
        return MAVLinkDialect.MAV_AUTOPILOT.get(autopilot, f"UNKNOWN({autopilot})")

    @staticmethod
    def get_type_string(mav_type: int) -> str:
        """Get human-readable vehicle type string"""
        return MAVLinkDialect.MAV_TYPE.get(mav_type, f"UNKNOWN({mav_type})")

    @staticmethod
    def get_all_modes_for_type(mav_type: int) -> Dict[int, str]:
        """
        Get all available modes for a vehicle type

        Args:
            mav_type: MAV_TYPE from heartbeat

        Returns:
            Dictionary of {mode_number: mode_name}
        """
        return MAVLinkDialect.MAV_TYPE_MODES.get(mav_type, {})

    @staticmethod
    def get_enum_value(enum_name: str, value_name: str) -> Optional[int]:
        """
        Get numeric value for an enum entry

        Args:
            enum_name: Name of the enum (e.g., 'MAV_CMD')
            value_name: Name of the value (e.g., 'MAV_CMD_NAV_WAYPOINT')

        Returns:
            Numeric value or None if not found
        """
        try:
            # Access enum from ardupilotmega module
            enum_dict = getattr(apm, enum_name, None)
            if enum_dict and isinstance(enum_dict, dict):
                return enum_dict.get(value_name)
            return None
        except:
            return None

    @staticmethod
    def get_enum_name(enum_name: str, value: int) -> Optional[str]:
        """
        Get name for an enum value (reverse lookup)

        Args:
            enum_name: Name of the enum
            value: Numeric value

        Returns:
            Enum entry name or None if not found
        """
        try:
            enum_dict = getattr(apm, enum_name, None)
            if enum_dict and isinstance(enum_dict, dict):
                # Reverse lookup
                for k, v in enum_dict.items():
                    if v == value:
                        return k
            return None
        except:
            return None
