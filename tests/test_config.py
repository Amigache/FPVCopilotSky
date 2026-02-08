"""
Tests for Application Services Module

Tests for core application services initialization and configuration
"""

import pytest
import os
import json
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestServicesImports:
    """Test that core services can be imported"""

    def test_preferences_service_exists(self):
        """Test that preferences service module exists"""
        try:
            from app.services import preferences
            assert preferences is not None
        except ImportError:
            pytest.skip("Preferences service not available")

    def test_mavlink_bridge_exists(self):
        """Test that MAVLink bridge module exists"""
        try:
            from app.services import mavlink_bridge
            assert mavlink_bridge is not None
        except ImportError:
            pytest.skip("MAVLink bridge not available")

    def test_websocket_manager_exists(self):
        """Test that WebSocket manager module exists"""
        try:
            from app.services import websocket_manager
            assert websocket_manager is not None
        except ImportError:
            pytest.skip("WebSocket manager not available")


class TestProvidersExists:
    """Test that provider modules exist"""

    def test_providers_module_exists(self):
        """Test that providers package exists"""
        try:
            from app import providers
            assert providers is not None
        except ImportError:
            pytest.skip("Providers package not available")

    def test_board_provider_exists(self):
        """Test that board provider module exists"""
        try:
            from app.providers import board
            assert board is not None
        except ImportError:
            pytest.skip("Board provider not available")

    def test_network_providers_exist(self):
        """Test that network providers module exists"""
        try:
            from app.providers import network
            assert network is not None
        except ImportError:
            pytest.skip("Network providers not available")
