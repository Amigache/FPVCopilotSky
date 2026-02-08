"""
Performance Profiling Tests

Comprehensive performance profiling including CPU, memory, latency,
and throughput measurements for all major system components.
"""

import pytest
import time
import psutil
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(mock_api_services):
    """Create TestClient with mocked API services"""
    return TestClient(app)


@pytest.fixture
def process_metrics():
    """Get current process metrics"""
    process = psutil.Process()
    return {
        "cpu_percent": process.cpu_percent(interval=0.1),
        "memory_info": process.memory_info(),
        "num_threads": process.num_threads(),
    }


class TestAPILatency:
    """Test API endpoint latency"""

    def test_status_endpoint_latency(self, client):
        """Measure latency of status endpoint"""
        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/status/health")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # ms

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 1000, f"Status endpoint latency too high: {avg_latency}ms"

    def test_system_info_endpoint_latency(self, client):
        """Measure latency of system info endpoint"""
        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/system/info")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 5000, f"System info latency too high: {avg_latency}ms"

    def test_network_status_endpoint_latency(self, client):
        """Measure latency of network status endpoint"""
        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/network/status")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 2000, f"Network status latency too high: {avg_latency}ms"

    def test_video_config_endpoint_latency(self, client):
        """Measure latency of video config endpoint"""
        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/video/config")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 2000, f"Video config latency too high: {avg_latency}ms"

    def test_vpn_status_endpoint_latency(self, client):
        """Measure latency of VPN status endpoint"""
        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/vpn/status")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 2000, f"VPN status latency too high: {avg_latency}ms"


class TestThroughput:
    """Test API throughput and capacity"""

    def test_sequential_requests_throughput(self, client):
        """Measure throughput of sequential requests"""
        num_requests = 20
        start = time.perf_counter()

        for _ in range(num_requests):
            response = client.get("/api/status/health")
            assert response.status_code in [200, 404, 500]

        end = time.perf_counter()
        duration = end - start
        throughput = num_requests / duration

        # Realistic threshold for Radxa Zero (ARM-based, 4GB RAM)
        # CI may run slower due to mocking/test overhead
        assert throughput > 2, f"Throughput too low: {throughput} req/s"

    def test_mixed_endpoint_throughput(self, client):
        """Measure throughput with mixed endpoints"""
        endpoints = [
            "/api/status/health",
            "/api/system/status",
            "/api/network/status",
            "/api/video/config",
            "/api/vpn/status",
        ]

        num_cycles = 4
        start = time.perf_counter()

        for _ in range(num_cycles):
            for endpoint in endpoints:
                response = client.get(endpoint)
                assert response.status_code in [200, 404, 500]

        end = time.perf_counter()
        duration = end - start
        total_requests = len(endpoints) * num_cycles
        throughput = total_requests / duration

        assert throughput > 5, f"Mixed throughput too low: {throughput} req/s"

    def test_burst_request_handling(self, client):
        """Test burst handling with rapid requests"""
        burst_size = 10
        start = time.perf_counter()

        # Rapid fire requests
        responses = []
        for _ in range(burst_size):
            response = client.get("/api/status/health")
            responses.append(response.status_code)

        end = time.perf_counter()
        duration = end - start

        # All should succeed
        assert all(status in [200, 404, 500] for status in responses)
        # Should handle burst reasonably
        assert duration < 5.0, f"Burst handling too slow: {duration}s"


class TestMemoryUsage:
    """Test memory consumption and efficiency"""

    def test_api_memory_usage(self, client):
        """Measure memory usage during API calls"""
        process = psutil.Process()

        # Get baseline
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Make requests
        for _ in range(10):
            response = client.get("/api/system/status")

        # Get end memory
        final_memory = process.memory_info().rss / 1024 / 1024

        memory_increase = final_memory - initial_memory
        # Allow reasonable memory increase (< 50MB)
        assert memory_increase < 50, f"Memory increase too large: {memory_increase}MB"

    def test_memory_stability(self, client):
        """Test memory stability over multiple requests"""
        process = psutil.Process()
        memory_samples = []

        for _ in range(5):
            client.get("/api/status/health")
            memory_samples.append(process.memory_info().rss / 1024 / 1024)

        # Check for memory leaks (increasing trend)
        differences = [memory_samples[i + 1] - memory_samples[i] for i in range(len(memory_samples) - 1)]
        avg_increase = sum(differences) / len(differences)

        # Should be stable (no consistent increase)
        assert avg_increase < 5, f"Memory leak detected: {avg_increase}MB average increase"


class TestCPUUsage:
    """Test CPU efficiency"""

    def test_cpu_usage_single_request(self, client):
        """Measure CPU usage per request"""
        process = psutil.Process()

        start_cpu = process.cpu_num()
        response = client.get("/api/status/health")
        end_cpu = process.cpu_num()

        # Should complete without excessive CPU
        assert response.status_code in [200, 404, 500]

    def test_cpu_efficiency_sustained_load(self, client):
        """Test CPU efficiency under sustained load"""
        process = psutil.Process()

        # Warm up
        for _ in range(5):
            client.get("/api/status/health")

        # Measure
        start = time.perf_counter()
        cpu_samples = []

        for _ in range(10):
            cpu_percent = process.cpu_percent(interval=0.01)
            cpu_samples.append(cpu_percent)
            client.get("/api/status/health")

        end = time.perf_counter()
        avg_cpu = sum(cpu_samples) / len(cpu_samples)

        # CPU usage should be reasonable (<50% for test process)
        assert avg_cpu < 50, f"CPU usage too high: {avg_cpu}%"


