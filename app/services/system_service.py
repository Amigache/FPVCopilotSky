"""
System Service
Manages system-level operations
"""

import glob
import os
import platform
import subprocess
from typing import List, Dict

class SystemService:
    # Services to monitor
    MONITORED_SERVICES = ['fpvcopilot-sky', 'nginx']
    
    @staticmethod
    def get_services_status() -> List[Dict[str, any]]:
        """
        Get status of monitored systemd services
        
        Returns:
            List of dictionaries with service status information
        """
        services = []
        
        for service_name in SystemService.MONITORED_SERVICES:
            service_info = {
                "name": service_name,
                "active": False,
                "status": "unknown",
                "description": "",
                "memory": None,
                "uptime": None
            }
            
            try:
                # Check if service is active
                result = subprocess.run(
                    ['systemctl', 'is-active', service_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                service_info["active"] = result.returncode == 0
                service_info["status"] = result.stdout.strip()
                
                # Get service description and memory if active
                if service_info["active"]:
                    # Get service properties
                    show_result = subprocess.run(
                        ['systemctl', 'show', service_name, 
                         '--property=Description,MemoryCurrent,ActiveEnterTimestamp'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if show_result.returncode == 0:
                        for line in show_result.stdout.strip().split('\n'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                if key == 'Description':
                                    service_info["description"] = value
                                elif key == 'MemoryCurrent':
                                    try:
                                        mem_bytes = int(value)
                                        service_info["memory"] = f"{mem_bytes // (1024*1024)} MB"
                                    except:
                                        pass
                                elif key == 'ActiveEnterTimestamp':
                                    service_info["uptime"] = value
                                    
            except subprocess.TimeoutExpired:
                service_info["status"] = "timeout"
            except Exception as e:
                service_info["status"] = f"error: {str(e)}"
            
            services.append(service_info)
        
        return services
    
    @staticmethod
    def get_available_serial_ports() -> List[Dict[str, str]]:
        """
        Get list of available serial ports
        
        Returns:
            List of dictionaries with port information
        """
        ports = []
        
        # Check common serial port patterns (Linux)
        patterns = [
            '/dev/ttyAML*',      # Amlogic UART (Radxa, etc)
            '/dev/ttyUSB*',      # USB serial adapters
            '/dev/ttyACM*',      # USB CDC ACM devices
            '/dev/ttyS*',        # Standard serial ports
            '/dev/ttyAMA*',      # ARM serial ports (Raspberry Pi, etc)
            '/dev/serial/by-id/*'  # Persistent USB names
        ]
        
        for pattern in patterns:
            for port_path in sorted(glob.glob(pattern)):
                # Check if port exists and is accessible
                if os.path.exists(port_path):
                    try:
                        port_info = {
                            "path": port_path,
                            "name": os.path.basename(port_path)
                        }
                        ports.append(port_info)
                    except Exception as e:
                        print(f"⚠️ Error checking port {port_path}: {e}")
        
        # Remove duplicates (in case of symlinks)
        seen = set()
        unique_ports = []
        for port in ports:
            if port["path"] not in seen:
                seen.add(port["path"])
                unique_ports.append(port)
        
        return unique_ports
    
    @staticmethod
    def get_system_info() -> Dict[str, str]:
        """
        Get system information
        
        Returns:
            Dictionary with system information
        """
        try:
            # Try to read device model
            device_model = "Unknown"
            model_files = [
                '/proc/device-tree/model',
                '/sys/firmware/devicetree/base/model'
            ]
            
            for model_file in model_files:
                if os.path.exists(model_file):
                    try:
                        with open(model_file, 'r') as f:
                            device_model = f.read().strip().replace('\x00', '')
                            break
                    except:
                        pass
            
            return {
                "platform": platform.system(),
                "machine": platform.machine(),
                "device": device_model,
                "python_version": platform.python_version()
            }
        except Exception as e:
            print(f"⚠️ Error getting system info: {e}")
            return {
                "platform": "Unknown",
                "machine": "Unknown",
                "device": "Unknown",
                "python_version": platform.python_version()
            }
