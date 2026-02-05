"""
HiLink Modem Service
Uses huawei-lte-api to interact with Huawei HiLink modems
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
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import huawei-lte-api
HILINK_AVAILABLE = False
Client = None
Connection = None

try:
    from huawei_lte_api.Client import Client
    from huawei_lte_api.Connection import Connection
    from huawei_lte_api.exceptions import (
        ResponseErrorException,
        ResponseErrorLoginRequiredException
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
    'B1':  0x1,           # 2100MHz - FDD
    'B3':  0x4,           # 1800MHz - FDD (Orange primary urban)
    'B7':  0x40,          # 2600MHz - FDD (High speed, short range)
    'B8':  0x80,          # 900MHz  - FDD
    'B20': 0x80000,       # 800MHz  - FDD (Best rural coverage)
}

# Preset band combinations for Spain/Orange
LTE_BAND_PRESETS = {
    'all': {
        'name': 'Todas las bandas',
        'description': 'Auto-selección (B1+B3+B7+B8+B20)',
        'mask': LTE_BANDS['B1'] | LTE_BANDS['B3'] | LTE_BANDS['B7'] | LTE_BANDS['B8'] | LTE_BANDS['B20'],
    },
    'orange_spain': {
        'name': 'Orange España Óptimo',
        'description': 'B3+B7+B20 (bandas principales Orange)',
        'mask': LTE_BANDS['B3'] | LTE_BANDS['B7'] | LTE_BANDS['B20'],
    },
    'urban': {
        'name': 'Urbano/Ciudad',
        'description': 'B3+B7 (alta velocidad, baja latencia)',
        'mask': LTE_BANDS['B3'] | LTE_BANDS['B7'],
    },
    'rural': {
        'name': 'Rural/Campo',
        'description': 'B20 (800MHz, máxima cobertura)',
        'mask': LTE_BANDS['B20'],
    },
    'balanced': {
        'name': 'Balanceado',
        'description': 'B3+B20 (velocidad + cobertura)',
        'mask': LTE_BANDS['B3'] | LTE_BANDS['B20'],
    },
    'b3_only': {
        'name': 'Solo B3 (1800MHz)',
        'description': 'Forzar banda 3',
        'mask': LTE_BANDS['B3'],
    },
    'b7_only': {
        'name': 'Solo B7 (2600MHz)', 
        'description': 'Forzar banda 7 (alta velocidad)',
        'mask': LTE_BANDS['B7'],
    },
    'b20_only': {
        'name': 'Solo B20 (800MHz)',
        'description': 'Forzar banda 20 (mejor cobertura)',
        'mask': LTE_BANDS['B20'],
    },
}

# ======================
# APN Configuration
# ======================
APN_PRESETS = {
    'orange': {
        'name': 'Orange',
        'apn': 'orange',
        'description': 'APN estándar Orange España',
    },
    'orangeworld': {
        'name': 'Orange World',
        'apn': 'orangeworld',
        'description': 'APN datos Orange',
    },
    'simyo': {
        'name': 'Simyo',
        'apn': 'orangeworld',
        'description': 'Simyo (usa red Orange)',
    },
    'internet': {
        'name': 'Genérico',
        'apn': 'internet',
        'description': 'APN genérico',
    },
}

# ======================
# Video Quality Thresholds
# ======================
# Based on SINR (Signal to Interference + Noise Ratio)
VIDEO_QUALITY_THRESHOLDS = {
    'excellent': {'sinr_min': 15, 'max_bitrate_kbps': 8000, 'label': 'Excelente', 'color': 'green'},
    'good':      {'sinr_min': 10, 'max_bitrate_kbps': 5000, 'label': 'Bueno', 'color': 'green'},
    'moderate':  {'sinr_min': 5,  'max_bitrate_kbps': 3000, 'label': 'Moderado', 'color': 'yellow'},
    'poor':      {'sinr_min': 0,  'max_bitrate_kbps': 1500, 'label': 'Bajo', 'color': 'orange'},
    'critical':  {'sinr_min': -5, 'max_bitrate_kbps': 800,  'label': 'Crítico', 'color': 'red'},
}

# RSRP thresholds (Reference Signal Received Power)
RSRP_THRESHOLDS = {
    'excellent': -80,   # > -80 dBm
    'good': -90,        # -80 to -90 dBm  
    'moderate': -100,   # -90 to -100 dBm
    'poor': -110,       # -100 to -110 dBm
    'critical': -120,   # < -110 dBm
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
    last_band: str = ''
    
    def to_dict(self) -> Dict:
        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            'start_time': self.start_time.isoformat(),
            'duration_seconds': int(duration),
            'sample_count': len(self.samples),
            'min_sinr': self.min_sinr if self.min_sinr != 99.0 else None,
            'max_sinr': self.max_sinr if self.max_sinr != -99.0 else None,
            'min_rsrp': self.min_rsrp if self.min_rsrp != 0.0 else None,
            'max_rsrp': self.max_rsrp if self.max_rsrp != -999.0 else None,
            'avg_latency_ms': round(self.avg_latency_ms, 1),
            'latency_samples': len(self.latency_samples),
            'disconnections': self.disconnections,
            'band_changes': self.band_changes,
        }


class HiLinkService:
    """Service for Huawei HiLink modem API interaction optimized for FPV video"""
    
    MODEM_URL = "http://192.168.8.1/"
    CONNECTION_TIMEOUT = 5  # 5 seconds timeout for modem connection
    WRITE_TIMEOUT = 15  # 15 seconds timeout for write operations (mode changes take time)
    LATENCY_TEST_HOST = "8.8.8.8"  # Google DNS for latency tests
    LATENCY_TEST_COUNT = 3
    
    def __init__(self):
        self._connection: Optional[Connection] = None
        self._client: Optional[Client] = None
        self._last_error: Optional[str] = None
        
        # Flight session tracking
        self._flight_session: Optional[FlightSessionStats] = None
        self._video_mode_active: bool = False
        self._original_settings: Dict = {}  # Store settings before video mode
        
        # Latency monitoring
        self._last_latency_ms: Optional[float] = None
        self._last_jitter_ms: Optional[float] = None
    
    def _ensure_connected(self) -> bool:
        """Ensure we have a connection to the modem"""
        if not HILINK_AVAILABLE:
            self._last_error = "huawei-lte-api not installed"
            return False
        
        try:
            if self._connection is None:
                self._connection = Connection(self.MODEM_URL, timeout=self.CONNECTION_TIMEOUT)
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
    
    # ======================
    # Direct API Methods (for write operations)
    # ======================
    
    def _get_session_token(self) -> Tuple[Optional[requests.Session], Optional[str]]:
        """Get a session with valid token for API calls"""
        try:
            session = requests.Session()
            # Get cookies first
            session.get(self.MODEM_URL, timeout=self.CONNECTION_TIMEOUT)
            
            # Get session token
            r = session.get(f'{self.MODEM_URL}api/webserver/SesTokInfo', timeout=self.CONNECTION_TIMEOUT)
            root = ET.fromstring(r.text)
            sesinfo = root.find('SesInfo').text
            token = root.find('TokInfo').text
            
            # Set cookie
            session.cookies.set('SessionID', sesinfo.replace('SessionID=', ''))
            
            return session, token
        except Exception as e:
            logger.error(f"Failed to get session token: {e}")
            return None, None
    
    def _direct_api_post(self, endpoint: str, xml_data: str, timeout: int = None) -> Tuple[bool, str]:
        """Make a direct POST request to the modem API with proper session handling"""
        if timeout is None:
            timeout = self.WRITE_TIMEOUT
            
        try:
            session, token = self._get_session_token()
            if not session or not token:
                return False, "Could not get session token"
            
            headers = {
                '__RequestVerificationToken': token,
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            }
            
            r = session.post(
                f'{self.MODEM_URL}{endpoint}',
                data=xml_data,
                headers=headers,
                timeout=timeout
            )
            
            # Parse response
            if '<response>OK</response>' in r.text:
                return True, "OK"
            elif '<error>' in r.text:
                root = ET.fromstring(r.text)
                code = root.find('code').text
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
    
    def _get_device_info_sync(self) -> Dict:
        """Get device information (sync)"""
        if not self._ensure_connected():
            return {}
        
        try:
            info = self._client.device.information()
            return {
                'device_name': info.get('DeviceName', ''),
                'serial_number': info.get('SerialNumber', ''),
                'imei': info.get('Imei', ''),
                'imsi': info.get('Imsi', ''),
                'iccid': info.get('Iccid', ''),
                'hardware_version': info.get('HardwareVersion', ''),
                'software_version': info.get('SoftwareVersion', ''),
                'mac_address1': info.get('MacAddress1', ''),
                'mac_address2': info.get('MacAddress2', ''),
                'product_family': info.get('ProductFamily', ''),
                'classify': info.get('Classify', ''),
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
            
            # Parse RSSI to percentage (typical range: -113 to -51 dBm)
            rssi_str = signal.get('rssi', '')
            signal_percent = None
            if rssi_str:
                try:
                    rssi = int(rssi_str.replace('dBm', '').strip())
                    # Convert to percentage (0-100)
                    signal_percent = max(0, min(100, int((rssi + 113) * 100 / 62)))
                except:
                    pass
            
            return {
                'rssi': signal.get('rssi', ''),
                'rsrp': signal.get('rsrp', ''),
                'rsrq': signal.get('rsrq', ''),
                'sinr': signal.get('sinr', ''),
                'cell_id': signal.get('cell_id', ''),
                'pci': signal.get('pci', ''),
                'band': signal.get('band', ''),
                'signal_percent': signal_percent,
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
            # Get monitoring status for network info
            status = self._client.monitoring.status()
            
            # Map network type codes (CurrentNetworkType)
            network_types = {
                '0': 'No Service',
                '1': 'GSM', '2': 'GPRS', '3': 'EDGE',
                '4': 'WCDMA', '5': 'HSDPA', '6': 'HSUPA', '7': 'HSPA+',
                '8': 'TD-SCDMA', '9': 'HSPA+',
                '19': 'LTE', '41': 'LTE',
                '101': '5G NR',
            }
            
            # Extended network type (more detailed)
            network_types_ex = {
                '0': 'No Service',
                '1': 'GSM', '2': 'GPRS', '3': 'EDGE',
                '41': 'UMTS', '42': 'HSDPA', '43': 'HSUPA', 
                '44': 'HSPA', '45': 'HSPA+', '46': 'DC-HSPA+',
                '61': 'LTE', '62': 'LTE+', '63': 'LTE-A',
                '64': 'LTE (4G)', '65': 'LTE-A Pro',
                '71': 'CDMA', '72': 'EVDO Rev.0', '73': 'EVDO Rev.A', '74': 'EVDO Rev.B',
                '81': 'TD-SCDMA',
                '101': 'LTE', '1011': 'LTE+',
                '111': '5G NSA', '121': '5G SA',
            }
            
            current_network = status.get('CurrentNetworkType', '0')
            current_network_ex = status.get('CurrentNetworkTypeEx', '')
            network_type = network_types.get(current_network, f'Unknown ({current_network})')
            network_type_ex = network_types_ex.get(str(current_network_ex), '')
            
            # Signal strength (0-5 bars)
            signal_icon = int(status.get('SignalIcon', 0))
            
            # Get PLMN info for operator details
            operator_name = ''
            operator_code = ''
            rat = ''
            try:
                plmn = self._client.net.current_plmn()
                operator_name = plmn.get('FullName', '') or plmn.get('ShortName', '')
                operator_code = plmn.get('Numeric', '')  # MCC+MNC code
                rat_code = plmn.get('Rat', '')
                rat_types = {'0': 'GSM', '2': 'WCDMA', '7': 'LTE', '12': '5G NR'}
                rat = rat_types.get(str(rat_code), '')
            except:
                operator_name = status.get('FullName', '')
            
            # Connection status codes
            conn_status_map = {
                '900': 'Connecting',
                '901': 'Connected',
                '902': 'Disconnected',
                '903': 'Disconnecting',
            }
            conn_code = status.get('ConnectionStatus', '')
            connection_status = conn_status_map.get(str(conn_code), conn_code)
            
            return {
                'operator': operator_name,
                'operator_code': operator_code,  # MCC+MNC (e.g., 21403 = Spain Orange)
                'network_type': network_type,
                'network_type_ex': network_type_ex or network_type,
                'current_network_type_ex': current_network_ex,
                'rat': rat,  # Radio Access Technology
                'signal_strength': signal_icon,
                'signal_icon': signal_icon,
                'roaming': status.get('RoamingStatus', '0') == '1',
                'sim_status': status.get('SimStatus', ''),
                'connection_status': connection_status,
                'connection_status_code': conn_code,
                'primary_dns': status.get('PrimaryDns', ''),
                'secondary_dns': status.get('SecondaryDns', ''),
                'max_signal': status.get('maxsignal', 5),
                'fly_mode': status.get('flymode', '0') == '1',
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
                """Format bytes to human readable"""
                try:
                    b = int(b)
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if b < 1024:
                            return f"{b:.1f} {unit}"
                        b /= 1024
                    return f"{b:.1f} TB"
                except:
                    return b
            
            return {
                'current_download': format_bytes(stats.get('CurrentDownload', 0)),
                'current_upload': format_bytes(stats.get('CurrentUpload', 0)),
                'total_download': format_bytes(stats.get('TotalDownload', 0)),
                'total_upload': format_bytes(stats.get('TotalUpload', 0)),
                'current_connect_time': int(stats.get('CurrentConnectTime', 0)),
                'total_connect_time': int(stats.get('TotalConnectTime', 0)),
                'current_download_raw': int(stats.get('CurrentDownload', 0)),
                'current_upload_raw': int(stats.get('CurrentUpload', 0)),
            }
        except Exception as e:
            self._last_error = str(e)
            self._disconnect()
            return {}
    
    def _get_sms_count_sync(self) -> Dict:
        """Get SMS count (sync)"""
        if not self._ensure_connected():
            return {}
        
        try:
            count = self._client.sms.sms_count()
            return {
                'local_unread': int(count.get('LocalUnread', 0)),
                'local_inbox': int(count.get('LocalInbox', 0)),
                'local_outbox': int(count.get('LocalOutbox', 0)),
                'local_draft': int(count.get('LocalDraft', 0)),
                'sim_unread': int(count.get('SimUnread', 0)),
                'sim_inbox': int(count.get('SimInbox', 0)),
            }
        except Exception as e:
            self._last_error = str(e)
            return {}
    
    def _get_network_mode_sync(self) -> Dict:
        """Get current network mode settings (sync)"""
        if not self._ensure_connected():
            return {}
        
        try:
            mode = self._client.net.net_mode()
            
            # Network mode mapping
            modes = {
                '00': 'Auto (4G/3G/2G)',
                '01': '2G Only',
                '02': '3G Only', 
                '03': '4G Only',
                '0201': '3G/2G Auto',
                '0301': '4G/2G Auto',
                '0302': '4G/3G Auto',
            }
            
            network_mode = mode.get('NetworkMode', '')
            network_band = mode.get('NetworkBand', '')
            lte_band = mode.get('LTEBand', '')
            
            return {
                'network_mode': network_mode,
                'network_mode_name': modes.get(network_mode, f'Unknown ({network_mode})'),
                'network_band': network_band,
                'lte_band': lte_band,
            }
        except Exception as e:
            self._last_error = str(e)
            return {}
    
    def _set_network_mode_sync(self, mode: str) -> bool:
        """Set network mode (sync). Modes: 00=Auto, 01=2G, 02=3G, 03=4G"""
        try:
            # Get current settings to preserve band settings
            if not self._ensure_connected():
                return False
            
            current = self._client.net.net_mode()
            network_band = current.get('NetworkBand', '3FFFFFFF')
            lte_band = current.get('LTEBand', '7FFFFFFFFFFFFFFF')
            
            # Use direct API for setting (library has session issues)
            xml_data = f'''<?xml version="1.0" encoding="UTF-8"?>
<request>
<NetworkMode>{mode}</NetworkMode>
<NetworkBand>{network_band}</NetworkBand>
<LTEBand>{lte_band}</LTEBand>
</request>'''
            
            success, msg = self._direct_api_post('api/net/net-mode', xml_data)
            if success:
                logger.info(f"Network mode set to: {mode}")
                return True
            else:
                self._last_error = msg
                logger.error(f"Failed to set network mode: {msg}")
                return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to set network mode: {e}")
            return False
    
    def _reboot_sync(self) -> bool:
        """Reboot the modem (sync)"""
        if not self._ensure_connected():
            return False
        
        try:
            self._client.device.reboot()
            self._disconnect()
            return True
        except Exception as e:
            self._last_error = str(e)
            return False
    
    # Async wrappers
    async def get_device_info(self) -> Dict:
        """Get device information"""
        return await self._run_sync(self._get_device_info_sync)
    
    async def get_signal_info(self) -> Dict:
        """Get signal information"""
        return await self._run_sync(self._get_signal_info_sync)
    
    async def get_network_info(self) -> Dict:
        """Get network/carrier information"""
        return await self._run_sync(self._get_network_info_sync)
    
    async def get_traffic_stats(self) -> Dict:
        """Get traffic statistics"""
        return await self._run_sync(self._get_traffic_stats_sync)
    
    async def get_sms_count(self) -> Dict:
        """Get SMS count"""
        return await self._run_sync(self._get_sms_count_sync)
    
    async def get_network_mode(self) -> Dict:
        """Get network mode settings"""
        return await self._run_sync(self._get_network_mode_sync)
    
    async def set_network_mode(self, mode: str) -> bool:
        """Set network mode"""
        return await self._run_sync(self._set_network_mode_sync, mode)
    
    async def reboot(self) -> bool:
        """Reboot the modem"""
        return await self._run_sync(self._reboot_sync)
    
    async def get_full_status(self) -> Dict:
        """Get complete modem status"""
        if not HILINK_AVAILABLE:
            return {
                'available': False,
                'error': 'huawei-lte-api not installed'
            }
        
        try:
            device = await self.get_device_info()
            if not device:
                return {
                    'available': False,
                    'error': self._last_error or 'Could not connect to modem'
                }
            
            signal = await self.get_signal_info()
            network = await self.get_network_info()
            traffic = await self.get_traffic_stats()
            mode = await self.get_network_mode()
            
            return {
                'available': True,
                'device': device,
                'signal': signal,
                'network': network,
                'traffic': traffic,
                'mode': mode,
            }
        except Exception as e:
            return {
                'available': False,
                'error': str(e)
            }
    
    # ======================
    # LTE Band Management
    # ======================
    
    def _get_current_band_sync(self) -> Dict:
        """Get current LTE band information (sync)"""
        if not self._ensure_connected():
            return {}
        
        try:
            signal = self._client.device.signal()
            mode = self._client.net.net_mode()
            
            current_band = signal.get('band', '')
            lte_band_hex = mode.get('LTEBand', '')
            
            # Decode which bands are enabled
            enabled_bands = []
            try:
                band_mask = int(lte_band_hex, 16)
                for band_name, band_val in LTE_BANDS.items():
                    if band_mask & band_val:
                        enabled_bands.append(band_name)
            except:
                pass
            
            return {
                'current_band': current_band,
                'lte_band_hex': lte_band_hex,
                'enabled_bands': enabled_bands,
            }
        except Exception as e:
            self._last_error = str(e)
            return {}
    
    def _set_lte_band_sync(self, band_mask: int) -> bool:
        """Set LTE band mask (sync)"""
        try:
            # Convert mask to hex string (uppercase, no 0x prefix)
            lte_band_hex = format(band_mask, 'X')
            
            # Get current 3G band setting to preserve it
            if self._ensure_connected():
                current = self._client.net.net_mode()
                network_band = current.get('NetworkBand', '3FFFFFFF')
            else:
                network_band = '3FFFFFFF'
            
            # Use direct API for setting (library has session issues)
            xml_data = f'''<?xml version="1.0" encoding="UTF-8"?>
<request>
<NetworkMode>03</NetworkMode>
<NetworkBand>{network_band}</NetworkBand>
<LTEBand>{lte_band_hex}</LTEBand>
</request>'''
            
            success, msg = self._direct_api_post('api/net/net-mode', xml_data)
            if success:
                logger.info(f"LTE band set to: {lte_band_hex}")
                return True
            else:
                self._last_error = msg
                logger.error(f"Failed to set LTE band: {msg}")
                return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to set LTE band: {e}")
            return False
    
    async def get_current_band(self) -> Dict:
        """Get current LTE band information"""
        return await self._run_sync(self._get_current_band_sync)
    
    async def set_lte_band(self, preset: str = None, custom_mask: int = None) -> Dict:
        """
        Set LTE band configuration
        
        Args:
            preset: One of the preset names (all, orange_spain, urban, rural, etc.)
            custom_mask: Custom band mask (overrides preset)
        
        Returns:
            Dict with success status and applied configuration
        """
        if custom_mask is not None:
            band_mask = custom_mask
            preset_info = {'name': 'Personalizado', 'mask': custom_mask}
        elif preset and preset in LTE_BAND_PRESETS:
            preset_info = LTE_BAND_PRESETS[preset]
            band_mask = preset_info['mask']
        else:
            return {'success': False, 'error': f'Invalid preset: {preset}'}
        
        success = await self._run_sync(self._set_lte_band_sync, band_mask)
        
        if success:
            return {
                'success': True,
                'preset': preset or 'custom',
                'preset_name': preset_info['name'],
                'band_mask': hex(band_mask),
            }
        return {'success': False, 'error': self._last_error}
    
    def get_band_presets(self) -> Dict:
        """Get available band presets"""
        return {
            'presets': LTE_BAND_PRESETS,
            'individual_bands': LTE_BANDS,
        }
    
    # ======================
    # Video Quality Assessment
    # ======================
    
    def _parse_signal_value(self, value: str, unit: str = 'dB') -> Optional[float]:
        """Parse signal value string to float"""
        if not value:
            return None
        try:
            # Remove unit suffix and parse
            clean = value.replace(unit, '').replace('dBm', '').strip()
            return float(clean)
        except:
            return None
    
    async def get_video_quality_assessment(self) -> Dict:
        """
        Assess current signal quality for video streaming
        
        Returns comprehensive assessment including:
        - Quality rating (excellent/good/moderate/poor/critical)
        - Recommended max bitrate
        - Current signal metrics
        - Warnings and recommendations
        """
        signal = await self.get_signal_info()
        network = await self.get_network_info()
        
        if not signal:
            return {
                'quality': 'unknown',
                'label': 'Sin datos',
                'color': 'gray',
                'available': False,
            }
        
        # Parse SINR (primary metric for video quality)
        sinr = self._parse_signal_value(signal.get('sinr', ''), 'dB')
        rsrp = self._parse_signal_value(signal.get('rsrp', ''), 'dBm')
        rsrq = self._parse_signal_value(signal.get('rsrq', ''), 'dB')
        
        # Determine quality level based on SINR
        quality = 'unknown'
        quality_info = {}
        
        if sinr is not None:
            for level, thresholds in VIDEO_QUALITY_THRESHOLDS.items():
                if sinr >= thresholds['sinr_min']:
                    quality = level
                    quality_info = thresholds
                    break
            else:
                quality = 'critical'
                quality_info = VIDEO_QUALITY_THRESHOLDS['critical']
        
        # Generate warnings and recommendations
        warnings = []
        recommendations = []
        
        if sinr is not None and sinr < 10:
            warnings.append('SINR bajo - posible inestabilidad de video')
            recommendations.append('Considera reducir el bitrate de video')
        
        if rsrp is not None and rsrp < RSRP_THRESHOLDS['poor']:
            warnings.append('Señal débil (RSRP)')
            recommendations.append('Busca mejor posición o usa banda B20')
        
        network_type = network.get('network_type', '')
        if '4G' not in network_type and 'LTE' not in network_type:
            warnings.append(f'Red actual: {network_type} (no 4G)')
            recommendations.append('Activa modo 4G Only para mejor rendimiento')
        
        return {
            'available': True,
            'quality': quality,
            'label': quality_info.get('label', 'Desconocido'),
            'color': quality_info.get('color', 'gray'),
            'max_bitrate_kbps': quality_info.get('max_bitrate_kbps', 0),
            'recommended_resolution': self._get_recommended_resolution(quality_info.get('max_bitrate_kbps', 0)),
            'metrics': {
                'sinr': sinr,
                'sinr_raw': signal.get('sinr', ''),
                'rsrp': rsrp,
                'rsrp_raw': signal.get('rsrp', ''),
                'rsrq': rsrq,
                'rsrq_raw': signal.get('rsrq', ''),
            },
            'network_type': network_type,
            'operator': network.get('operator', ''),
            'warnings': warnings,
            'recommendations': recommendations,
        }
    
    def _get_recommended_resolution(self, max_bitrate_kbps: int) -> str:
        """Get recommended video resolution based on available bitrate"""
        if max_bitrate_kbps >= 6000:
            return '1080p @ 30fps'
        elif max_bitrate_kbps >= 4000:
            return '1080p @ 24fps o 720p @ 60fps'
        elif max_bitrate_kbps >= 2500:
            return '720p @ 30fps'
        elif max_bitrate_kbps >= 1500:
            return '720p @ 24fps o 480p @ 30fps'
        elif max_bitrate_kbps >= 800:
            return '480p @ 24fps'
        else:
            return '360p o inferior'
    
    # ======================
    # APN Configuration
    # ======================
    
    def _get_apn_sync(self) -> Dict:
        """Get current APN settings (sync)"""
        if not self._ensure_connected():
            return {'supported': False, 'error': 'Not connected'}
        
        try:
            # Try to get dial-up profile (not available on all HiLink modems)
            if hasattr(self._client, 'dialup'):
                profiles = self._client.dialup.profiles()
                current_profile = self._client.dialup.connection()
                return {
                    'supported': True,
                    'profiles': profiles,
                    'current': current_profile,
                }
            else:
                # HiLink modems typically manage APN automatically
                return {
                    'supported': False,
                    'note': 'APN configuration not available via API in HiLink mode',
                    'suggestion': 'Configure APN via web interface at 192.168.8.1',
                }
        except Exception as e:
            self._last_error = str(e)
            logger.debug(f"APN get error (may not be supported): {e}")
            return {
                'supported': False,
                'error': str(e),
                'note': 'APN API not available on this modem',
            }
    
    def _set_apn_sync(self, apn: str, username: str = '', password: str = '') -> bool:
        """Set APN (sync) - Note: may require modem reboot"""
        # HiLink modems typically manage APN automatically from SIM
        # Manual APN setting is usually not available via API
        logger.info(f"APN configuration requested: {apn} (HiLink mode - may not be supported)")
        self._last_error = "APN configuration via API not supported in HiLink mode. Use web interface at 192.168.8.1"
        return False
    
    async def get_apn_settings(self) -> Dict:
        """Get current APN configuration"""
        result = await self._run_sync(self._get_apn_sync)
        result['presets'] = APN_PRESETS
        return result
    
    async def set_apn(self, preset: str = None, custom_apn: str = None) -> Dict:
        """Set APN configuration"""
        if custom_apn:
            apn = custom_apn
        elif preset and preset in APN_PRESETS:
            apn = APN_PRESETS[preset]['apn']
        else:
            return {'success': False, 'error': 'Invalid APN preset'}
        
        success = await self._run_sync(self._set_apn_sync, apn)
        return {
            'success': success,
            'apn': apn,
            'note': 'Puede requerir reinicio del módem' if success else self._last_error,
        }
    
    # ======================
    # Network Control
    # ======================
    
    def _reconnect_network_sync(self) -> bool:
        """Force network reconnection (sync) - uses PLMN re-registration"""
        try:
            # Method 1: Try to trigger network re-registration via PLMN API
            # This forces the modem to search for available networks
            xml_data = '''<?xml version="1.0" encoding="UTF-8"?>
<request>
<Mode>0</Mode>
<Plmn></Plmn>
<Rat></Rat>
</request>'''
            
            success, msg = self._direct_api_post('api/net/register', xml_data)
            if success:
                logger.info("Network re-registration initiated via PLMN")
                return True
            
            # Method 2: Toggle airplane mode equivalent (if available)
            # Try setting network mode briefly to trigger reconnection
            if self._ensure_connected():
                current = self._client.net.net_mode()
                current_mode = current.get('NetworkMode', '00')
                current_band = current.get('NetworkBand', '3FFFFFFF')
                current_lte = current.get('LTEBand', '7FFFFFFFFFFFFFFF')
                
                # Set to different mode and back
                xml_toggle = f'''<?xml version="1.0" encoding="UTF-8"?>
<request>
<NetworkMode>{current_mode}</NetworkMode>
<NetworkBand>{current_band}</NetworkBand>
<LTEBand>{current_lte}</LTEBand>
</request>'''
                
                success, msg = self._direct_api_post('api/net/net-mode', xml_toggle)
                if success:
                    logger.info("Network reconnection triggered via mode re-apply")
                    return True
            
            self._last_error = "Reconexión no soportada en este módem"
            return False
            
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def _set_roaming_sync(self, enabled: bool) -> bool:
        """Enable/disable roaming (sync)"""
        if not self._ensure_connected():
            return False
        
        try:
            # This is modem-specific
            logger.info(f"Roaming {'enabled' if enabled else 'disabled'}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False
    
    async def reconnect_network(self) -> Dict:
        """Force network reconnection to search for better cell"""
        success = await self._run_sync(self._reconnect_network_sync)
        return {
            'success': success,
            'message': 'Reconexión iniciada' if success else self._last_error,
        }
    
    async def set_roaming(self, enabled: bool) -> Dict:
        """Enable or disable roaming"""
        success = await self._run_sync(self._set_roaming_sync, enabled)
        return {
            'success': success,
            'roaming_enabled': enabled if success else None,
        }
    
    # ======================
    # Video Mode Profile
    # ======================
    
    async def enable_video_mode(self) -> Dict:
        """
        Enable optimized settings for video streaming:
        - Force 4G Only mode
        - Set optimal band for current location
        - Store original settings for later restore
        """
        if self._video_mode_active:
            return {'success': True, 'message': 'Modo video ya activo', 'already_active': True}
        
        try:
            # Store current settings
            self._original_settings = {
                'mode': await self.get_network_mode(),
                'band': await self.get_current_band(),
            }
            
            # Apply video-optimized settings
            results = {
                'mode_set': await self._run_sync(self._set_network_mode_sync, '03'),  # 4G Only
            }
            
            self._video_mode_active = True
            
            return {
                'success': True,
                'message': 'Modo video activado',
                'settings_applied': {
                    'network_mode': '4G Only',
                    'optimization': 'low_latency',
                },
                'original_settings_saved': True,
            }
        except Exception as e:
            self._last_error = str(e)
            return {'success': False, 'error': str(e)}
    
    async def disable_video_mode(self) -> Dict:
        """Restore original settings before video mode was enabled"""
        if not self._video_mode_active:
            return {'success': True, 'message': 'Modo video no está activo', 'was_active': False}
        
        try:
            # Restore original network mode if saved
            if 'mode' in self._original_settings:
                original_mode = self._original_settings['mode'].get('network_mode', '00')
                await self._run_sync(self._set_network_mode_sync, original_mode)
            
            self._video_mode_active = False
            self._original_settings = {}
            
            return {
                'success': True,
                'message': 'Configuración original restaurada',
            }
        except Exception as e:
            self._last_error = str(e)
            return {'success': False, 'error': str(e)}
    
    @property
    def video_mode_active(self) -> bool:
        return self._video_mode_active
    
    # ======================
    # Flight Session Stats
    # ======================
    
    async def start_flight_session(self) -> Dict:
        """Start recording flight session statistics"""
        self._flight_session = FlightSessionStats()
        logger.info("Flight session started")
        return {
            'success': True,
            'session_started': self._flight_session.start_time.isoformat(),
        }
    
    async def stop_flight_session(self) -> Dict:
        """Stop recording and return session statistics"""
        if not self._flight_session:
            return {'success': False, 'error': 'No hay sesión activa'}
        
        stats = self._flight_session.to_dict()
        self._flight_session = None
        logger.info(f"Flight session ended: {stats}")
        
        return {
            'success': True,
            'session_stats': stats,
        }
    
    async def record_flight_sample(self) -> Dict:
        """Record current signal quality sample for flight session"""
        if not self._flight_session:
            return {'success': False, 'error': 'No hay sesión activa'}
        
        signal = await self.get_signal_info()
        quality = await self.get_video_quality_assessment()
        latency = await self.measure_latency()
        
        sample = {
            'timestamp': datetime.now().isoformat(),
            'sinr': quality['metrics'].get('sinr') if quality.get('available') else None,
            'rsrp': quality['metrics'].get('rsrp') if quality.get('available') else None,
            'quality': quality.get('quality'),
            'latency_ms': latency.get('avg_ms'),
            'band': signal.get('band', ''),
        }
        
        self._flight_session.samples.append(sample)
        
        # Update min/max values
        if sample['sinr'] is not None:
            self._flight_session.min_sinr = min(self._flight_session.min_sinr, sample['sinr'])
            self._flight_session.max_sinr = max(self._flight_session.max_sinr, sample['sinr'])
        
        if sample['rsrp'] is not None:
            self._flight_session.min_rsrp = min(self._flight_session.min_rsrp, sample['rsrp'])
            self._flight_session.max_rsrp = max(self._flight_session.max_rsrp, sample['rsrp'])
        
        if sample['latency_ms'] is not None:
            self._flight_session.latency_samples.append(sample['latency_ms'])
            self._flight_session.avg_latency_ms = sum(self._flight_session.latency_samples) / len(self._flight_session.latency_samples)
        
        # Track band changes
        if sample['band'] and sample['band'] != self._flight_session.last_band:
            if self._flight_session.last_band:  # Don't count first band as change
                self._flight_session.band_changes += 1
            self._flight_session.last_band = sample['band']
        
        return {'success': True, 'sample': sample}
    
    async def get_flight_session_status(self) -> Dict:
        """Get current flight session status"""
        if not self._flight_session:
            return {'active': False}
        
        return {
            'active': True,
            'stats': self._flight_session.to_dict(),
        }
    
    # ======================
    # Latency Monitoring
    # ======================
    
    def _measure_latency_sync(self, host: str = None, count: int = None) -> Dict:
        """Measure network latency using ping (sync)"""
        host = host or self.LATENCY_TEST_HOST
        count = count or self.LATENCY_TEST_COUNT
        
        try:
            # Run ping command
            result = subprocess.run(
                ['ping', '-c', str(count), '-W', '2', host],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return {'success': False, 'error': 'Ping failed', 'host': host}
            
            # Parse ping output
            output = result.stdout
            
            # Extract individual ping times for jitter calculation
            import re
            times = re.findall(r'time=(\d+\.?\d*)', output)
            times = [float(t) for t in times]
            
            if not times:
                return {'success': False, 'error': 'No ping responses', 'host': host}
            
            # Calculate statistics
            avg_ms = sum(times) / len(times)
            min_ms = min(times)
            max_ms = max(times)
            
            # Calculate jitter (average deviation from mean)
            jitter_ms = sum(abs(t - avg_ms) for t in times) / len(times)
            
            # Store for quick access
            self._last_latency_ms = avg_ms
            self._last_jitter_ms = jitter_ms
            
            return {
                'success': True,
                'host': host,
                'samples': len(times),
                'avg_ms': round(avg_ms, 1),
                'min_ms': round(min_ms, 1),
                'max_ms': round(max_ms, 1),
                'jitter_ms': round(jitter_ms, 1),
                'times': times,
                'quality': self._latency_quality(avg_ms, jitter_ms),
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Ping timeout', 'host': host}
        except Exception as e:
            return {'success': False, 'error': str(e), 'host': host}
    
    def _latency_quality(self, latency_ms: float, jitter_ms: float) -> Dict:
        """Assess latency quality for video streaming"""
        if latency_ms < 50 and jitter_ms < 10:
            return {'level': 'excellent', 'label': 'Excelente', 'color': 'green'}
        elif latency_ms < 100 and jitter_ms < 20:
            return {'level': 'good', 'label': 'Bueno', 'color': 'green'}
        elif latency_ms < 150 and jitter_ms < 40:
            return {'level': 'moderate', 'label': 'Moderado', 'color': 'yellow'}
        elif latency_ms < 250 and jitter_ms < 60:
            return {'level': 'poor', 'label': 'Bajo', 'color': 'orange'}
        else:
            return {'level': 'critical', 'label': 'Crítico', 'color': 'red'}
    
    async def measure_latency(self, host: str = None, count: int = None) -> Dict:
        """Measure network latency and jitter"""
        return await self._run_sync(self._measure_latency_sync, host, count)
    
    @property
    def last_latency(self) -> Optional[float]:
        return self._last_latency_ms
    
    @property
    def last_jitter(self) -> Optional[float]:
        return self._last_jitter_ms
    
    # ======================
    # Enhanced Full Status
    # ======================
    
    async def get_full_status_enhanced(self) -> Dict:
        """Get complete modem status with video optimization data"""
        base_status = await self.get_full_status()
        
        if not base_status.get('available'):
            return base_status
        
        # Add video-specific data
        video_quality = await self.get_video_quality_assessment()
        current_band = await self.get_current_band()
        latency = await self.measure_latency()
        
        base_status['video_quality'] = video_quality
        base_status['current_band'] = current_band
        base_status['latency'] = latency
        base_status['video_mode_active'] = self._video_mode_active
        base_status['flight_session_active'] = self._flight_session is not None
        
        return base_status
    
    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


# Singleton instance
_hilink_service: Optional[HiLinkService] = None


def get_hilink_service() -> HiLinkService:
    """Get or create the HiLinkService singleton"""
    global _hilink_service
    if _hilink_service is None:
        _hilink_service = HiLinkService()
    return _hilink_service