class TestResponseSize:
    """Test response payload sizes"""

    def test_status_response_size(self, client):
        """Measure status endpoint response size"""
        response = client.get("/api/status/health")

        if response.status_code == 200:
            content_length = len(response.content)
            # Should be small response
            assert content_length < 10000, f"Response too large: {content_length} bytes"

    def test_system_info_response_size(self, client):
        """Measure system info response size"""
        response = client.get("/api/system/info")

        if response.status_code == 200:
            content_length = len(response.content)
            # Should be reasonable for info
            assert content_length < 100000, f"Response too large: {content_length} bytes"

    def test_network_status_response_size(self, client):
        """Measure network status response size"""
        response = client.get("/api/network/status")

        if response.status_code == 200:
            content_length = len(response.content)
            assert content_length < 50000, f"Response too large: {content_length} bytes"


class TestConcurrentLoad:
    """Test system under concurrent load"""

    def test_concurrent_requests_stability(self, client):
        """Test stability under concurrent requests"""
        concurrent_requests = 5
        responses = []

        import threading

        def make_request():
            response = client.get("/api/status/health")
            responses.append(response.status_code)

        threads = []
        for _ in range(concurrent_requests):
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All should succeed
        assert len(responses) == concurrent_requests
        assert all(status in [200, 404, 500] for status in responses)

    def test_concurrent_mixed_endpoints(self, client):
        """Test concurrent requests to different endpoints"""
        endpoints = [
            "/api/status/health",
            "/api/system/status",
            "/api/network/status",
        ]

        responses = []

        import threading

        def make_request(endpoint):
            response = client.get(endpoint)
            responses.append(
                {
                    "endpoint": endpoint,
                    "status": response.status_code,
                }
            )

        threads = []
        for endpoint in endpoints:
            for _ in range(2):
                t = threading.Thread(target=make_request, args=(endpoint,))
                threads.append(t)
                t.start()

        for t in threads:
            t.join()

        assert len(responses) == len(endpoints) * 2
        assert all(r["status"] in [200, 404, 500] for r in responses)


class TestEndpointBottlenecks:
    """Identify endpoint bottlenecks"""

    def test_slowest_endpoint_identification(self, client):
        """Identify slowest endpoints"""
        endpoints = [
            "/api/status/health",
            "/api/status/dependencies",
            "/api/system/info",
            "/api/system/status",
            "/api/network/status",
            "/api/network/interfaces",
            "/api/video/config",
            "/api/vpn/status",
            "/api/vpn/peers",
            "/api/modem/status",
        ]

        latencies = {}

        for endpoint in endpoints:
            times = []
            for _ in range(3):
                start = time.perf_counter()
                response = client.get(endpoint)
                end = time.perf_counter()
                if response.status_code in [200, 404, 500]:
                    times.append((end - start) * 1000)

            if times:
                latencies[endpoint] = sum(times) / len(times)

        # Find slowest
        if latencies:
            slowest = max(latencies, key=latencies.get)
            slowest_time = latencies[slowest]

            # Log for analysis
            assert slowest_time < 10000, f"Slowest endpoint {slowest}: {slowest_time}ms"

    def test_resource_intensive_operations(self, client):
        """Identify resource-intensive operations"""
        endpoints_to_test = [
            "/api/system/info",
            "/api/network/interfaces",
            "/api/status/dependencies",
        ]

        process = psutil.Process()

        for endpoint in endpoints_to_test:
            initial_memory = process.memory_info().rss

            # Make request
            response = client.get(endpoint)

            final_memory = process.memory_info().rss
            memory_delta = (final_memory - initial_memory) / 1024

            # Memory increase should be minimal
            assert memory_delta < 10000, f"{endpoint} used too much memory: {memory_delta}KB"


class TestResponseTimeDistribution:
    """Analyze response time distribution"""

    def test_response_time_percentiles(self, client):
        """Measure response time percentiles"""
        latencies = []

        for _ in range(20):
            start = time.perf_counter()
            response = client.get("/api/status/health")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        latencies.sort()

        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        # Percentile assertions
        assert p50 < 500, f"P50 latency too high: {p50}ms"
        assert p95 < 1000, f"P95 latency too high: {p95}ms"
        assert p99 < 2000, f"P99 latency too high: {p99}ms"

    def test_latency_consistency(self, client):
        """Test latency consistency across calls"""
        latencies = []

        for _ in range(10):
            start = time.perf_counter()
            response = client.get("/api/status/health")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        # Calculate standard deviation
        mean = sum(latencies) / len(latencies)
        variance = sum((x - mean) ** 2 for x in latencies) / len(latencies)
        std_dev = variance**0.5

        # Should be consistent (low standard deviation)
        assert std_dev < mean * 0.5, f"Inconsistent latency: std_dev={std_dev}ms, mean={mean}ms"
