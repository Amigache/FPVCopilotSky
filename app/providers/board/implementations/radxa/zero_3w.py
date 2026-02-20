"""
Radxa Zero 3W board provider

Hardware: Rockchip RK3566 CPU, up to 8GB RAM, eMMC/SD storage, WiFi 5
Supported Storage: eMMC, SD Card
Distros: Ubuntu, Armbian, Debian
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


class RadxaZero3WProvider(BoardProvider):
    """
    Radxa Zero 3W - ARM SBC with Rockchip RK3566
    https://wiki.radxa.com/Zero3

    Auto-detects at runtime:
    - CPU cores from os.cpu_count()
    - RAM from /proc/meminfo
    - Storage capacity from df
    - Kernel version from uname

    Variants managed:
    - Storage: eMMC (internal), SD Card (external)
    - Distro: Ubuntu (primary), Armbian, Debian
    """

    @property
    def board_name(self) -> str:
        return "Radxa Zero 3W"

    @property
    def board_identifier(self) -> str:
        return "radxa_zero_3w"

    def get_detection_criteria(self) -> DetectionCriteria:
        """Detect Radxa Zero 3W by device tree model"""
        return DetectionCriteria(
            cpu_model_contains="Rockchip",
            device_tree_contains="Radxa ZERO 3",
            check_files=[],
        )

    def _check_detection_criteria(self, criteria: DetectionCriteria) -> bool:
        """
        Custom detection for Radxa Zero 3W.
        Check device tree first (more reliable), then cpuinfo.
        """
        # Priority 1: Check device tree model
        try:
            with open("/proc/device-tree/model", "rb") as f:
                # Read as bytes and decode, stripping null bytes
                model = f.read().decode("utf-8", errors="ignore").rstrip("\x00").strip()
                if "Radxa ZERO 3" in model:
                    logger.info(f"Detected Radxa Zero 3W via device tree: {model}")
                    return True
        except Exception as e:
            logger.debug(f"Device tree check failed: {e}")

        # Priority 2: Check cpuinfo for Rockchip RK3566
        try:
            with open("/proc/cpuinfo", "r") as f:
                content = f.read()
                if "Rockchip" in content or "rk3566" in content.lower():
                    logger.info("Detected Radxa Zero 3W via cpuinfo (Rockchip RK3566)")
                    return True
        except Exception as e:
            logger.debug(f"cpuinfo check failed: {e}")

        return False

    def get_variants(self) -> List[VariantInfo]:
        """Define supported variants for Radxa Zero 3W."""
        variants = []

        # Ubuntu (default — shipped by Radxa)
        ubuntu_default = VariantInfo(
            name="Ubuntu 24.04 (Radxa official)",
            storage_type=StorageType.EMMC,
            distro_family=DistroFamily.UBUNTU,
            distro_version="24.04",
            kernel_version="5.10.0",
            is_default=True,
            video_sources=[
                VideoSourceFeature.V4L2,
                VideoSourceFeature.LIBCAMERA,
            ],
            video_encoders=[
                VideoEncoderFeature.HARDWARE_H264,
                VideoEncoderFeature.MJPEG,
                VideoEncoderFeature.X264_SOFTWARE,
            ],
            connectivity=[
                ConnectivityFeature.WIFI,
                ConnectivityFeature.ETHERNET,
                ConnectivityFeature.USB_MODEM,
                ConnectivityFeature.USB_3,
            ],
            system_features=[
                SystemFeature.GPIO,
                SystemFeature.I2C,
                SystemFeature.SPI,
            ],
        )
        variants.append(ubuntu_default)

        return variants

    def detect_running_variant(self) -> Optional[VariantInfo]:
        """
        Detect which variant is currently running.
        Reads /etc/os-release to determine distro + version.
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

            variant = self.get_variants()[0]
            variant.storage_type = storage_type
            variant.kernel_version = kernel_version
            variant.distro_version = distro_version

            if "ubuntu" in distro_name:
                variant.distro_family = DistroFamily.UBUNTU
                variant.name = f"Ubuntu {distro_version}"
                logger.info(f"Detected Radxa Zero 3W on Ubuntu {distro_version}, kernel {kernel_version}")
            elif "armbian" in distro_name:
                variant.distro_family = DistroFamily.ARMBIAN
                variant.name = f"Armbian {distro_version}"
                logger.info(f"Detected Radxa Zero 3W on Armbian {distro_version}, kernel {kernel_version}")
            elif "debian" in distro_name:
                variant.distro_family = DistroFamily.DEBIAN
                variant.name = f"Debian {distro_version}"
                logger.info(f"Detected Radxa Zero 3W on Debian {distro_version}, kernel {kernel_version}")
            else:
                logger.warning(
                    f"Unknown distro on Radxa Zero 3W: {distro_name} {distro_version}, using default variant"
                )

            return variant

        except Exception as e:
            logger.error(f"Error detecting Radxa Zero 3W variant: {e}")
            return None

    def _get_hardware_info(self) -> HardwareInfo:
        """Return hardware specs — auto-detects RAM and storage at runtime"""
        return HardwareInfo(
            cpu_model="Rockchip RK3566",
            cpu_cores=self._detect_cpu_cores(),
            cpu_arch=CPUArch.ARMV8,
            ram_gb=self._detect_ram_gb(),
            storage_gb=self._detect_storage_gb(),
            has_gpu=True,
            gpu_model="Mali-G52 2EE",
        )

    def _get_cpu_model(self) -> str:
        return "Rockchip RK3566"

    @staticmethod
    def _detect_cpu_cores() -> int:
        try:
            cores = os.cpu_count()
            if cores:
                return cores
        except Exception as e:
            logger.warning(f"Error detecting CPU cores: {e}")
        return 4

    @staticmethod
    def _detect_ram_gb() -> int:
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return max(1, int(round(kb / (1024 * 1024))))
        except Exception as e:
            logger.warning(f"Error detecting RAM: {e}")
        return 4

    @staticmethod
    def _detect_storage_gb() -> int:
        try:
            output = subprocess.check_output(["df", "/"], text=True, timeout=3)
            lines = output.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                kb = int(parts[1])
                return max(1, int(round(kb / (1024 * 1024))))
        except Exception as e:
            logger.warning(f"Error detecting storage: {e}")
        return 32

    @staticmethod
    def _read_os_release() -> dict:
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
        try:
            return subprocess.check_output(["uname", "-r"], text=True, timeout=3).strip()
        except Exception as e:
            logger.warning(f"Error getting kernel version: {e}")
            return "unknown"

    @staticmethod
    def _detect_storage_type() -> StorageType:
        try:
            output = subprocess.check_output(["df", "/"], text=True, timeout=3)
            for line in output.split("\n")[1:]:
                if line.startswith("/dev/"):
                    device = line.split()[0]
                    if "mmcblk" in device:
                        return StorageType.EMMC
                    elif "sd" in device:
                        return StorageType.SD_CARD
                    elif "nvme" in device:
                        return StorageType.NVME
        except Exception as e:
            logger.warning(f"Error detecting storage type: {e}")
        return StorageType.EMMC
