"""
GStreamer utility helpers.

Centralised, cached checks for GStreamer plugin availability so that
every encoder / source provider does not shell out individually.
"""

import logging
import subprocess
import threading
from typing import Dict

logger = logging.getLogger(__name__)

# Module-level cache: element_name → bool
_gst_plugin_cache: Dict[str, bool] = {}
_gst_cache_lock = threading.Lock()

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    _gst_available = True
    _gst_init_done = False
except Exception:  # pragma: no cover
    Gst = None  # type: ignore
    _gst_available = False
    _gst_init_done = False

# Timeout for gst-inspect-1.0 calls.
# On first boot GStreamer may rebuild its plugin registry while
# gst-plugin-scanner is running; 10 s accommodates that.
GST_INSPECT_TIMEOUT = 10


def is_gst_element_available(element: str) -> bool:
    """Return *True* if *element* is available in the GStreamer registry.

    Results are cached for the lifetime of the process (plugin
    availability doesn't change at runtime).
    """
    with _gst_cache_lock:
        if element in _gst_plugin_cache:
            return _gst_plugin_cache[element]

    # Prefer in-process registry query (avoids spawning gst-inspect processes
    # that can generate noisy MPP logs on some Rockchip boards).
    if _gst_available:
        global _gst_init_done
        try:
            with _gst_cache_lock:
                if not _gst_init_done:
                    Gst.init(None)
                    _gst_init_done = True

            available = Gst.ElementFactory.find(element) is not None
            with _gst_cache_lock:
                _gst_plugin_cache[element] = available
            if available:
                logger.debug("GStreamer element '%s' is available (Gst registry)", element)
            return available
        except Exception as e:
            logger.debug("Gst registry probe failed for %s, falling back to gst-inspect: %s", element, e)

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

    with _gst_cache_lock:
        _gst_plugin_cache[element] = available
    if available:
        logger.debug("GStreamer element '%s' is available", element)

    return available
