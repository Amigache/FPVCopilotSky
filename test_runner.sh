#!/bin/bash
cd /opt/FPVCopilotSky
source venv/bin/activate
PYTHONPATH=. pytest tests/test_api_routes.py::TestNetworkRouteModule tests/test_network_priority.py::TestNetworkPriorityMode -v --tb=short
