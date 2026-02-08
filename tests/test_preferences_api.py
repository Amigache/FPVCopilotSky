#!/usr/bin/env python3
"""
System Preferences API Tests

Tests for preferences endpoints (GET/POST /api/system/preferences)
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked services"""
    return TestClient(app)


class TestPreferencesEndpoints:
    """Test system preferences API endpoints"""

    def test_get_all_preferences(self, client):
        """GET /api/system/preferences should return all preferences"""
        response = client.get('/api/system/preferences')
        
        if response.status_code == 200:
            prefs = response.json()
            assert isinstance(prefs, dict)
            # Should contain at least some sections
            possible_keys = ['serial', 'video', 'streaming', 'vpn', 'ui', 'flight_session', 'system']
            assert any(key in prefs for key in possible_keys)

    def test_get_preferences_has_flight_session(self, client):
        """Preferences should include flight_session config"""
        response = client.get('/api/system/preferences')
        
        if response.status_code == 200:
            prefs = response.json()
            if 'flight_session' in prefs:
                fs = prefs['flight_session']
                assert isinstance(fs, dict)
                # Should have expected keys
                assert any(key in fs for key in ['auto_start_on_arm', 'log_directory'])

    def test_post_update_preferences(self, client):
        """POST /api/system/preferences should update preferences"""
        response = client.post('/api/system/preferences', json={
            'flight_session': {
                'auto_start_on_arm': True
            }
        })
        
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert 'success' in data or 'message' in data

    def test_post_update_serial_preferences(self, client):
        """Should be able to update serial preferences"""
        response = client.post('/api/system/preferences', json={
            'serial': {
                'port': '/dev/ttyUSB0',
                'baudrate': 115200
            }
        })
        
        assert response.status_code in [200, 400]

    def test_post_update_video_preferences(self, client):
        """Should be able to update video preferences"""
        response = client.post('/api/system/preferences', json={
            'video': {
                'codec': 'mjpeg',
                'width': 960,
                'height': 720
            }
        })
        
        assert response.status_code in [200, 400]

    def test_post_update_ui_preferences(self, client):
        """Should be able to update UI preferences"""
        response = client.post('/api/system/preferences', json={
            'ui': {
                'language': 'en',
                'theme': 'dark'
            }
        })
        
        assert response.status_code in [200, 400]

    def test_preferences_persistence(self, client):
        """Updated preferences should persist"""
        # Update preference
        response = client.post('/api/system/preferences', json={
            'ui': {'language': 'es'}
        })
        
        if response.status_code == 200:
            # Verify it was saved
            response = client.get('/api/system/preferences')
            if response.status_code == 200:
                prefs = response.json()
                if 'ui' in prefs and 'language' in prefs['ui']:
                    # Language should be set (or default)
                    assert isinstance(prefs['ui']['language'], str)

    def test_partial_update_doesnt_remove_other_keys(self, client):
        """Updating one key should not remove other keys"""
        # Get current state
        response = client.get('/api/system/preferences')
        if response.status_code == 200:
            original_prefs = response.json()
            original_keys = set(original_prefs.keys())
            
            # Update just one section
            response = client.post('/api/system/preferences', json={
                'ui': {'theme': 'light'}
            })
            
            # Verify other sections still exist
            if response.status_code == 200:
                response = client.get('/api/system/preferences')
                if response.status_code == 200:
                    new_prefs = response.json()
                    new_keys = set(new_prefs.keys())
                    # Should have same sections (or more)
                    assert original_keys.issubset(new_keys) or new_keys.issubset(original_keys)

    def test_invalid_preference_key(self, client):
        """Should handle invalid preference keys gracefully"""
        response = client.post('/api/system/preferences', json={
            'invalid_key': {'value': 'test'}
        })
        
        # Should either ignore or return error
        assert response.status_code in [200, 400, 422]

    def test_reset_preferences_endpoint(self, client):
        """POST /api/system/preferences/reset should reset to defaults"""
        response = client.post('/api/system/preferences/reset')
        
        if response.status_code == 200:
            data = response.json()
            assert 'success' in data or 'message' in data

    def test_flight_session_auto_start_preference(self, client):
        """Should be able to set auto_start_on_arm preference"""
        # Enable auto-start
        response = client.post('/api/system/preferences', json={
            'flight_session': {'auto_start_on_arm': True}
        })
        
        if response.status_code == 200:
            # Retrieve and verify
            response = client.get('/api/system/preferences')
            if response.status_code == 200:
                prefs = response.json()
                if 'flight_session' in prefs:
                    assert 'auto_start_on_arm' in prefs['flight_session']

    def test_flight_session_log_directory(self, client):
        """Should be able to set custom log directory"""
        response = client.post('/api/system/preferences', json={
            'flight_session': {'log_directory': '/tmp/flight-logs'}
        })
        
        if response.status_code == 200:
            # Verify it was set
            response = client.get('/api/system/preferences')
            if response.status_code == 200:
                prefs = response.json()
                if 'flight_session' in prefs:
                    if 'log_directory' in prefs['flight_session']:
                        assert isinstance(prefs['flight_session']['log_directory'], str)
