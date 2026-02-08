"""
Board Registry: singleton that detects and manages available boards
"""

import os
import importlib
import logging
from typing import Optional, List
from .board_provider import BoardProvider
from .detected_board import DetectedBoard

logger = logging.getLogger(__name__)


class BoardRegistry:
    """
    Singleton registry for board providers.

    - Auto-discovers board provider modules
    - Detects running board at startup
    - Provides detected board info to services
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._providers = []
            cls._instance._detected_board = None
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # _providers and _detected_board already initialized in __new__

        logger.info("Initializing BoardRegistry")
        self._discover_providers()
        self.detect_board()

    def _discover_providers(self):
        """
        Auto-discover board provider modules in implementations/
        """
        implementations_dir = os.path.join(os.path.dirname(__file__), "implementations")

        if not os.path.exists(implementations_dir):
            logger.warning(f"Implementations directory not found: {implementations_dir}")
            return

        package_prefix = __package__ or "providers.board"

        # Walk implementations directory structure
        for root, dirs, files in os.walk(implementations_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    # Extract module path: implementations/radxa/zero.py -> implementations.radxa.zero
                    rel_path = os.path.relpath(os.path.join(root, file), implementations_dir)
                    module_path = f"{package_prefix}.implementations.{rel_path[:-3].replace(os.sep, '.')}"

                    try:
                        module = importlib.import_module(module_path)
                        logger.debug(f"Loaded board module: {module_path}")

                        # Find BoardProvider subclasses in module
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and issubclass(attr, BoardProvider) and attr is not BoardProvider:

                                provider = attr()
                                self._providers.append(provider)
                                logger.info(f"Registered board provider: {provider.board_name}")

                    except Exception as e:
                        logger.error(f"Failed to load board module {module_path}: {e}")

    def detect_board(self) -> Optional[DetectedBoard]:
        """
        Detect running board by checking all providers.

        Tries each provider in order until one successfully detects.

        Returns:
            DetectedBoard if detection successful, None otherwise
        """
        if self._detected_board is not None:
            return self._detected_board

        logger.info(f"Detecting board from {len(self._providers)} providers")

        for provider in self._providers:
            try:
                detected = provider.detect_board()
                if detected:
                    self._detected_board = detected
                    logger.info(
                        f"Board detected: {detected.board_name} "
                        f"({detected.variant.name}) "
                        f"confidence={detected.detection_confidence}"
                    )
                    return detected
            except Exception as e:
                logger.warning(f"Detection failed for {provider.board_name}: {e}")

        logger.warning("No board detected")
        return None

    def get_detected_board(self) -> Optional[DetectedBoard]:
        """Get currently detected board, or None if detection failed"""
        return self._detected_board

    def get_provider(self, board_identifier: str) -> Optional[BoardProvider]:
        """Get board provider by identifier"""
        for provider in self._providers:
            if provider.board_identifier == board_identifier:
                return provider
        return None

    def list_providers(self) -> List[BoardProvider]:
        """List all available board providers"""
        return self._providers.copy()

    def supports_feature(self, feature_name: str) -> bool:
        """
        Check if detected board supports a feature.

        Examples:
            - supports_feature("video_source:v4l2")
            - supports_feature("video_encoder:hardware_h264")
            - supports_feature("connectivity:wifi")
        """
        if not self._detected_board:
            return False

        # Parse feature_name format: "category:feature"
        if ":" not in feature_name:
            return False

        category, feature = feature_name.split(":", 1)
        variant = self._detected_board.variant

        if category == "video_source":
            return feature in [f.value for f in variant.video_sources]
        elif category == "video_encoder":
            return feature in [f.value for f in variant.video_encoders]
        elif category == "connectivity":
            return feature in [f.value for f in variant.connectivity]
        elif category == "system_feature":
            return feature in [f.value for f in variant.system_features]

        return False
