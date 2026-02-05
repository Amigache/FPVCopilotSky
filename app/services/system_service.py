"""
System Service
Manages system-level operations
"""

import glob
import os
import platform
from typing import List, Dict

class SystemService:
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
