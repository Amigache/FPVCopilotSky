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

from providers.base import ModemProvider, ModemStatus, ModemInfo, NetworkInfo

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

# APN Configuration
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

# Video Quality Thresholds (based on SINR)
VIDEO_QUALITY_THRESHOLDS = {
    'excellent': {'sinr_min': 15, 'max_bitrate_kbps': 8000, 'label': 'Excelente', 'color': 'green'},
    'good':      {'sinr_min': 10, 'max_bitrate_kbps': 5000, 'label': 'Bueno', 'color': 'green'},
    'moderate':  {'sinr_min': 5,  'max_bitrate_kbps': 3000, 'label': 'Moderado', 'color': 'yellow'},
    'poor':      {'sinr_min': 0,  'max_bitrate_kbps': 1500, 'label': 'Bajo', 'color': 'orange'},
    'critical':  {'sinr_min': -5, 'max_bitrate_kbps': 800,  'label': 'Crítico', 'color': 'red'},
}

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
        self._video_mode_active: bool = False
        self._original_settings: Dict = {}
        
        # Latency monitoring
        self._last_latency_ms: Optional[float] = None
        self._last_jitter_ms: Optional[float] = None
        
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
            model = info.get('DeviceName', '').lower()
            return 'e3372' in model or 'hilink' in model
        except:
            return False
    
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
    
    def _get_session_token(self) -> Tuple[Optional[requests.Session], Optional[str]]:
        """Get a session with valid token for API calls"""
        try:
            session = requests.Session()
            session.get(self.MODEM_URL, timeout=self.CONNECTION_TIMEOUT)
            
            r = session.get(f'{self.MODEM_URL}api/webserver/SesTokInfo', timeout=self.CONNECTION_TIMEOUT)
            root = ET.fromstring(r.text)
            sesinfo = root.find('SesInfo').text
            token = root.find('TokInfo').text
            
            session.cookies.set('SessionID', sesinfo.replace('SessionID=', ''))
            return session, token
        except Exception as e:
            logger.error(f"Failed to get session token: {e}")
            return None, None
    
    def _direct_api_post(self, endpoint: str, xml_data: str, timeout: int = None) -> Tuple[bool, str]:
        """Make a direct POST request to the modem API"""
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
    
    # ======================
    # ModemProvider Interface Implementation
    # ======================
    
    def get_status(self) -> Dict:
        """Get modem status (sync version for provider interface)"""
        if not HILINK_AVAILABLE:
            return {
                'available': False,
                'status': ModemStatus.UNAVAILABLE,
                'modem_info': None,
                'network_info': None,
                'error': 'huawei-lte-api not installed'
            }
        
        try:
            modem_info = self.get_modem_info()
            network_info = self.get_network_info()
            
            if not modem_info:
                return {
                    'available': False,
                    'status': ModemStatus.ERROR,
                    'modem_info': None,
                    'network_info': None,
                    'error': self._last_error or 'Could not connect to modem'
                }
            
            status = ModemStatus.CONNECTED if network_info and network_info.status == ModemStatus.CONNECTED else ModemStatus.DISCONNECTED
            
            return {
                'available': True,
                'status': status,
                'modem_info': modem_info,
                'network_info': network_info,
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'status': ModemStatus.ERROR,
                'modem_info': None,
                'network_info': None,
                'error': str(e)
            }
    
    def connect(self) -> Dict:
        """Activate modem connection"""
        # HiLink modems are auto-connect, this would trigger reconnection
        try:
            success = self._reconnect_network_sync()
            return {
                'success': success,
                'message': 'Conexión iniciada' if success else self._last_error,
                'network_info': self.get_network_info() if success else None
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'network_info': None}
    
    def disconnect(self) -> Dict:
        """Deactivate modem connection"""
        # HiLink modems typically stay connected, this would require airplane mode
        return {'success': False, 'message': 'Desconexión manual no soportada en HiLink mode'}
    
    def get_modem_info(self) -> Optional[ModemInfo]:
        """Get modem hardware information"""
        device = self._get_device_info_sync()
        if not device:
            return None
        
        return ModemInfo(
            name=device.get('device_name', 'Huawei E3372h'),
            model=device.get('device_name', 'E3372h-153'),
            imei=device.get('imei', ''),
            imsi=device.get('imsi', ''),
            manufacturer='Huawei'
        )
    
    def get_network_info(self) -> Optional[NetworkInfo]:
        """Get network connection information"""
        signal = self._get_signal_info_sync()
        network = self._get_network_info_sync()
        traffic = self._get_traffic_stats_sync()
        
        if not signal or not network:
            return None
        
        # Determine status
        conn_code = network.get('connection_status_code', '')
        status = ModemStatus.CONNECTED if conn_code == '901' else ModemStatus.DISCONNECTED
        
        # Signal strength
        signal_percent = signal.get('signal_percent', 0)
        
        return NetworkInfo(
            status=status,
            signal_strength=signal_percent,
            network_type=network.get('network_type_ex', network.get('network_type', '')),
            operator=network.get('operator', ''),
            ip_address=network.get('primary_dns', None),  # Approximation
            dns_servers=[network.get('primary_dns', ''), network.get('secondary_dns', '')],
            data_uploaded=traffic.get('current_upload_raw', 0),
            data_downloaded=traffic.get('current_download_raw', 0)
        )
    
    def configure_band(self, band_mask: int) -> Dict:
        """Configure LTE band preference"""
        try:
            success = self._set_lte_band_sync(band_mask)
            return {
                'success': success,
                'message': f'Banda configurada: {hex(band_mask)}' if success else self._last_error
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def reboot(self) -> Dict:
        """Reboot the modem"""
        try:
            success = self._reboot_sync()
            return {
                'success': success,
                'message': 'Módem reiniciando...' if success else self._last_error
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
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
            
            rssi_str = signal.get('rssi', '')
            signal_percent = None
            if rssi_str:
                try:
                    rssi = int(rssi_str.replace('dBm', '').strip())
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
            status = self._client.monitoring.status()
            
            network_types = {
                '0': 'No Service',
                '1': 'GSM', '2': 'GPRS', '3': 'EDGE',
                '4': 'WCDMA', '5': 'HSDPA', '6': 'HSUPA', '7': 'HSPA+',
                '8': 'TD-SCDMA', '9': 'HSPA+',
                '19': 'LTE', '41': 'LTE',
                '101': '5G NR',
            }
            
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
            
            signal_icon = int(status.get('SignalIcon', 0))
            
            operator_name = ''
            operator_code = ''
            rat = ''
            try:
                plmn = self._client.net.current_plmn()
                operator_name = plmn.get('FullName', '') or plmn.get('ShortName', '')
                operator_code = plmn.get('Numeric', '')
                rat_code = plmn.get('Rat', '')
                rat_types = {'0': 'GSM', '2': 'WCDMA', '7': 'LTE', '12': '5G NR'}
                rat = rat_types.get(str(rat_code), '')
            except:
                operator_name = status.get('FullName', '')
            
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
                'operator_code': operator_code,
                'network_type': network_type,
                'network_type_ex': network_type_ex or network_type,
                'current_network_type_ex': current_network_ex,
                'rat': rat,
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
    
    def _reconnect_network_sync(self) -> bool:
        """Force network reconnection"""
        try:
            xml_data = '''<?xml version="1.0" encoding="UTF-8"?>
<request>
<Mode>0</Mode>
<Plmn></Plmn>
<Rat></Rat>
</request>'''
            
            success, msg = self._direct_api_post('api/net/register', xml_data)
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
            lte_band_hex = format(band_mask, 'X')
            
            if self._ensure_connected():
                current = self._client.net.net_mode()
                network_band = current.get('NetworkBand', '3FFFFFFF')
            else:
                network_band = '3FFFFFFF'
            
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
            return {
                'available': False,
                'error': 'huawei-lte-api not installed'
            }
        
        try:
            device = await self._run_sync(self._get_device_info_sync)
            if not device:
                return {
                    'available': False,
                    'error': self._last_error or 'Could not connect to modem'
                }
            
            signal = await self._run_sync(self._get_signal_info_sync)
            network = await self._run_sync(self._get_network_info_sync)
            traffic = await self._run_sync(self._get_traffic_stats_sync)
            
            return {
                'available': True,
                'device': device,
                'signal': signal,
                'network': network,
                'traffic': traffic,
            }
        except Exception as e:
            return {
                'available': False,
                'error': str(e)
            }
    
    def get_band_presets(self) -> Dict:
        """Get available band presets"""
        return {
            'presets': LTE_BAND_PRESETS,
            'individual_bands': LTE_BANDS,
        }
    
    def get_info(self) -> Dict:
        """Get provider information"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': 'Huawei E3372h-153 HiLink modem with video streaming optimization',
            'features': [
                'LTE Cat 4 (150 Mbps down, 50 Mbps up)',
                'Band optimization (B1, B3, B7, B8, B20)',
                'Video quality assessment',
                'Flight session tracking',
                'Latency monitoring'
            ],
            'modes': ['HiLink (Router mode)'],
        }
