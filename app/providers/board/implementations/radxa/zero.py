"""
Radxa Zero board provider

Hardware: Amlogic S905Y2 CPU, 4GB RAM, 32GB eMMC, WiFi 5 (or 4)
Supported Storage: eMMC, SD Card, USB
Distros: Armbian, Ubuntu, Debian
"""

import os
import logging
import subprocess
from typing import Optional, List
from ...board_provider import BoardProvider
from ...board_definitions import (
    HardwareInfo,
    VariantInfo,
    DetectionCriteria,
    StorageType,
    DistroFamily,
    CPUArch,
    VideoSourceFeature,
    VideoEncoderFeature,
    ConnectivityFeature,
    SystemFeature,
)

logger = logging.getLogger(__name__)


class RadxaZeroProvider(BoardProvider):
    """
    Radxa Zero - ARM SBC with Amlogic S905Y2
    https://wiki.radxa.com/Zero

    Auto-detects at runtime:
    - CPU cores from /proc/cpuinfo
    - RAM from /proc/meminfo
    - Storage capacity from df
    - Kernel version from uname

    Variants managed:
    - Storage: eMMC (internal), SD Card (external), USB (external)
    - Distro: Armbian (primary), Ubuntu, Debian
    """

    @property
    def board_name(self) -> str:
        return "Radxa Zero"

    @property
    def board_identifier(self) -> str:
        return "radxa_zero"

    def get_detection_criteria(self) -> DetectionCriteria:
        """Detect Radxa Zero by device tree model or CPU"""
        return DetectionCriteria(
            cpu_model_contains="Amlogic",
            device_tree_contains="Radxa Zero",
            check_files=[],  # Don't require device tree files
        )

    def _check_detection_criteria(self, criteria: DetectionCriteria) -> bool:
        """
        Custom detection for Radxa Zero.
        Check device tree first (more reliable), then cpuinfo.
        """
        # Priority 1: Check device tree model
        try:
            with open("/proc/device-tree/model", "r") as f:
                model = f.read().strip()
                if (
                    criteria.device_tree_contains
                    and criteria.device_tree_contains in model
                ):
                    logger.info(f"Detected Radxa Zero via device tree: {model}")
                    return True
        except Exception as e:
            logger.debug(f"Device tree check failed: {e}")

        # Priority 2: Check cpuinfo for Amlogic
        try:
            if criteria.cpu_model_contains:
                with open("/proc/cpuinfo", "r") as f:
                    content = f.read()
                    if criteria.cpu_model_contains in content:
                        logger.info("Detected Radxa Zero via cpuinfo (Amlogic CPU)")
                        return True
        except Exception as e:
            logger.debug(f"cpuinfo check failed: {e}")

        return False

    def get_variants(self) -> List[VariantInfo]:
        """
        Define supported variants for Radxa Zero.

        Mainline kernel only (no legacy kernel support).
        """
        variants = []

        # Armbian mainline kernel (recommended)
        armbian_current = VariantInfo(
            name="Armbian mainline kernel",
            storage_type=StorageType.EMMC,
            distro_family=DistroFamily.ARMBIAN,
            distro_version="25.11.2",
            kernel_version="6.12.58-current-meson64",
            is_default=True,
            # Video capabilities (mainline kernel - no HW H.264)
            video_sources=[
                VideoSourceFeature.V4L2,
                VideoSourceFeature.LIBCAMERA,
            ],
            video_encoders=[
                VideoEncoderFeature.MJPEG,
                VideoEncoderFeature.X264_SOFTWARE,
            ],
            # Network
            connectivity=[
                ConnectivityFeature.WIFI,
                ConnectivityFeature.ETHERNET,
                ConnectivityFeature.USB_MODEM,
                ConnectivityFeature.USB_3,
            ],
            # GPIO/peripherals
            system_features=[
                SystemFeature.GPIO,
                SystemFeature.I2C,
                SystemFeature.SPI,
            ],
        )
        variants.append(armbian_current)

        return variants

    def detect_running_variant(self) -> Optional[VariantInfo]:
        """
        Detect which variant is currently running.

        Detects distro + kernel version and fills in runtime values.
        """
        try:
            distro_info = self._read_os_release()
            if not distro_info:
                logger.warning("Cannot read /etc/os-release")
                return None

            distro_name = distro_info.get("name", "").lower()
            distro_version = distro_info.get("version_id", "")

            storage_type = self._detect_storage_type()
            kernel_version = self._get_kernel_version()

            # Match Radxa Zero - Armbian es la distro principal
            if "armbian" in distro_name:
                logger.info(f"Detected Armbian Radxa Zero kernel: {kernel_version}")

                # Use default mainline variant
                variant = self.get_variants()[0]

                # Actualiza valores detectados en runtime
                variant.storage_type = storage_type
                variant.kernel_version = kernel_version
                variant.distro_version = distro_version

                return variant

            # Fallback: Acepta cualquier distro basada en Debian
            # (Ubuntu, Debian, etc.) si es Radxa Zero
            if any(deb in distro_name for deb in ["ubuntu", "debian", "raspberry"]):
                variants = self.get_variants()
                variant = variants[0]  # Usa default (current)
                variant.storage_type = storage_type
                variant.kernel_version = kernel_version
                variant.distro_family = (
                    DistroFamily.DEBIAN
                    if "debian" in distro_name
                    else DistroFamily.UBUNTU
                )
                variant.distro_version = distro_version
                variant.name = f"{distro_name.capitalize()} {distro_version}"
                logger.info(f"Detected Radxa Zero ({distro_name} {distro_version})")
                return variant

            # Last resort: usa variante default con specs detectados
            logger.warning(
                f"Unknown distro on Radxa Zero: {distro_name} {distro_version}, "
                "using default variant"
            )
            variants = self.get_variants()
            variant = variants[0]
            variant.storage_type = storage_type
            variant.kernel_version = kernel_version
            return variant

        except Exception as e:
            logger.error(f"Error detecting Radxa Zero variant: {e}")
            return None

    def _get_hardware_info(self) -> HardwareInfo:
        """Return hardware specs - auto-detects RAM and storage at runtime"""
        return HardwareInfo(
            cpu_model="Amlogic S905Y2",
            cpu_cores=self._detect_cpu_cores(),
            cpu_arch=CPUArch.ARMV8,
            ram_gb=self._detect_ram_gb(),
            storage_gb=self._detect_storage_gb(),
            has_gpu=True,
            gpu_model="Mali-G31 MP2",
        )

    def _get_cpu_model(self) -> str:
        return "Amlogic S905Y2"

    @staticmethod
    def _detect_cpu_cores() -> int:
        """Detect CPU cores"""
        try:
            cores = os.cpu_count()
            if cores:
                return cores
        except Exception as e:
            logger.warning(f"Error detecting CPU cores: {e}")
        return 4

    @staticmethod
    def _detect_ram_gb() -> int:
        """Detect RAM from /proc/meminfo"""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        gb = kb / (1024 * 1024)
                        return int(round(gb))
        except Exception as e:
            logger.warning(f"Error detecting RAM: {e}")
        return 4

    @staticmethod
    def _detect_storage_gb() -> int:
        """Detect root storage capacity from df"""
        try:
            output = subprocess.check_output(["df", "/"], text=True)
            lines = output.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                kb = int(parts[1])
                gb = kb / (1024 * 1024)
                return int(round(gb))
        except Exception as e:
            logger.warning(f"Error detecting storage: {e}")
        return 32

    @staticmethod
    def _read_os_release() -> dict:
        """Parse /etc/os-release"""
        os_release_path = "/etc/os-release"
        if not os.path.exists(os_release_path):
            return {}

        info = {}
        try:
            with open(os_release_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, value = line.split("=", 1)
                        value = value.strip('"').strip("'")
                        info[key.lower()] = value
        except Exception as e:
            logger.error(f"Error reading {os_release_path}: {e}")

        return info

    @staticmethod
    def _get_kernel_version() -> str:
        """Get kernel version from uname"""
        try:
            output = subprocess.check_output(["uname", "-r"], text=True)
            return output.strip()
        except Exception as e:
            logger.warning(f"Error getting kernel version: {e}")
            return "unknown"

    @staticmethod
    def _detect_storage_type() -> StorageType:
        """Detect root storage type"""
        try:
            output = subprocess.check_output(["df", "/"], text=True)

            for line in output.split("\n")[1:]:
                if line.startswith("/dev/"):
                    device = line.split()[0]

                    if "mmcblk" in device:
                        return StorageType.EMMC
                    elif "sd" in device:
                        return StorageType.SD_CARD
                    elif "nvme" in device:
                        return StorageType.NVME
                    elif "sda" in device or "sdb" in device:
                        return StorageType.USB

            return StorageType.EMMC

        except Exception as e:
            logger.warning(f"Error detecting storage type: {e}")
            return StorageType.EMMC
