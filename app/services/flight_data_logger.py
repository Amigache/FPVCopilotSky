"""
Flight Data Logger Service

Combines telemetry data from MAVLink with modem signal data
and writes it to CSV files for flight analysis.
"""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class FlightDataLogger:
    """Logs flight data (telemetry + signal) to CSV files"""

    CSV_HEADERS = [
        # Timestamp
        "timestamp",
        # GPS Position
        "latitude",
        "longitude",
        "altitude_msl",
        # Speed
        "ground_speed_ms",
        "air_speed_ms",
        "climb_rate_ms",
        # System Status
        "armed",
        "flight_mode",
        "vehicle_type",
        # Modem Signal Quality
        "rssi",
        "rsrp_dbm",
        "rsrq_db",
        "sinr_db",
        # Network Info
        "cell_id",
        "pci",
        "band",
        "network_type",
        "operator",
        "latency_ms",
    ]

    def __init__(self, mavlink_service, log_directory: str = ""):
        """
        Initialize flight data logger.

        Args:
            mavlink_service: MAVLinkBridge instance for telemetry data
            log_directory: Custom log directory path. If empty, uses ~/flight-records
        """
        self.mavlink_service = mavlink_service
        self.log_directory = (
            Path(log_directory) if log_directory else Path.home() / "flight-records"
        )
        self.csv_file = None
        self.csv_writer = None
        self.file_path = None
        self.session_active = False

    def start_session(self) -> Dict[str, Any]:
        """
        Start a new flight session and create CSV file.

        Returns:
            Dict with success status and file path
        """
        if self.session_active:
            return {
                "success": False,
                "message": "Session already active",
                "file_path": str(self.file_path) if self.file_path else None,
            }

        try:
            # Create log directory if it doesn't exist
            self.log_directory.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"flight-{timestamp}.csv"
            self.file_path = self.log_directory / filename

            # Open CSV file and write headers
            self.csv_file = open(self.file_path, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=self.CSV_HEADERS)
            self.csv_writer.writeheader()
            self.csv_file.flush()  # Ensure headers are written immediately

            self.session_active = True
            logger.info(f"Flight data logging started: {self.file_path}")

            return {
                "success": True,
                "message": "Flight data logging started",
                "file_path": str(self.file_path),
            }

        except Exception as e:
            logger.error(f"Error starting flight data logger: {e}")
            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None
            return {
                "success": False,
                "message": f"Error starting logger: {str(e)}",
            }

    def log_sample(self, modem_sample: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log a combined telemetry + signal sample to CSV.

        Args:
            modem_sample: Sample data from modem provider (signal quality, network info)

        Returns:
            Dict with success status
        """
        if not self.session_active or not self.csv_writer:
            return {"success": False, "message": "No active session"}

        try:
            # Get current telemetry data
            telemetry = self.mavlink_service.get_telemetry()

            # Build CSV row combining telemetry and modem data
            row = {
                # Timestamp from modem sample
                "timestamp": modem_sample.get("timestamp", datetime.now().isoformat()),
                # GPS Position
                "latitude": telemetry.get("gps", {}).get("lat", 0),
                "longitude": telemetry.get("gps", {}).get("lon", 0),
                "altitude_msl": telemetry.get("gps", {}).get("alt", 0),
                # Speed
                "ground_speed_ms": telemetry.get("speed", {}).get("ground_speed", 0),
                "air_speed_ms": telemetry.get("speed", {}).get("air_speed", 0),
                "climb_rate_ms": telemetry.get("speed", {}).get("climb_rate", 0),
                # System Status
                "armed": telemetry.get("system", {}).get("armed", False),
                "flight_mode": telemetry.get("system", {}).get("mode", "UNKNOWN"),
                "vehicle_type": telemetry.get("system", {}).get(
                    "vehicle_type", "UNKNOWN"
                ),
                # Modem Signal Quality
                "rssi": modem_sample.get("rssi", ""),
                "rsrp_dbm": modem_sample.get("rsrp", ""),
                "rsrq_db": modem_sample.get("rsrq", ""),
                "sinr_db": modem_sample.get("sinr", ""),
                # Network Info
                "cell_id": modem_sample.get("cell_id", ""),
                "pci": modem_sample.get("pci", ""),
                "band": modem_sample.get("band", ""),
                "network_type": modem_sample.get("network_type", ""),
                "operator": modem_sample.get("operator", ""),
                "latency_ms": modem_sample.get("latency_ms", ""),
            }

            # Write row to CSV
            self.csv_writer.writerow(row)
            self.csv_file.flush()  # Ensure data is written immediately

            return {"success": True, "file_path": str(self.file_path)}

        except Exception as e:
            logger.error(f"Error logging flight sample: {e}")
            return {"success": False, "message": str(e)}

    def stop_session(self) -> Dict[str, Any]:
        """
        Stop the flight session and close CSV file.

        Returns:
            Dict with success status and final file path
        """
        if not self.session_active:
            return {"success": False, "message": "No active session"}

        try:
            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None

            final_path = str(self.file_path) if self.file_path else None
            self.csv_writer = None
            self.file_path = None
            self.session_active = False

            logger.info(f"Flight data logging stopped: {final_path}")

            return {
                "success": True,
                "message": "Flight data logging stopped",
                "file_path": final_path,
            }

        except Exception as e:
            logger.error(f"Error stopping flight data logger: {e}")
            return {"success": False, "message": str(e)}

    def is_active(self) -> bool:
        """Check if a logging session is active"""
        return self.session_active

    def get_status(self) -> Dict[str, Any]:
        """Get current logger status"""
        return {
            "active": self.session_active,
            "file_path": str(self.file_path) if self.file_path else None,
            "log_directory": str(self.log_directory),
        }
