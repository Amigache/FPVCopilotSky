"""
Custom exception hierarchy for FPVCopilotSky

Provides typed exceptions for different domains (network, video, modem, VPN)
to enable precise error handling, diagnostics, and observability.

Each exception includes a category and context dict for structured logging.
"""

from typing import Optional, Dict, Any


class FPVCopilotException(Exception):
    """Base exception for all FPVCopilotSky errors"""

    def __init__(
        self,
        message: str,
        category: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.category = category
        self.context = context or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to structured dict for logging/API responses"""
        return {
            "error_type": self.__class__.__name__,
            "category": self.category,
            "error_message": self.message,
            "context": self.context,
        }


# ──────────────────────────────────────────────────────────────────────────
# Network Exceptions
# ──────────────────────────────────────────────────────────────────────────


class NetworkException(FPVCopilotException):
    """Base exception for network-related errors"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, category="network", context=context)


class InterfaceNotFoundError(NetworkException):
    """Network interface not found or not available"""

    def __init__(self, interface_name: str, reason: str = "not_found"):
        super().__init__(
            f"Network interface not found: {interface_name}",
            context={"interface": interface_name, "reason": reason},
        )


class RouteConfigurationError(NetworkException):
    """Error configuring or reading routing table"""

    def __init__(self, operation: str, details: str):
        super().__init__(
            f"Route configuration failed: {operation}",
            context={"operation": operation, "details": details},
        )


class NetworkCommandError(NetworkException):
    """Error executing network command (ip, tc, iptables, etc.)"""

    def __init__(
        self,
        command: str,
        returncode: int,
        stderr: str,
    ):
        super().__init__(
            f"Network command failed: {command}",
            context={
                "command": command,
                "returncode": returncode,
                "stderr": stderr,
            },
        )


class FailoverError(NetworkException):
    """Error during network failover operation"""

    def __init__(self, from_iface: str, to_iface: str, reason: str):
        super().__init__(
            f"Failover failed from {from_iface} to {to_iface}",
            context={
                "from_interface": from_iface,
                "to_interface": to_iface,
                "reason": reason,
            },
        )


# ──────────────────────────────────────────────────────────────────────────
# Video Exceptions
# ──────────────────────────────────────────────────────────────────────────


class VideoException(FPVCopilotException):
    """Base exception for video-related errors"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, category="video", context=context)


class VideoSourceError(VideoException):
    """Error accessing or configuring video source"""

    def __init__(self, source: str, reason: str):
        super().__init__(
            f"Video source error: {source}",
            context={"source": source, "reason": reason},
        )


class EncoderError(VideoException):
    """Error in video encoder configuration or execution"""

    def __init__(self, encoder: str, operation: str, details: str):
        super().__init__(
            f"Encoder error ({encoder}): {operation}",
            context={
                "encoder": encoder,
                "operation": operation,
                "details": details,
            },
        )


class GStreamerError(VideoException):
    """Error in GStreamer pipeline or runtime"""

    def __init__(self, operation: str, details: str):
        super().__init__(
            f"GStreamer error: {operation}",
            context={"operation": operation, "details": details},
        )


class StreamingConfigError(VideoException):
    """Error in streaming configuration"""

    def __init__(self, mode: str, parameter: str, value: Any):
        super().__init__(
            f"Invalid streaming config: {parameter}={value} for mode {mode}",
            context={
                "mode": mode,
                "parameter": parameter,
                "value": value,
            },
        )


# ──────────────────────────────────────────────────────────────────────────
# Modem Exceptions
# ──────────────────────────────────────────────────────────────────────────


class ModemException(FPVCopilotException):
    """Base exception for modem-related errors"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, category="modem", context=context)


class ModemConnectionError(ModemException):
    """Error connecting to or communicating with modem"""

    def __init__(self, modem_id: str, reason: str):
        super().__init__(
            f"Modem connection error: {modem_id}",
            context={"modem_id": modem_id, "reason": reason},
        )


class ModemCommandError(ModemException):
    """Error executing modem command"""

    def __init__(self, command: str, status_code: int, response: str):
        super().__init__(
            f"Modem command failed: {command} (status={status_code})",
            context={
                "command": command,
                "status_code": status_code,
                "response": response,
            },
        )


class ModemConfigError(ModemException):
    """Error in modem configuration or mode change"""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"Modem configuration error: {operation}",
            context={"operation": operation, "reason": reason},
        )


# ──────────────────────────────────────────────────────────────────────────
# VPN Exceptions
# ──────────────────────────────────────────────────────────────────────────


class VPNException(FPVCopilotException):
    """Base exception for VPN-related errors"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, category="vpn", context=context)


class VPNConnectionError(VPNException):
    """Error connecting to VPN service"""

    def __init__(self, vpn_type: str, reason: str):
        super().__init__(
            f"VPN connection error ({vpn_type}): {reason}",
            context={"vpn_type": vpn_type, "reason": reason},
        )


class VPNConfigError(VPNException):
    """Error in VPN configuration"""

    def __init__(self, vpn_type: str, setting: str, issue: str):
        super().__init__(
            f"VPN config error ({vpn_type}): {setting}",
            context={"vpn_type": vpn_type, "setting": setting, "issue": issue},
        )


class VPNAuthError(VPNException):
    """Error in VPN authentication or authorization"""

    def __init__(self, vpn_type: str, reason: str):
        super().__init__(
            f"VPN auth error ({vpn_type}): {reason}",
            context={"vpn_type": vpn_type, "reason": reason},
        )


# ──────────────────────────────────────────────────────────────────────────
# System/Telemetry Exceptions
# ──────────────────────────────────────────────────────────────────────────


class SystemException(FPVCopilotException):
    """Base exception for system-level errors"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, category="system", context=context)


class SerialPortError(SystemException):
    """Error accessing serial port or flight controller"""

    def __init__(self, port: str, reason: str):
        super().__init__(
            f"Serial port error: {port}",
            context={"port": port, "reason": reason},
        )


class MAVLinkError(SystemException):
    """Error in MAVLink communication or protocol"""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"MAVLink error: {operation}",
            context={"operation": operation, "reason": reason},
        )


class ProviderError(SystemException):
    """Error in provider initialization or operation"""

    def __init__(self, provider_type: str, provider_id: str, reason: str):
        super().__init__(
            f"Provider error: {provider_type}/{provider_id}",
            context={
                "provider_type": provider_type,
                "provider_id": provider_id,
                "reason": reason,
            },
        )


class ServiceInitError(SystemException):
    """Error during service initialization"""

    def __init__(self, service_name: str, reason: str):
        super().__init__(
            f"Service init error: {service_name}",
            context={"service_name": service_name, "reason": reason},
        )
