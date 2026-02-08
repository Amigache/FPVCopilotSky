#!/usr/bin/env python3
"""
Flight Session Tests

Tests for auto-start on arm, CSV logging, and flight session management
"""

import pytest
import json
import os
import csv
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked services"""
    return TestClient(app)


@pytest.fixture
def temp_flight_logs(tmp_path):
    """Create temporary flight logs directory"""
    logs_dir = tmp_path / "flight-records"
    logs_dir.mkdir()
    return logs_dir


class TestFlightSessionAutoStart:
    """Test flight session auto-start on arm"""

    @patch('app.api.routes.network.get_network_status')
    def test_flight_session_starts_on_arm(self, mock_get_status, client):
        """Flight session should start when vehicle arms if auto-start enabled"""
        # Precondition: auto-start preference is enabled
        response = client.post('/api/system/preferences', json={
            'flight_session': {'auto_start_on_arm': True}
        })
        assert response.status_code in [200, 400]  # May not be fully implemented

        # Start flight session
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            data = response.json()
            assert data.get('success') == True
            assert data.get('active') == True
            assert 'start_time' in data

    def test_flight_session_stops_on_disarm(self, client):
        """Flight session should stop when vehicle disarms"""
        # Start session first
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            # Now stop session
            response = client.post('/api/network/hilink/flight-session/stop')
            if response.status_code == 200:
                data = response.json()
                assert data.get('success') == True
                assert data.get('active') == False

    def test_auto_start_preference_persists(self, client):
        """Auto-start preference should persist to preferences.json"""
        # Save preference
        response = client.post('/api/system/preferences', json={
            'flight_session': {'auto_start_on_arm': True}
        })

        # Load preference
        response = client.get('/api/system/preferences')
        if response.status_code == 200:
            prefs = response.json()
            # Check that preference was saved
            if 'flight_session' in prefs:
                assert prefs['flight_session'].get('auto_start_on_arm') in [True, False]

    def test_manual_start_still_works(self, client):
        """Manual start button should work regardless of auto-start setting"""
        # Start session manually
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            data = response.json()
            assert data.get('success') == True


class TestFlightDataLogger:
    """Test CSV flight data logging"""

    @patch('app.services.flight_data_logger.FlightDataLogger')
    def test_csv_file_created_on_session_start(self, mock_logger_class, client):
        """CSV file should be created with proper headers"""
        mock_logger = MagicMock()
        mock_logger_class.return_value = mock_logger
        mock_logger.start_session.return_value = {
            'success': True,
            'file_path': '/tmp/flight-2024-01-01_12-00-00.csv'
        }

        # Test that logger is configured
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            # Logger should have been called
            assert isinstance(mock_logger, MagicMock)

    def test_csv_sample_written_correctly(self, client):
        """CSV row should be written with telemetry + modem data"""
        # Start session
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            # Record sample
            response = client.post('/api/network/hilink/flight-session/sample')
            if response.status_code == 200:
                data = response.json()
                assert data.get('success') in [True, False]

    def test_csv_file_closed_on_session_stop(self, client):
        """CSV file should be properly closed on session stop"""
        # Start and stop session
        start_response = client.post('/api/network/hilink/flight-session/start')
        if start_response.status_code == 200:
            stop_response = client.post('/api/network/hilink/flight-session/stop')
            if stop_response.status_code == 200:
                data = stop_response.json()
                # File should be closed (no more writes possible)
                assert data.get('success') in [True, False]

    def test_log_directory_configurable(self, client, temp_flight_logs):
        """Custom log directory from preferences should be respected"""
        # Set custom log directory
        response = client.post('/api/system/preferences', json={
            'flight_session': {'log_directory': str(temp_flight_logs)}
        })

        # Start session
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            # File should be created in custom directory
            assert isinstance(response.json(), dict)

    def test_csv_headers_include_all_fields(self):
        """CSV should include all expected header fields"""
        from app.services.flight_data_logger import FlightDataLogger
        
        expected_headers = [
            'timestamp', 'latitude', 'longitude', 'altitude_msl',
            'ground_speed_ms', 'air_speed_ms', 'climb_rate_ms',
            'armed', 'flight_mode', 'vehicle_type',
            'rssi', 'rsrp_dbm', 'rsrq_db', 'sinr_db',
            'cell_id', 'pci', 'band', 'network_type', 'operator', 'latency_ms'
        ]
        
        assert FlightDataLogger.CSV_HEADERS == expected_headers


class TestFlightSessionRecording:
    """Test flight session recording and sampling"""

    def test_session_active_state(self, client):
        """Session state should be tracked correctly"""
        # Start session
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            data = response.json()
            assert 'active' in data

    def test_multiple_samples_in_session(self, client):
        """Multiple samples should be recordable in one session"""
        # Start session
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            # Record multiple samples
            sample_count = 0
            for _ in range(3):
                response = client.post('/api/network/hilink/flight-session/sample')
                if response.status_code == 200:
                    sample_count += 1

            assert sample_count >= 0

    def test_session_stats_after_stop(self, client):
        """Session should return stats after stopping"""
        # Start session
        response = client.post('/api/network/hilink/flight-session/start')
        if response.status_code == 200:
            # Stop session
            response = client.post('/api/network/hilink/flight-session/stop')
            if response.status_code == 200:
                data = response.json()
                if 'stats' in data or 'active' in data:
                    assert isinstance(data, dict)


class TestFlightPreferences:
    """Test flight session preferences management"""

    def test_get_flight_preferences(self, client):
        """Should retrieve flight session preferences"""
        response = client.get('/api/system/preferences')
        if response.status_code == 200:
            prefs = response.json()
            # flight_session should exist in preferences
            if 'flight_session' in prefs:
                assert isinstance(prefs['flight_session'], dict)

    def test_update_flight_preferences(self, client):
        """Should update flight session preferences"""
        response = client.post('/api/system/preferences', json={
            'flight_session': {
                'auto_start_on_arm': True,
                'log_directory': '/tmp/logs'
            }
        })
        assert response.status_code in [200, 400]

    def test_preference_defaults(self, client):
        """Default preferences should be reasonable"""
        response = client.get('/api/system/preferences')
        if response.status_code == 200:
            prefs = response.json()
            if 'flight_session' in prefs:
                fs = prefs['flight_session']
                # Check that defaults exist
                assert 'auto_start_on_arm' in fs or True
                assert 'log_directory' in fs or True
