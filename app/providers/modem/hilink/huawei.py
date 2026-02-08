"""
Huawei E3372h ModemProvider
Implementation for Huawei E3372h-153 HiLink modem
Optimized for FPV video streaming over 4G LTE
"""

import asyncio
import time
import subprocess
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Any, List, Tuple
from functools import partial
from dataclasses import dataclass, field
from datetime import datetime
import logging

from ...base import ModemProvider, ModemStatus, ModemInfo, NetworkInfo

logger = logging.getLogger(__name__)

# Try to import huawei-lte-api
HILINK_AVAILABLE = False
Client = None
Connection = None

try:
    from huawei_lte_api.Client import Client
    from huawei_lte_api.Connection import Connection
    from huawei_lte_api.exceptions import (
        ResponseErrorException,
        ResponseErrorLoginRequiredException,
    )

    HILINK_AVAILABLE = True
    logger.info("huawei-lte-api loaded successfully")
except ImportError as e:
    logger.warning(f"huawei-lte-api not installed: {e}")
except Exception as e:
    logger.error(f"Error loading huawei-lte-api: {e}")


# ======================
# LTE Band Configuration
# ======================
# E3372h-153 supported bands: B1, B3, B7, B8, B20
LTE_BANDS = {
    "B1": 0x1,  # 2100MHz - FDD
    "B3": 0x4,  # 1800MHz - FDD (Orange primary urban)
    "B7": 0x40,  # 2600MHz - FDD (High speed, short range)
    "B8": 0x80,  # 900MHz  - FDD
    "B20": 0x80000,  # 800MHz  - FDD (Best rural coverage)
}

# Preset band combinations for Spain/Orange
LTE_BAND_PRESETS = {
    "all": {
        "name": "Todas las bandas",
        "description": "Auto-selección (B1+B3+B7+B8+B20)",
        "mask": LTE_BANDS["B1"]
        | LTE_BANDS["B3"]
        | LTE_BANDS["B7"]
        | LTE_BANDS["B8"]
        | LTE_BANDS["B20"],
    },
    "orange_spain": {
        "name": "Orange España Óptimo",
        "description": "B3+B7+B20 (bandas principales Orange)",
        "mask": LTE_BANDS["B3"] | LTE_BANDS["B7"] | LTE_BANDS["B20"],
    },
    "urban": {
        "name": "Urbano/Ciudad",
        "description": "B3+B7 (alta velocidad, baja latencia)",
        "mask": LTE_BANDS["B3"] | LTE_BANDS["B7"],
    },
    "rural": {
        "name": "Rural/Campo",
        "description": "B20 (800MHz, máxima cobertura)",
        "mask": LTE_BANDS["B20"],
    },
    "balanced": {
        "name": "Balanceado",
        "description": "B3+B20 (velocidad + cobertura)",
        "mask": LTE_BANDS["B3"] | LTE_BANDS["B20"],
    },
    "b3_only": {
        "name": "Solo B3 (1800MHz)",
        "description": "Forzar banda 3",
        "mask": LTE_BANDS["B3"],
    },
    "b7_only": {
        "name": "Solo B7 (2600MHz)",
        "description": "Forzar banda 7 (alta velocidad)",
        "mask": LTE_BANDS["B7"],
    },
    "b20_only": {
        "name": "Solo B20 (800MHz)",
        "description": "Forzar banda 20 (mejor cobertura)",
        "mask": LTE_BANDS["B20"],
    },
}

# APN Configuration
APN_PRESETS = {
    "orange": {
        "name": "Orange",
        "apn": "orange",
        "description": "APN estándar Orange España",
    },
    "orangeworld": {
        "name": "Orange World",
        "apn": "orangeworld",
        "description": "APN datos Orange",
    },
    "simyo": {
        "name": "Simyo",
        "apn": "orangeworld",
        "description": "Simyo (usa red Orange)",
    },
    "internet": {
        "name": "Genérico",
        "apn": "internet",
        "description": "APN genérico",
    },
}

# Video Quality Thresholds (based on SINR)
VIDEO_QUALITY_THRESHOLDS = {
    "excellent": {
        "sinr_min": 15,
        "max_bitrate_kbps": 8000,
        "label": "Excelente",
        "color": "green",
    },
    "good": {
        "sinr_min": 10,
        "max_bitrate_kbps": 5000,
        "label": "Bueno",
        "color": "green",
    },
    "moderate": {
        "sinr_min": 5,
        "max_bitrate_kbps": 3000,
        "label": "Moderado",
        "color": "yellow",
    },
    "poor": {
        "sinr_min": 0,
        "max_bitrate_kbps": 1500,
        "label": "Bajo",
        "color": "orange",
    },
    "critical": {
        "sinr_min": -5,
        "max_bitrate_kbps": 800,
        "label": "Crítico",
        "color": "red",
    },
}

RSRP_THRESHOLDS = {
    "excellent": -80,  # > -80 dBm
    "good": -90,  # -80 to -90 dBm
    "moderate": -100,  # -90 to -100 dBm
    "poor": -110,  # -100 to -110 dBm
    "critical": -120,  # < -110 dBm
}


@dataclass
class FlightSessionStats:
    """Statistics for a flight session"""

    start_time: datetime = field(default_factory=datetime.now)
    samples: List[Dict] = field(default_factory=list)
    min_sinr: float = 99.0
    max_sinr: float = -99.0
    min_rsrp: float = 0.0
    max_rsrp: float = -999.0
    avg_latency_ms: float = 0.0
    latency_samples: List[float] = field(default_factory=list)
    disconnections: int = 0
    band_changes: int = 0
    last_band: str = ""

    def to_dict(self) -> Dict:
        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            "start_time": self.start_time.isoformat(),
            "duration_seconds": int(duration),
            "sample_count": len(self.samples),
            "min_sinr": self.min_sinr if self.min_sinr != 99.0 else None,
            "max_sinr": self.max_sinr if self.max_sinr != -99.0 else None,
            "min_rsrp": self.min_rsrp if self.min_rsrp != 0.0 else None,
            "max_rsrp": self.max_rsrp if self.max_rsrp != -999.0 else None,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "latency_samples": len(self.latency_samples),
            "disconnections": self.disconnections,
            "band_changes": self.band_changes,
        }


