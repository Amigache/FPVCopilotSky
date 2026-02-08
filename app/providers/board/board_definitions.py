"""
Board definitions: enums and data structures for feature descriptions
"""

from enum import Enum
from dataclasses import dataclass
from typing import List


class StorageType(Enum):
    """Where system is running from"""

    EMMC = "eMMC"
    SD_CARD = "SD Card"
    NVME = "NVMe"
    USB = "USB"


class DistroFamily(Enum):
    """Linux distribution family"""

    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    ARMBIAN = "armbian"
    ALPINE = "alpine"
    CUSTOM = "custom"


class CPUArch(Enum):
    """CPU architecture"""

    ARMV7 = "armv7l"
    ARMV8 = "aarch64"
    X86_64 = "x86_64"
    RISCV64 = "riscv64"


class VideoSourceFeature(Enum):
    """Video source capabilities"""

    V4L2 = "v4l2"
    LIBCAMERA = "libcamera"
    HDMI_IN = "hdmi_in"
    NETWORK_STREAM = "network_stream"


class VideoEncoderFeature(Enum):
    """Video encoder capabilities"""

    HARDWARE_H264 = "hardware_h264"
    MJPEG = "mjpeg"
    X264_SOFTWARE = "x264"
    OPENH264_SOFTWARE = "openh264"


class ConnectivityFeature(Enum):
    """Connectivity options"""

    WIFI = "wifi"
    ETHERNET = "ethernet"
    USB_MODEM = "usb_modem"
    USB_3 = "usb3"


class SystemFeature(Enum):
    """System capabilities"""

    GPIO = "gpio"
    SPI = "spi"
    I2C = "i2c"
    UART = "uart"
    CAN = "can"


@dataclass
class HardwareInfo:
    """Hardware specifications"""

    cpu_model: str  # e.g., "Amlogic S905Y2"
    cpu_cores: int  # Number of CPU cores
    cpu_arch: CPUArch  # Architecture
    ram_gb: int  # RAM in GB
    storage_gb: int  # Primary storage in GB
    has_gpu: bool  # GPU present
    gpu_model: str = None  # e.g., "Mali-G31", None if no GPU


@dataclass
class VariantInfo:
    """Board variant configuration"""

    name: str  # e.g., "eMMC Storage"
    storage_type: StorageType  # Where system runs from
    distro_family: DistroFamily  # Linux distro
    distro_version: str  # Version (e.g., "25.11.2")
    kernel_version: str  # Kernel (e.g., "6.12.58-current-meson64")
    is_default: bool = False  # Default variant for detection
    video_sources: List[VideoSourceFeature] = None
    video_encoders: List[VideoEncoderFeature] = None
    connectivity: List[ConnectivityFeature] = None
    system_features: List[SystemFeature] = None

    def __post_init__(self):
        if self.video_sources is None:
            self.video_sources = []
        if self.video_encoders is None:
            self.video_encoders = []
        if self.connectivity is None:
            self.connectivity = []
        if self.system_features is None:
            self.system_features = []


@dataclass
class DetectionCriteria:
    """How to detect a board in runtime"""

    cpu_model_contains: str = None  # Check /proc/cpuinfo
    device_tree_contains: str = None  # Check /proc/device-tree/model
    dmesg_contains: str = None  # Check kernel logs
    distro_name: str = None  # Check /etc/os-release
    check_files: List[str] = None  # Files that should exist
