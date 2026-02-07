"""
Radxa Zero board provider

Hardware: Amlogic S905Y2 CPU, 4GB RAM, 32GB eMMC, WiFi 5 (or 4)
Supported Storage: eMMC, SD Card, USB
Distros: Armbian, Ubuntu, Debian

⚠️ Kernel families (Armbian-specific):
   - legacy:  Vendor BSP kernel (máximo soporte HW, menos mantenimiento)
   - current: Kernel mainline estable (buen balance, recomendado)
   - edge:    Kernel mainline más reciente (experimental, posibles issues)

El soporte para HW H.264 encoder en Amlogic depende MUCHO del kernel.
"""

import os
import logging
import subprocess
from typing import Optional, List
from enum import Enum
from ...board_provider import BoardProvider
from ...board_definitions import (
    HardwareInfo, VariantInfo, DetectionCriteria,
    StorageType, DistroFamily, CPUArch,
    VideoSourceFeature, VideoEncoderFeature, ConnectivityFeature, SystemFeature
)
logger = logging.getLogger(__name__)


class ArmbiankernelFamily(Enum):
    """Armbian kernel families for Amlogic SoC"""
    LEGACY = "legacy"      # Vendor BSP, máximo HW support
    CURRENT = "current"    # Mainline estable (recomendado)
    EDGE = "edge"          # Mainline latest (experimental)
    UNKNOWN = "unknown"    # No se pudo determinar