class HuaweiE3372hProvider(ModemProvider):
    """Huawei E3372h-153 HiLink modem provider"""

    MODEM_URL = "http://192.168.8.1/"
    CONNECTION_TIMEOUT = 5
    WRITE_TIMEOUT = 15
    LATENCY_TEST_HOST = "8.8.8.8"
    LATENCY_TEST_COUNT = 3

    def __init__(self):
        super().__init__()
        self.name = "huawei_e3372h"
        self.display_name = "Huawei E3372h"
        self._connection: Optional[Connection] = None
        self._client: Optional[Client] = None
        self._last_error: Optional[str] = None

        # Flight session tracking
        self._flight_session: Optional[FlightSessionStats] = None
        self._flight_logger = None  # FlightDataLogger instance
        self._video_mode_active: bool = False
        self._original_settings: Dict = {}

        # Latency monitoring
        self._last_latency_ms: Optional[float] = None
        self._last_jitter_ms: Optional[float] = None

        # Thread pool for async operations
        self._executor = None

        self.is_available = self.detect()

    def detect(self) -> bool:
        """Auto-detect if Huawei E3372h is available"""
        if not HILINK_AVAILABLE:
            return False

        try:
            conn = Connection(self.MODEM_URL, timeout=self.CONNECTION_TIMEOUT)
            client = Client(conn)
            info = client.device.information()
            conn.close()

            # Check if it's the E3372h model
            model = info.get("DeviceName", "").lower()
            return "e3372" in model or "hilink" in model
        except:
            return False

    def set_flight_logger(self, flight_logger):
        """Set flight data logger for CSV recording"""
        self._flight_logger = flight_logger
        logger.info(f"Flight logger configured for {self.display_name}")

    # =====================
    # Async Methods
    # =====================

    async def _run_in_executor(self, func, timeout: float = 1.0):
        """
        Run a sync function in a thread pool executor with timeout.

        Args:
            func: Synchronous function/callable to run
            timeout: Max seconds to wait (default 1.0 for quick failure)

        Returns:
            Result of the function or None on error
        """
        try:
            loop = asyncio.get_event_loop()
            # Use ThreadPoolExecutor for I/O operations (default executor is used)
            result = await asyncio.wait_for(
                loop.run_in_executor(None, func), timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            self._last_error = f"Operation timeout after {timeout}s"
            return None
        except Exception as e:
            self._last_error = str(e)
            return None

    async def async_get_status(self) -> Dict:
        """Async version of get_status() - get full modem status asynchronously"""
        if not HILINK_AVAILABLE:
            return {
                "available": False,
                "status": ModemStatus.UNAVAILABLE,
                "modem_info": None,
                "network_info": None,
                "error": "huawei-lte-api not installed",
            }

        try:
            # Get modem info and network info in parallel
            modem_info, network_info = await asyncio.gather(
                self.async_get_device_info(),
                self.async_get_network_info(),
                return_exceptions=True,
            )

            # Handle exceptions
            if isinstance(modem_info, Exception):
                modem_info = None
            if isinstance(network_info, Exception):
                network_info = None

            if not modem_info:
                return {
                    "available": False,
                    "status": ModemStatus.ERROR,
                    "modem_info": None,
                    "network_info": None,
                    "error": self._last_error or "Could not connect to modem",
                }

            status = (
                ModemStatus.CONNECTED
                if network_info and network_info.status == ModemStatus.CONNECTED
                else ModemStatus.DISCONNECTED
            )

            return {
                "available": True,
                "status": status,
                "modem_info": modem_info,
                "network_info": network_info,
                "error": None,
            }
        except Exception as e:
            return {
                "available": False,
                "status": ModemStatus.ERROR,
                "modem_info": None,
                "network_info": None,
                "error": str(e),
            }

    async def async_get_device_info(self) -> Optional[ModemInfo]:
        """Async version of get_modem_info()"""
        return await self._run_in_executor(self.get_modem_info, timeout=1.0)

    async def async_get_signal_info(self) -> Optional[Dict]:
        """Async version of get_signal_info()"""
        return await self._run_in_executor(self._get_signal_info_sync, timeout=1.0)

    async def async_get_network_info(self) -> Optional[NetworkInfo]:
        """Async version of get_network_info()"""
        return await self._run_in_executor(self.get_network_info, timeout=1.0)

    async def async_get_traffic_stats(self) -> Optional[Dict]:
        """Async version of get_traffic_stats()"""
        return await self._run_in_executor(self._get_traffic_stats_sync, timeout=1.0)

    async def async_get_raw_device_info(self) -> Optional[Dict]:
        """Async version of _get_device_info_sync() - returns raw dict with all fields"""
        return await self._run_in_executor(self._get_device_info_sync, timeout=1.0)

    async def async_get_raw_network_info(self) -> Optional[Dict]:
        """Async version of _get_network_info_sync() - returns raw dict with all fields"""
        return await self._run_in_executor(self._get_network_info_sync, timeout=1.0)

    # =====================
    # Sync Methods
    # =====================

    def _ensure_connected(self) -> bool:
        """Ensure we have a connection to the modem"""
        if not HILINK_AVAILABLE:
            self._last_error = "huawei-lte-api not installed"
            return False

        try:
            if self._connection is None:
                # Clear any previous error before retrying
                self._last_error = None
                # Use very short timeout (500ms) to fail fast if modem not available
                self._connection = Connection(self.MODEM_URL, timeout=0.5)
                self._client = Client(self._connection)
            return True
        except Exception as e:
            self._last_error = str(e)
            self._connection = None
            self._client = None
            return False

    def _disconnect(self):
        """Close connection"""
        try:
            if self._connection:
                self._connection.close()
        except:
            pass
        self._connection = None
        self._client = None

    def _get_session_token(self) -> Tuple[Optional[requests.Session], Optional[str]]:
        """Get a session with valid token for API calls"""
        try:
            session = requests.Session()
            session.get(self.MODEM_URL, timeout=self.CONNECTION_TIMEOUT)

            r = session.get(
                f"{self.MODEM_URL}api/webserver/SesTokInfo",
                timeout=self.CONNECTION_TIMEOUT,
            )
            root = ET.fromstring(r.text)
            sesinfo = root.find("SesInfo").text
            token = root.find("TokInfo").text

            session.cookies.set("SessionID", sesinfo.replace("SessionID=", ""))
            return session, token
        except Exception as e:
            logger.error(f"Failed to get session token: {e}")
            return None, None

    def _direct_api_post(
        self, endpoint: str, xml_data: str, timeout: int = None
    ) -> Tuple[bool, str]:
        """Make a direct POST request to the modem API"""
        if timeout is None:
            timeout = self.WRITE_TIMEOUT

        try:
            session, token = self._get_session_token()
            if not session or not token:
                return False, "Could not get session token"

            headers = {
                "__RequestVerificationToken": token,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }

            r = session.post(
                f"{self.MODEM_URL}{endpoint}",
                data=xml_data,
                headers=headers,
                timeout=timeout,
            )

            if "<response>OK</response>" in r.text:
                return True, "OK"
            elif "<error>" in r.text:
                root = ET.fromstring(r.text)
                code = root.find("code").text
                return False, f"Error {code}"
            else:
                return True, r.text

        except Exception as e:
            logger.error(f"Direct API POST failed: {e}")
            return False, str(e)

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous function in executor"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # ======================
    # ModemProvider Interface Implementation
    # ======================

    def get_status(self) -> Dict:
        """Get modem status (sync version for provider interface)"""
        if not HILINK_AVAILABLE:
            return {
                "available": False,
                "status": ModemStatus.UNAVAILABLE,
                "modem_info": None,
                "network_info": None,
                "error": "huawei-lte-api not installed",
            }

        try:
            modem_info = self.get_modem_info()
            network_info = self.get_network_info()

            if not modem_info:
                return {
                    "available": False,
                    "status": ModemStatus.ERROR,
                    "modem_info": None,
                    "network_info": None,
                    "error": self._last_error or "Could not connect to modem",
                }

            status = (
                ModemStatus.CONNECTED
                if network_info and network_info.status == ModemStatus.CONNECTED
                else ModemStatus.DISCONNECTED
            )

            return {
                "available": True,
                "status": status,
                "modem_info": modem_info,
                "network_info": network_info,
                "error": None,
            }
        except Exception as e:
            return {
                "available": False,
                "status": ModemStatus.ERROR,
                "modem_info": None,
                "network_info": None,
                "error": str(e),
            }

    def connect(self) -> Dict:
        """Activate modem connection"""
        # HiLink modems are auto-connect, this would trigger reconnection
        try:
            success = self._reconnect_network_sync()
            return {
                "success": success,
                "message": "Conexión iniciada" if success else self._last_error,
                "network_info": self.get_network_info() if success else None,
            }
        except Exception as e:
            return {"success": False, "message": str(e), "network_info": None}

    def disconnect(self) -> Dict:
        """Deactivate modem connection"""
        # HiLink modems typically stay connected, this would require airplane mode
        return {
            "success": False,
            "message": "Desconexión manual no soportada en HiLink mode",
        }

    def get_modem_info(self) -> Optional[ModemInfo]:
        """Get modem hardware information"""
        device = self._get_device_info_sync()
        if not device:
            return None

        return ModemInfo(
            name=device.get("device_name", "Huawei E3372h"),
            model=device.get("device_name", "E3372h-153"),
            imei=device.get("imei", ""),
            imsi=device.get("imsi", ""),
            manufacturer="Huawei",
        )

    def get_network_info(self) -> Optional[NetworkInfo]:
        """Get network connection information"""
        signal = self._get_signal_info_sync()
        network = self._get_network_info_sync()
        traffic = self._get_traffic_stats_sync()

        if not signal or not network:
            return None

        # Determine status
        conn_code = network.get("connection_status_code", "")
        status = (
            ModemStatus.CONNECTED if conn_code == "901" else ModemStatus.DISCONNECTED
        )

        # Signal strength
        signal_percent = signal.get("signal_percent", 0)

        return NetworkInfo(
            status=status,
            signal_strength=signal_percent,
            network_type=network.get(
                "network_type_ex", network.get("network_type", "")
            ),
            operator=network.get("operator", ""),
            ip_address=network.get("primary_dns", None),  # Approximation
            dns_servers=[
                network.get("primary_dns", ""),
                network.get("secondary_dns", ""),
            ],
            data_uploaded=traffic.get("current_upload_raw", 0),
            data_downloaded=traffic.get("current_download_raw", 0),
        )

    def configure_band(self, band_mask: int) -> Dict:
        """Configure LTE band preference"""
        try:
            success = self._set_lte_band_sync(band_mask)
            return {
                "success": success,
                "message": (
                    f"Banda configurada: {hex(band_mask)}"
                    if success
                    else self._last_error
                ),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ======================
    # Public methods expected by route endpoints
    # ======================

    def set_lte_band(self, preset: str = None, custom_mask: int = None) -> Dict:
        """Set LTE band from preset name or custom mask"""
        try:
            if preset:
                if preset not in LTE_BAND_PRESETS:
                    return {
                        "success": False,
                        "message": f"Preset desconocido: {preset}",
                    }
                band_mask = LTE_BAND_PRESETS[preset]["mask"]
                preset_name = LTE_BAND_PRESETS[preset]["name"]
            elif custom_mask is not None:
                band_mask = custom_mask
                preset_name = f"Custom ({hex(custom_mask)})"
            else:
                return {"success": False, "message": "Provide preset or custom_mask"}

            success = self._set_lte_band_sync(band_mask)
            if success:
                return {
                    "success": True,
                    "message": f"Banda configurada: {preset_name}",
                    "preset_name": preset_name,
                    "band_mask": hex(band_mask),
                }
            return {
                "success": False,
                "message": self._last_error or "Error configurando banda",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_current_band(self) -> Optional[Dict]:
        """Get current LTE band configuration"""
        try:
            if not self._ensure_connected():
                return None

            net_mode = self._client.net.net_mode()
            lte_band_hex = net_mode.get("LTEBand", "")
            network_mode = net_mode.get("NetworkMode", "")
            network_band = net_mode.get("NetworkBand", "")

            # Convert hex to int for band detection
            lte_band_int = int(lte_band_hex, 16) if lte_band_hex else 0

            # Detect which bands are enabled
            enabled_bands = []
            for band_name, band_mask in LTE_BANDS.items():
                if lte_band_int & band_mask:
                    enabled_bands.append(band_name)

            # Detect matching preset
            matching_preset = None
            for preset_key, preset_data in LTE_BAND_PRESETS.items():
                if preset_data["mask"] == lte_band_int:
                    matching_preset = preset_key
                    break

            # Current active band from signal info
            signal = self._get_signal_info_sync()
            current_band = signal.get("band", "") if signal else ""

            mode_names = {
                "00": "Auto",
                "01": "2G Only",
                "02": "3G Only",
                "03": "4G Only",
            }

            return {
                "lte_band_hex": lte_band_hex,
                "lte_band_int": lte_band_int,
                "enabled_bands": enabled_bands,
                "matching_preset": matching_preset,
                "active_band": current_band,
                "network_mode": network_mode,
                "network_mode_name": mode_names.get(network_mode, network_mode),
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return None

    def get_network_mode(self) -> Optional[Dict]:
        """Get current network mode (Auto/2G/3G/4G)"""
        try:
            if not self._ensure_connected():
                return None

            net_mode = self._client.net.net_mode()
            network_mode = net_mode.get("NetworkMode", "00")

            mode_names = {
                "00": "Auto (4G/3G/2G)",
                "01": "2G Only",
                "02": "3G Only",
                "03": "4G Only",
            }

            return {
                "network_mode": network_mode,
                "network_mode_name": mode_names.get(
                    network_mode, f"Unknown ({network_mode})"
                ),
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return None

    def set_network_mode(self, mode: str) -> bool:
        """Set network mode (00=Auto, 01=2G, 02=3G, 03=4G)"""
        try:
            # Read current band config to preserve it
            if self._ensure_connected():
                current = self._client.net.net_mode()
                network_band = current.get("NetworkBand", "3FFFFFFF")
                lte_band = current.get("LTEBand", "7FFFFFFFFFFFFFFF")
            else:
                network_band = "3FFFFFFF"
                lte_band = "7FFFFFFFFFFFFFFF"

            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
<NetworkMode>{mode}</NetworkMode>
<NetworkBand>{network_band}</NetworkBand>
<LTEBand>{lte_band}</LTEBand>
</request>"""

            success, msg = self._direct_api_post("api/net/net-mode", xml_data)
            if success:
                logger.info(f"Network mode set to: {mode}")
                return True
            else:
                self._last_error = msg
                return False
        except Exception as e:
            self._last_error = str(e)
            return False

    def reconnect_network(self) -> Dict:
        """Force network reconnection (public wrapper)"""
        try:
            success = self._reconnect_network_sync()
            return {
                "success": success,
                "message": (
                    "Re-registro de red iniciado"
                    if success
                    else (self._last_error or "Error en reconexión")
                ),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_apn_settings(self) -> Dict:
        """Get current APN settings and available presets"""
        try:
            current_apn = ""
            if self._ensure_connected():
                try:
                    dialup = self._client.dialup.profiles()
                    # profiles may return a list or dict
                    if isinstance(dialup, dict):
                        current_apn = dialup.get("ApnName", "") or dialup.get("APN", "")
                    elif isinstance(dialup, list) and dialup:
                        current_apn = dialup[0].get("ApnName", "") or dialup[0].get(
                            "APN", ""
                        )
                except Exception as e:
                    logger.debug(f"Could not read APN: {e}")

            return {
                "current_apn": current_apn,
                "presets": APN_PRESETS,
            }
        except Exception as e:
            return {"current_apn": "", "presets": APN_PRESETS, "error": str(e)}

    def set_apn(self, preset: str = None, custom_apn: str = None) -> Dict:
        """Configure APN settings"""
        try:
            if preset:
                if preset not in APN_PRESETS:
                    return {
                        "success": False,
                        "message": f"Preset APN desconocido: {preset}",
                    }
                apn = APN_PRESETS[preset]["apn"]
                apn_name = APN_PRESETS[preset]["name"]
            elif custom_apn:
                apn = custom_apn
                apn_name = custom_apn
            else:
                return {"success": False, "message": "Provide preset or custom_apn"}

            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
<Delete>0</Delete>
<SetDefault>0</SetDefault>
<Modify>1</Modify>
<ProfileName>{apn_name}</ProfileName>
<ApnIsStatic>1</ApnIsStatic>
<ApnName>{apn}</ApnName>
<DailupNum>*99#</DailupNum>
<Username></Username>
<Password></Password>
<AuthMode>0</AuthMode>
<IpIsStatic>0</IpIsStatic>
<IpAddress></IpAddress>
</request>"""

            success, msg = self._direct_api_post("api/dialup/profiles", xml_data)
            if success:
                return {
                    "success": True,
                    "message": f"APN configurado: {apn_name}",
                    "apn": apn,
                }
            return {"success": False, "message": msg or "Error configurando APN"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def set_roaming(self, enabled: bool) -> Dict:
        """Enable or disable data roaming"""
        try:
            roaming_val = "1" if enabled else "0"
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
<RoamAutoConnectEnable>{roaming_val}</RoamAutoConnectEnable>
</request>"""

            success, msg = self._direct_api_post("api/dialup/connection", xml_data)
            if success:
                state = "activado" if enabled else "desactivado"
                return {"success": True, "message": f"Roaming {state}"}
            return {"success": False, "message": msg or "Error configurando roaming"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ======================
    # Video Mode
    # ======================

    @property
    def video_mode_active(self) -> bool:
        """Whether video-optimized mode is active"""
        return self._video_mode_active

    def enable_video_mode(self) -> Dict:
        """Enable video-optimized modem settings (force 4G, optimize bands)"""
        try:
            if self._video_mode_active:
                return {
                    "success": True,
                    "message": "Modo video ya activo",
                    "video_mode_active": True,
                }

            # Save current settings
            current_mode = self.get_network_mode()
            current_band = self.get_current_band()
            self._original_settings = {
                "network_mode": (
                    current_mode.get("network_mode", "00") if current_mode else "00"
                ),
                "lte_band_hex": (
                    current_band.get("lte_band_hex", "") if current_band else ""
                ),
            }

            # Force 4G Only mode
            self.set_network_mode("03")

            # Set urban bands (B3+B7) for lowest latency
            self._set_lte_band_sync(LTE_BAND_PRESETS["urban"]["mask"])

            self._video_mode_active = True
            logger.info("Video mode enabled: 4G Only + B3+B7")

            return {
                "success": True,
                "message": "Modo video activado: 4G Only + B3+B7 (baja latencia)",
                "video_mode_active": True,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def disable_video_mode(self) -> Dict:
        """Disable video mode and restore original settings"""
        try:
            if not self._video_mode_active:
                return {
                    "success": True,
                    "message": "Modo video no estaba activo",
                    "video_mode_active": False,
                }

            # Restore original settings
            original_mode = self._original_settings.get("network_mode", "00")
            self.set_network_mode(original_mode)

            # Restore bands (all bands)
            self._set_lte_band_sync(LTE_BAND_PRESETS["all"]["mask"])

            self._video_mode_active = False
            self._original_settings = {}
            logger.info("Video mode disabled: settings restored")

            return {
                "success": True,
                "message": "Modo video desactivado: configuración restaurada",
                "video_mode_active": False,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ======================
    # Video Quality Assessment
    # ======================

    def get_video_quality_assessment(self) -> Dict:
        """
        Assess video streaming quality based on current signal metrics.
        Uses SINR and RSRP to determine max recommended bitrate.
        """
        try:
            signal = self._get_signal_info_sync()
            if not signal:
                return {"available": False, "error": "No signal data"}

            # Parse SINR
            sinr_str = signal.get("sinr", "")
            sinr = None
            if sinr_str:
                try:
                    sinr = float(sinr_str.replace("dB", "").strip())
                except (ValueError, AttributeError):
                    pass

            # Parse RSRP
            rsrp_str = signal.get("rsrp", "")
            rsrp = None
            if rsrp_str:
                try:
                    rsrp = float(rsrp_str.replace("dBm", "").strip())
                except (ValueError, AttributeError):
                    pass

            if sinr is None:
                return {"available": False, "error": "Could not parse SINR"}

            # Determine quality level from SINR
            quality = "critical"
            for level in ["excellent", "good", "moderate", "poor", "critical"]:
                threshold = VIDEO_QUALITY_THRESHOLDS[level]
                if sinr >= threshold["sinr_min"]:
                    quality = level
                    break

            threshold = VIDEO_QUALITY_THRESHOLDS[quality]

            # RSRP quality check (can downgrade quality)
            rsrp_quality = "critical"
            if rsrp is not None:
                for level in ["excellent", "good", "moderate", "poor", "critical"]:
                    if rsrp >= RSRP_THRESHOLDS[level]:
                        rsrp_quality = level
                        break

            # Resolution recommendations
            resolutions = {
                "excellent": "1920x1080",
                "good": "1280x720",
                "moderate": "854x480",
                "poor": "640x360",
                "critical": "320x240",
            }

            # Warnings
            warnings = []
            if rsrp is not None and rsrp < RSRP_THRESHOLDS["poor"]:
                warnings.append("Señal muy débil")
            if sinr < 0:
                warnings.append("SINR negativo - interferencia alta")
            if rsrp_quality == "critical":
                warnings.append("RSRP crítico - posible pérdida de conexión")

            return {
                "available": True,
                "quality": quality,
                "label": threshold["label"],
                "color": threshold["color"],
                "max_bitrate_kbps": threshold["max_bitrate_kbps"],
                "recommended_resolution": resolutions.get(quality, "640x360"),
                "sinr_db": sinr,
                "rsrp_dbm": rsrp,
                "rsrp_quality": rsrp_quality,
                "signal_percent": signal.get("signal_percent", 0),
                "warnings": warnings,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    # ======================
    # Latency Measurement
    # ======================

    def measure_latency(self, host: str = None, count: int = None) -> Dict:
        """
        Measure network latency using ping through the modem interface.
        Returns avg, min, max, jitter in milliseconds.
        """
        target = host or self.LATENCY_TEST_HOST
        ping_count = count or self.LATENCY_TEST_COUNT

        try:
            # Find modem interface (192.168.8.x route)
            iface = None
            try:
                result = subprocess.run(
                    ["ip", "route", "show", "to", "192.168.8.0/24"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                for line in result.stdout.strip().split("\n"):
                    if "dev" in line:
                        parts = line.split()
                        dev_idx = parts.index("dev") + 1
                        if dev_idx < len(parts):
                            iface = parts[dev_idx]
                            break
            except Exception:
                pass

            # Build ping command
            cmd = ["ping", "-c", str(ping_count), "-W", "3", "-q", target]
            if iface:
                cmd.extend(["-I", iface])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=ping_count * 5 + 5
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f'Ping failed: {result.stderr.strip() or "No response"}',
                    "host": target,
                }

            # Parse ping output
            # rtt min/avg/max/mdev = 23.456/45.678/67.890/12.345 ms
            output = result.stdout
            rtt_line = None
            packet_loss = None

            for line in output.split("\n"):
                if "rtt" in line or "round-trip" in line:
                    rtt_line = line
                if "packet loss" in line:
                    try:
                        loss_str = line.split("%")[0].split()[-1]
                        packet_loss = float(loss_str)
                    except (ValueError, IndexError):
                        pass

            if not rtt_line:
                return {
                    "success": False,
                    "error": "Could not parse ping results",
                    "host": target,
                }

            # Extract values
            import re

            match = re.search(r"[\d.]+/[\d.]+/[\d.]+/[\d.]+", rtt_line)
            if not match:
                return {
                    "success": False,
                    "error": "Could not parse RTT",
                    "host": target,
                }

            parts = match.group().split("/")
            min_ms = round(float(parts[0]), 1)
            avg_ms = round(float(parts[1]), 1)
            max_ms = round(float(parts[2]), 1)
            jitter_ms = round(float(parts[3]), 1)

            # Store for later reference
            self._last_latency_ms = avg_ms
            self._last_jitter_ms = jitter_ms

            # Quality assessment
            if avg_ms < 30:
                quality_level = "excellent"
                quality_label = "Excelente"
            elif avg_ms < 60:
                quality_level = "good"
                quality_label = "Bueno"
            elif avg_ms < 100:
                quality_level = "moderate"
                quality_label = "Moderado"
            elif avg_ms < 200:
                quality_level = "poor"
                quality_label = "Alto"
            else:
                quality_level = "critical"
                quality_label = "Crítico"

            return {
                "success": True,
                "host": target,
                "count": ping_count,
                "interface": iface,
                "min_ms": min_ms,
                "avg_ms": avg_ms,
                "max_ms": max_ms,
                "jitter_ms": jitter_ms,
                "packet_loss": packet_loss,
                "quality": {
                    "level": quality_level,
                    "label": quality_label,
                },
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Ping timeout",
                "host": target,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "host": target}

    # ======================
    # Flight Session
    # ======================

    def get_flight_session_status(self) -> Dict:
        """Get current flight session status"""
        if self._flight_session:
            return {
                "active": True,
                "stats": self._flight_session.to_dict(),
            }
        return {"active": False}

    def start_flight_session(self) -> Dict:
        """Start a new flight session to track signal statistics"""
        if self._flight_session:
            return {
                "success": False,
                "message": "Ya hay una sesión activa",
                "active": True,
                "stats": self._flight_session.to_dict(),
            }

        self._flight_session = FlightSessionStats()
        logger.info("Flight session started")

        # Start CSV logging if logger is available
        log_result = None
        if self._flight_logger:
            log_result = self._flight_logger.start_session()
            if log_result.get("success"):
                logger.info(
                    f"Flight CSV logging started: {log_result.get('file_path')}"
                )
            else:
                logger.warning(
                    f"Failed to start CSV logging: {log_result.get('message')}"
                )

        return {
            "success": True,
            "message": "Sesión de vuelo iniciada",
            "active": True,
            "start_time": self._flight_session.start_time.isoformat(),
            "csv_logging": log_result.get("success", False) if log_result else False,
            "csv_file": log_result.get("file_path") if log_result else None,
        }

    def stop_flight_session(self) -> Dict:
        """Stop flight session and return summary"""
        if not self._flight_session:
            return {"success": False, "message": "No hay sesión activa"}

        stats = self._flight_session.to_dict()
        self._flight_session = None
        logger.info("Flight session stopped")

        # Stop CSV logging if logger is available
        log_result = None
        if self._flight_logger and self._flight_logger.is_active():
            log_result = self._flight_logger.stop_session()
            if log_result.get("success"):
                logger.info(
                    f"Flight CSV logging stopped: {log_result.get('file_path')}"
                )
            else:
                logger.warning(
                    f"Failed to stop CSV logging: {log_result.get('message')}"
                )

        return {
            "success": True,
            "message": "Sesión de vuelo finalizada",
            "active": False,
            "stats": stats,
            "csv_file": log_result.get("file_path") if log_result else None,
        }

    def record_flight_sample(self) -> Dict:
        """Record a signal sample during flight session"""
        if not self._flight_session:
            return {"success": False, "message": "No hay sesión activa"}

        try:
            signal = self._get_signal_info_sync()
            network = self._get_network_info_sync()

            if not signal:
                return {"success": False, "message": "No signal data available"}

            # Parse values
            sinr = None
            sinr_str = signal.get("sinr", "")
            if sinr_str:
                try:
                    sinr = float(sinr_str.replace("dB", "").strip())
                except (ValueError, AttributeError):
                    pass

            rsrp = None
            rsrp_str = signal.get("rsrp", "")
            if rsrp_str:
                try:
                    rsrp = float(rsrp_str.replace("dBm", "").strip())
                except (ValueError, AttributeError):
                    pass

            current_band = signal.get("band", "")

            sample = {
                "timestamp": datetime.now().isoformat(),
                "rssi": signal.get("rssi", ""),
                "rsrp": rsrp_str,
                "rsrq": signal.get("rsrq", ""),
                "sinr": sinr_str,
                "cell_id": signal.get("cell_id", ""),
                "pci": signal.get("pci", ""),
                "band": current_band,
                "network_type": network.get("network_type_ex", "") if network else "",
                "operator": network.get("operator", "") if network else "",
                "latency_ms": self._last_latency_ms,
            }

            self._flight_session.samples.append(sample)

            # Log to CSV if logger is available
            if self._flight_logger and self._flight_logger.is_active():
                log_result = self._flight_logger.log_sample(sample)
                if not log_result.get("success"):
                    logger.warning(
                        f"Failed to log flight sample to CSV: {log_result.get('message')}"
                    )

            # Update stats
            if sinr is not None:
                self._flight_session.min_sinr = min(self._flight_session.min_sinr, sinr)
                self._flight_session.max_sinr = max(self._flight_session.max_sinr, sinr)
            if rsrp is not None:
                self._flight_session.min_rsrp = min(self._flight_session.min_rsrp, rsrp)
                self._flight_session.max_rsrp = max(self._flight_session.max_rsrp, rsrp)
            if self._last_latency_ms is not None:
                self._flight_session.latency_samples.append(self._last_latency_ms)
                avg = sum(self._flight_session.latency_samples) / len(
                    self._flight_session.latency_samples
                )
                self._flight_session.avg_latency_ms = avg

            # Track band changes
            if current_band and current_band != self._flight_session.last_band:
                if self._flight_session.last_band:
                    self._flight_session.band_changes += 1
                self._flight_session.last_band = current_band

            return {
                "success": True,
                "sample_count": len(self._flight_session.samples),
                "sample": sample,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def reboot(self) -> Dict:
        """Reboot the modem"""
        try:
            success = self._reboot_sync()
            return {
                "success": success,
                "message": "Módem reiniciando..." if success else self._last_error,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ======================
    # HiLink-specific methods (preserved from original)
    # ======================

    def _get_device_info_sync(self) -> Dict:
        """Get device information (sync)"""
        if not self._ensure_connected():
            return {}

        try:
            info = self._client.device.information()
            return {
                "device_name": info.get("DeviceName", ""),
                "serial_number": info.get("SerialNumber", ""),
                "imei": info.get("Imei", ""),
                "imsi": info.get("Imsi", ""),
                "iccid": info.get("Iccid", ""),
                "hardware_version": info.get("HardwareVersion", ""),
                "software_version": info.get("SoftwareVersion", ""),
                "mac_address1": info.get("MacAddress1", ""),
                "mac_address2": info.get("MacAddress2", ""),
                "product_family": info.get("ProductFamily", ""),
                "classify": info.get("Classify", ""),
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return {}

    def _get_signal_info_sync(self) -> Dict:
        """Get signal information (sync)"""
        if not self._ensure_connected():
            return {}

        try:
            signal = self._client.device.signal()

            rssi_str = signal.get("rssi", "")
            signal_percent = None
            if rssi_str:
                try:
                    rssi = int(rssi_str.replace("dBm", "").strip())
                    signal_percent = max(0, min(100, int((rssi + 113) * 100 / 62)))
                except:
                    pass

            return {
                "rssi": signal.get("rssi", ""),
                "rsrp": signal.get("rsrp", ""),
                "rsrq": signal.get("rsrq", ""),
                "sinr": signal.get("sinr", ""),
                "cell_id": signal.get("cell_id", ""),
                "pci": signal.get("pci", ""),
                "band": signal.get("band", ""),
                "signal_percent": signal_percent,
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return {}

    def _get_network_info_sync(self) -> Dict:
        """Get network/carrier information (sync)"""
        if not self._ensure_connected():
            return {}

        try:
            status = self._client.monitoring.status()

            network_types = {
                "0": "No Service",
                "1": "GSM",
                "2": "GPRS",
                "3": "EDGE",
                "4": "WCDMA",
                "5": "HSDPA",
                "6": "HSUPA",
                "7": "HSPA+",
                "8": "TD-SCDMA",
                "9": "HSPA+",
                "19": "LTE",
                "41": "LTE",
                "101": "5G NR",
            }

            network_types_ex = {
                "0": "No Service",
                "1": "GSM",
                "2": "GPRS",
                "3": "EDGE",
                "41": "UMTS",
                "42": "HSDPA",
                "43": "HSUPA",
                "44": "HSPA",
                "45": "HSPA+",
                "46": "DC-HSPA+",
                "61": "LTE",
                "62": "LTE+",
                "63": "LTE-A",
                "64": "LTE (4G)",
                "65": "LTE-A Pro",
                "71": "CDMA",
                "72": "EVDO Rev.0",
                "73": "EVDO Rev.A",
                "74": "EVDO Rev.B",
                "81": "TD-SCDMA",
                "101": "LTE",
                "1011": "LTE+",
                "111": "5G NSA",
                "121": "5G SA",
            }

            current_network = status.get("CurrentNetworkType", "0")
            current_network_ex = status.get("CurrentNetworkTypeEx", "")
            network_type = network_types.get(
                current_network, f"Unknown ({current_network})"
            )
            network_type_ex = network_types_ex.get(str(current_network_ex), "")

            signal_icon = int(status.get("SignalIcon", 0))

            operator_name = ""
            operator_code = ""
            rat = ""
            try:
                plmn = self._client.net.current_plmn()
                operator_name = plmn.get("FullName", "") or plmn.get("ShortName", "")
                operator_code = plmn.get("Numeric", "")
                rat_code = plmn.get("Rat", "")
                rat_types = {"0": "GSM", "2": "WCDMA", "7": "LTE", "12": "5G NR"}
                rat = rat_types.get(str(rat_code), "")
            except:
                operator_name = status.get("FullName", "")

            conn_status_map = {
                "900": "Connecting",
                "901": "Connected",
                "902": "Disconnected",
                "903": "Disconnecting",
            }
            conn_code = status.get("ConnectionStatus", "")
            connection_status = conn_status_map.get(str(conn_code), conn_code)

            return {
                "operator": operator_name,
                "operator_code": operator_code,
                "network_type": network_type,
                "network_type_ex": network_type_ex or network_type,
                "current_network_type_ex": current_network_ex,
                "rat": rat,
                "signal_strength": signal_icon,
                "signal_icon": signal_icon,
                "roaming": status.get("RoamingStatus", "0") == "1",
                "sim_status": status.get("SimStatus", ""),
                "connection_status": connection_status,
                "connection_status_code": conn_code,
                "primary_dns": status.get("PrimaryDns", ""),
                "secondary_dns": status.get("SecondaryDns", ""),
                "max_signal": status.get("maxsignal", 5),
                "fly_mode": status.get("flymode", "0") == "1",
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return {}

    def _get_traffic_stats_sync(self) -> Dict:
        """Get traffic statistics (sync)"""
        if not self._ensure_connected():
            return {}

        try:
            stats = self._client.monitoring.traffic_statistics()

            def format_bytes(b):
                try:
                    b = int(b)
                    for unit in ["B", "KB", "MB", "GB"]:
                        if b < 1024:
                            return f"{b:.1f} {unit}"
                        b /= 1024
                    return f"{b:.1f} TB"
                except:
                    return b

            return {
                "current_download": format_bytes(stats.get("CurrentDownload", 0)),
                "current_upload": format_bytes(stats.get("CurrentUpload", 0)),
                "total_download": format_bytes(stats.get("TotalDownload", 0)),
                "total_upload": format_bytes(stats.get("TotalUpload", 0)),
                "current_connect_time": int(stats.get("CurrentConnectTime", 0)),
                "total_connect_time": int(stats.get("TotalConnectTime", 0)),
                "current_download_raw": int(stats.get("CurrentDownload", 0)),
                "current_upload_raw": int(stats.get("CurrentUpload", 0)),
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return {}

    def _reconnect_network_sync(self) -> bool:
        """Force network reconnection"""
        try:
            xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<request>
<Mode>0</Mode>
<Plmn></Plmn>
<Rat></Rat>
</request>"""

            success, msg = self._direct_api_post("api/net/register", xml_data)
            if success:
                logger.info("Network re-registration initiated")
                return True

            self._last_error = "Reconexión no soportada en este módem"
            return False
        except Exception as e:
            self._last_error = str(e)
            return False

    def _set_lte_band_sync(self, band_mask: int) -> bool:
        """Set LTE band mask"""
        try:
            lte_band_hex = format(band_mask, "X")

            if self._ensure_connected():
                current = self._client.net.net_mode()
                network_band = current.get("NetworkBand", "3FFFFFFF")
            else:
                network_band = "3FFFFFFF"

            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
<NetworkMode>03</NetworkMode>
<NetworkBand>{network_band}</NetworkBand>
<LTEBand>{lte_band_hex}</LTEBand>
</request>"""

            success, msg = self._direct_api_post("api/net/net-mode", xml_data)
            if success:
                logger.info(f"LTE band set to: {lte_band_hex}")
                return True
            else:
                self._last_error = msg
                return False
        except Exception as e:
            self._last_error = str(e)
            return False

    def _reboot_sync(self) -> bool:
        """Reboot the modem"""
        if not self._ensure_connected():
            return False

        try:
            self._client.device.reboot()
            self._disconnect()
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    # Keep all async methods and additional HiLink-specific features
    # (These are preserved for backward compatibility with existing hilink_service usage)

    async def get_full_status(self) -> Dict:
        """Get complete modem status"""
        if not HILINK_AVAILABLE:
            return {"available": False, "error": "huawei-lte-api not installed"}

        try:
            device = await self._run_sync(self._get_device_info_sync)
            if not device:
                return {
                    "available": False,
                    "error": self._last_error or "Could not connect to modem",
                }

            signal = await self._run_sync(self._get_signal_info_sync)
            network = await self._run_sync(self._get_network_info_sync)
            traffic = await self._run_sync(self._get_traffic_stats_sync)

            return {
                "available": True,
                "device": device,
                "signal": signal,
                "network": network,
                "traffic": traffic,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def get_band_presets(self) -> Dict:
        """Get available band presets"""
        return {
            "presets": LTE_BAND_PRESETS,
            "individual_bands": LTE_BANDS,
        }

    def get_info(self) -> Dict:
        """Get provider information"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": "Huawei E3372h-153 HiLink modem with video streaming optimization",
            "features": [
                "LTE Cat 4 (150 Mbps down, 50 Mbps up)",
                "Band optimization (B1, B3, B7, B8, B20)",
                "Video quality assessment",
                "Flight session tracking",
                "Latency monitoring",
            ],
            "modes": ["HiLink (Router mode)"],
        }
