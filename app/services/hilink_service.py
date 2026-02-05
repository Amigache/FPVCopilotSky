"""
HiLink Modem Service
Uses huawei-lte-api to interact with Huawei HiLink modems
"""

import asyncio
from typing import Dict, Optional, Any
from functools import partial
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


class HiLinkService:
    """Service for Huawei HiLink modem API interaction"""
    
    MODEM_URL = "http://192.168.8.1/"
    CONNECTION_TIMEOUT = 5  # 5 seconds timeout for modem connection
    
    def __init__(self):
        self._connection: Optional[Connection] = None
        self._client: Optional[Client] = None
        self._last_error: Optional[str] = None
    
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
            
            # Map network type codes
            network_types = {
                '0': 'No Service',
                '1': 'GSM', '2': 'GPRS', '3': 'EDGE',
                '4': 'WCDMA', '5': 'HSDPA', '6': 'HSUPA', '7': 'HSPA+',
                '8': 'TD-SCDMA', '9': 'HSPA+',
                '19': 'LTE', '41': 'LTE',
                '101': '5G NR',
            }
            
            current_network = status.get('CurrentNetworkType', '0')
            network_type = network_types.get(current_network, f'Unknown ({current_network})')
            
            # Signal strength (0-5 bars)
            signal_icon = int(status.get('SignalIcon', 0))
            
            return {
                'operator': status.get('FullName', ''),
                'network_type': network_type,
                'current_network_type_ex': status.get('CurrentNetworkTypeEx', ''),
                'signal_strength': signal_icon,
                'signal_icon': signal_icon,
                'roaming': status.get('RoamingStatus', '0') == '1',
                'sim_status': status.get('SimStatus', ''),
                'connection_status': status.get('ConnectionStatus', ''),
                'primary_dns': status.get('PrimaryDns', ''),
                'secondary_dns': status.get('SecondaryDns', ''),
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
        if not self._ensure_connected():
            return False
        
        try:
            # Get current settings to preserve band settings
            current = self._client.net.net_mode()
            
            self._client.net.set_net_mode(
                mode,
                current.get('NetworkBand', '3FFFFFFF'),
                current.get('LTEBand', '7FFFFFFFFFFFFFFF')
            )
            return True
        except Exception as e:
            self._last_error = str(e)
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
