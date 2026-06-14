"""
GStreamer utility helpers.

Centralised, cached checks for GStreamer plugin availability so that
every encoder / source provider does not shell out individually.
"""

import logging
import threading
from typing import Dict
from app.utils.cmd import run_cmd

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

    stdout, stderr, returncode = run_cmd(
        ["gst-inspect-1.0", element],
        timeout=GST_INSPECT_TIMEOUT,
        check=False,
    )
    available = returncode == 0
    if not available and "Command timed out" in stderr:
        logger.warning(
            "gst-inspect-1.0 %s timed out after %ds (registry still building?)",
            element,
            GST_INSPECT_TIMEOUT,
        )
    elif not available and ("No such file or directory" in stderr or "not found" in stderr.lower()):
        logger.warning("gst-inspect-1.0 not found on PATH")
    elif not available and stderr:
        logger.debug("gst-inspect-1.0 probe failed for %s: %s", element, stderr)

    with _gst_cache_lock:
        _gst_plugin_cache[element] = available
    if available:
        logger.debug("GStreamer element '%s' is available", element)

    return available