class RadxaZeroProvider(BoardProvider):
    """
    Radxa Zero - ARM SBC with Amlogic S905Y2
    https://wiki.radxa.com/Zero
    
    Auto-detects at runtime:
    - CPU cores from /proc/cpuinfo
    - RAM from /proc/meminfo
    - Storage capacity from df
    - Kernel family (legacy/current/edge) from version string
    
    Variants managed:
    - Storage: eMMC (internal), SD Card (external), USB (external)
    - Distro: Armbian (primary), Ubuntu, Debian
    - Kernel family: legacy (max HW support) vs current (recommended)
    
    ⚠️ HW H.264 encoder support varies by kernel family:
       - legacy: máximo soporte VPU/encoder (vendor BSP)
       - current: buen balance, encoder funciona bien (recomendado)
       - edge: experimental, puede faltar soporte
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
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                if criteria.device_tree_contains and criteria.device_tree_contains in model:
                    logger.info(f"Detected Radxa Zero via device tree: {model}")
                    return True
        except Exception as e:
            logger.debug(f"Device tree check failed: {e}")
        
        # Priority 2: Check cpuinfo for Amlogic
        try:
            if criteria.cpu_model_contains:
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    if criteria.cpu_model_contains in content:
                        logger.info("Detected Radxa Zero via cpuinfo (Amlogic CPU)")
                        return True
        except Exception as e:
            logger.debug(f"cpuinfo check failed: {e}")
        
        return False
    
    def get_variants(self) -> List[VariantInfo]:
        """
        Define all supported variants for Radxa Zero.
        
        Focus en las dos familias principales de kernel Armbian:
        1. current: mainline estable, buen balance (pero SIN HW H.264 confiable)
        2. legacy: vendor BSP, máximo soporte HW para VPU/encoder
        
        ⚠️ IMPORTANTE: HW H.264 solo en legacy. Current es mainline y no tiene
        soporte VPU H.264 confiable en Amlogic S905Y2.
        """
        variants = []
        
        # Variant 1: Armbian current kernel (RECOMENDADO para estabilidad)
        # Mainline estable, buen balance, pero SIN HW H.264
        armbian_current = VariantInfo(
            name="Armbian current kernel",
            storage_type=StorageType.EMMC,
            distro_family=DistroFamily.ARMBIAN,
            distro_version="25.11.2",
            kernel_version="6.12.58-current-meson64",
            is_default=True,
            
            # Video capabilities (current kernel - SIN HW H.264)
            video_sources=[
                VideoSourceFeature.V4L2,
                VideoSourceFeature.LIBCAMERA,
            ],
            video_encoders=[
                # ⚠️ NO hardware_h264 en mainline current
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
            ]
        )
        variants.append(armbian_current)
        
        # Variant 2: Armbian legacy kernel
        # Vendor BSP kernel, máximo soporte de HW/VPU (incluyendo H.264)
        armbian_legacy = VariantInfo(
            name="Armbian legacy kernel (máximo HW support)",
            storage_type=StorageType.EMMC,
            distro_family=DistroFamily.ARMBIAN,
            distro_version="25.11.2",
            kernel_version="5.15-legacy-meson64",
            is_default=False,
            
            # Video: legacy kernel tiene soporte completo VPU/encoder
            video_sources=[
                VideoSourceFeature.V4L2,
                VideoSourceFeature.LIBCAMERA,
            ],
            video_encoders=[
                VideoEncoderFeature.HARDWARE_H264,  # ✅ Disponible en legacy (vendor BSP)
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
            ]
        )
        variants.append(armbian_legacy)
        
        return variants
    
    def detect_running_variant(self) -> Optional[VariantInfo]:
        """
        Detect which variant is currently running.
        
        Especial care para Armbian: detecta la familia de kernel
        (legacy/current/edge) y retorna la variante apropiada
        con los features correctos para esa rama.
        """
        try:
            distro_info = self._read_os_release()
            if not distro_info:
                logger.warning("Cannot read /etc/os-release")
                return None
            
            distro_name = distro_info.get('name', '').lower()
            distro_version = distro_info.get('version_id', '')
            
            storage_type = self._detect_storage_type()
            kernel_version = self._get_kernel_version()
            
            # Match Radxa Zero - Armbian es la distro principal
            if 'armbian' in distro_name:
                kernel_family = self._detect_kernel_family(kernel_version)
                logger.info(
                    f"Detected Armbian Radxa Zero with {kernel_family.value} kernel: {kernel_version}"
                )
                
                # Selecciona variante según kernel family
                variant = self._get_variant_for_kernel_family(kernel_family)
                
                # Actualiza valores detectados en runtime
                variant.storage_type = storage_type
                variant.kernel_version = kernel_version
                variant.distro_version = distro_version
                
                return variant
            
            # Fallback: Acepta cualquier distro basada en Debian
            # (Ubuntu, Debian, etc.) si es Radxa Zero
            if any(deb in distro_name for deb in ['ubuntu', 'debian', 'raspberry']):
                variants = self.get_variants()
                variant = variants[0]  # Usa default (current)
                variant.storage_type = storage_type
                variant.kernel_version = kernel_version
                variant.distro_family = (
                    DistroFamily.DEBIAN if 'debian' in distro_name 
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
    
    def _detect_kernel_family(self, kernel_version: str) -> ArmbiankernelFamily:
        """
        Detecta la familia de kernel de Armbian desde la versión string.
        
        Formato Armbian: X.Y.Z-FAMILIA-meson64
        Ejemplos:
        - 6.12.58-current-meson64  → CURRENT
        - 5.15.25-legacy-meson64   → LEGACY
        - 6.13-edge-meson64        → EDGE
        
        Returns:
            ArmbiankernelFamily: legacy, current, edge, o unknown
        """
        if not kernel_version:
            logger.warning("Empty kernel version, assuming current")
            return ArmbiankernelFamily.CURRENT
        
        kernel_lower = kernel_version.lower()
        
        # Look for family marker in kernel version string
        if 'legacy' in kernel_lower:
            logger.info(f"Detected Armbian LEGACY kernel: {kernel_version}")
            return ArmbiankernelFamily.LEGACY
        elif 'current' in kernel_lower:
            logger.info(f"Detected Armbian CURRENT kernel: {kernel_version}")
            return ArmbiankernelFamily.CURRENT
        elif 'edge' in kernel_lower:
            logger.info(f"Detected Armbian EDGE kernel: {kernel_version}")
            return ArmbiankernelFamily.EDGE
        else:
            # Non-Armbian kernel or unknown format
            logger.debug(
                f"Cannot determine kernel family from: {kernel_version}, "
                "assuming current characteristics"
            )
            return ArmbiankernelFamily.CURRENT
    
    def _get_variant_for_kernel_family(self, family: ArmbiankernelFamily) -> VariantInfo:
        """
        Retorna la configuración de variante para la familia de kernel detectada.
        
        - legacy: máximo soporte HW, encoder funciona muy bien (index 1)
        - current: recomendado, buen balance (index 0, default)
        - edge: experimental, puede faltar soporte (no implementado aún)
        """
        variants = self.get_variants()
        
        if family == ArmbiankernelFamily.LEGACY:
            logger.info("Using LEGACY kernel variant (máximo HW support)")
            return variants[1]
        elif family == ArmbiankernelFamily.EDGE:
            # Por ahora, usa current para edge también
            # Se puede extender con variant edge cuando se tenga más info
            logger.warning(
                "EDGE kernel detected, using current variant as fallback "
                "(edge support not fully implemented yet)"
            )
            return variants[0]
        else:
            # Default: current (index 0)
            logger.info("Using CURRENT kernel variant (recommended)")
            return variants[0]
    
    def _get_hardware_info(self) -> HardwareInfo:
        """Return hardware specs - auto-detects RAM and storage at runtime"""
        return HardwareInfo(
            cpu_model="Amlogic S905Y2",
            cpu_cores=self._detect_cpu_cores(),
            cpu_arch=CPUArch.ARMV8,
            ram_gb=self._detect_ram_gb(),
            storage_gb=self._detect_storage_gb(),
            has_gpu=True,
            gpu_model="Mali-G31 MP2"
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
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
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
            output = subprocess.check_output(['df', '/'], text=True)
            lines = output.strip().split('\n')
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
            with open(os_release_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip('"').strip("'")
                        info[key.lower()] = value
        except Exception as e:
            logger.error(f"Error reading {os_release_path}: {e}")
        
        return info
    
    @staticmethod
    def _get_kernel_version() -> str:
        """Get kernel version from uname"""
        try:
            output = subprocess.check_output(['uname', '-r'], text=True)
            return output.strip()
        except Exception as e:
            logger.warning(f"Error getting kernel version: {e}")
            return "unknown"
    
    @staticmethod
    def _detect_storage_type() -> StorageType:
        """Detect root storage type"""
        try:
            output = subprocess.check_output(['df', '/'], text=True)
            
            for line in output.split('\n')[1:]:
                if line.startswith('/dev/'):
                    device = line.split()[0]
                    
                    if 'mmcblk' in device:
                        return StorageType.EMMC
                    elif 'sd' in device:
                        return StorageType.SD_CARD
                    elif 'nvme' in device:
                        return StorageType.NVME
                    elif 'sda' in device or 'sdb' in device:
                        return StorageType.USB
            
            return StorageType.EMMC
        
        except Exception as e:
            logger.warning(f"Error detecting storage type: {e}")
            return StorageType.EMMC
