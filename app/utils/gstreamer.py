"""
GStreamer utility helpers.

Centralised, cached checks for GStreamer plugin availability so that
every encoder / source provider does not shell out individually.
"""

import logging
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)

# Module-level cache: element_name → bool
_gst_plugin_cache: Dict[str, bool] = {}

# Timeout for gst-inspect-1.0 calls.
# On first boot GStreamer may rebuild its plugin registry while
# gst-plugin-scanner is running; 10 s accommodates that.
GST_INSPECT_TIMEOUT = 10


def is_gst_element_available(element: str) -> bool:
    """Return *True* if *element* is available in the GStreamer registry.

    Results are cached for the lifetime of the process (plugin
    availability doesn't change at runtime).
    """
    if element in _gst_plugin_cache:
        return _gst_plugin_cache[element]

    try:
        result = subprocess.run(
            ["gst-inspect-1.0", element],
            capture_output=True,
            timeout=GST_INSPECT_TIMEOUT,
        )
        available = result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning(
            "gst-inspect-1.0 %s timed out after %ds (registry still building?)",
            element,
            GST_INSPECT_TIMEOUT,
        )
        available = False
    except FileNotFoundError:
        logger.warning("gst-inspect-1.0 not found on PATH")
        available = False
    except Exception as e:  # pragma: no cover
        logger.error("Error checking GStreamer element %s: %s", element, e)
        available = False

    _gst_plugin_cache[element] = available
    if available:
        logger.debug("GStreamer element '%s' is available", element)

    return available
