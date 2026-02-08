"""
Stress Testing Utilities

Tools for stress testing and load simulation.
"""

import asyncio
import random
import threading
import time
from typing import Callable, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


@dataclass
class StressTestResult:
    """Result from a stress test"""

    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    throughput_rps: float
    error_rate: float
    min_latency_ms: float
    max_latency_ms: float
    avg_latency_ms: float

    def __str__(self) -> str:
        return (
            f"Stress Test Results:\n"
            f"  Total Requests: {self.total_requests}\n"
            f"  Successful: {self.successful_requests}\n"
            f"  Failed: {self.failed_requests} ({self.error_rate:.1f}%)\n"
            f"  Duration: {self.duration_seconds:.2f}s\n"
            f"  Throughput: {self.throughput_rps:.2f} req/s\n"
            f"  Latency (min/avg/max): {self.min_latency_ms:.2f}/{self.avg_latency_ms:.2f}/{self.max_latency_ms:.2f}ms"
        )


class LoadSimulator:
    """Simulate load with concurrent requests"""

    def __init__(self, workers: int = 10):
        self.workers = workers
        self.latencies: List[float] = []
        self.errors: List[Exception] = []

    def run_sync(self, func: Callable, requests: int, *args, **kwargs) -> StressTestResult:
        """Run synchronous load test"""
        start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = []

            for _ in range(requests):
                future = executor.submit(self._execute_request, func, args, kwargs)
                futures.append(future)

            for future in as_completed(futures):
                try:
                    latency = future.result()
                    self.latencies.append(latency)
                except Exception as e:
                    self.errors.append(e)

        elapsed = time.perf_counter() - start

        return self._create_result(elapsed)

    async def run_async(self, func: Callable, requests: int, *args, **kwargs) -> StressTestResult:
        """Run asynchronous load test"""
        start = time.perf_counter()

        tasks = [self._execute_async_request(func, args, kwargs) for _ in range(requests)]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                self.errors.append(result)
            else:
                self.latencies.append(result)

        elapsed = time.perf_counter() - start

        return self._create_result(elapsed)

    @staticmethod
    def _execute_request(func: Callable, args: tuple, kwargs: dict) -> float:
        """Execute single request and measure latency"""
        start = time.perf_counter()
        func(*args, **kwargs)
        return (time.perf_counter() - start) * 1000

    @staticmethod
    async def _execute_async_request(func: Callable, args: tuple, kwargs: dict) -> float:
        """Execute single async request and measure latency"""
        start = time.perf_counter()
        await func(*args, **kwargs)
        return (time.perf_counter() - start) * 1000

    def _create_result(self, elapsed: float) -> StressTestResult:
        """Create result object"""
        successful = len(self.latencies)
        failed = len(self.errors)
        total = successful + failed

        throughput = total / elapsed if elapsed > 0 else 0
        error_rate = (failed / total * 100) if total > 0 else 0

        if self.latencies:
            min_latency = min(self.latencies)
            max_latency = max(self.latencies)
            avg_latency = sum(self.latencies) / len(self.latencies)
        else:
            min_latency = max_latency = avg_latency = 0

        return StressTestResult(
            total_requests=total,
            successful_requests=successful,
            failed_requests=failed,
            duration_seconds=elapsed,
            throughput_rps=throughput,
            error_rate=error_rate,
            min_latency_ms=min_latency,
            max_latency_ms=max_latency,
            avg_latency_ms=avg_latency,
        )


class SpikeTest:
    """Simulate traffic spikes"""

    def __init__(self, baseline_workers: int = 5):
        self.baseline_workers = baseline_workers
        self.spike_workers = baseline_workers * 4  # 4x spike
        self.results: Dict[str, StressTestResult] = {}

    def run_with_spikes(
        self,
        func: Callable,
        requests_baseline: int,
        requests_spike: int,
        spike_frequency: float = 10.0,
        *args,
        **kwargs,
    ) -> Dict[str, StressTestResult]:
        """Run load test with traffic spikes"""
        # Baseline load
        simulator = LoadSimulator(workers=self.baseline_workers)
        baseline_result = simulator.run_sync(func, requests_baseline, *args, **kwargs)
        self.results["baseline"] = baseline_result

        # Wait before spike
        time.sleep(1)

        # Spike load
        simulator_spike = LoadSimulator(workers=self.spike_workers)
        spike_result = simulator_spike.run_sync(func, requests_spike, *args, **kwargs)
        self.results["spike"] = spike_result

        return self.results

    def get_spike_impact(self) -> Dict[str, float]:
        """Calculate spike impact metrics"""
        if "baseline" not in self.results or "spike" not in self.results:
            return {}

        baseline = self.results["baseline"]
        spike = self.results["spike"]

        return {
            "throughput_increase": ((spike.throughput_rps - baseline.throughput_rps) / baseline.throughput_rps * 100),
            "latency_increase": ((spike.avg_latency_ms - baseline.avg_latency_ms) / baseline.avg_latency_ms * 100),
            "error_rate_change": spike.error_rate - baseline.error_rate,
        }


class EnduranceTest:
    """Long-running endurance test"""

    def __init__(self, duration_seconds: int = 300, workers: int = 10):
        self.duration = duration_seconds
        self.workers = workers
        self.metrics: Dict[str, Any] = {}

    def run(self, func: Callable, interval_seconds: int = 1, *args, **kwargs):
        """Run endurance test"""
        start = time.perf_counter()
        request_count = 0
        error_count = 0
        latencies = []

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = []

            while time.perf_counter() - start < self.duration:
                for _ in range(self.workers):
                    if time.perf_counter() - start < self.duration:
                        future = executor.submit(self._execute_request, func, args, kwargs)
                        futures.append(future)

                # Check completed futures
                for future in list(futures):
                    if future.done():
                        try:
                            latency = future.result()
                            latencies.append(latency)
                            request_count += 1
                        except Exception:
                            error_count += 1
                        futures.remove(future)

                time.sleep(interval_seconds)

        elapsed = time.perf_counter() - start

        self.metrics = {
            "duration_seconds": elapsed,
            "total_requests": request_count,
            "errors": error_count,
            "error_rate": (
                error_count / (request_count + error_count) * 100 if (request_count + error_count) > 0 else 0
            ),
            "throughput": request_count / elapsed if elapsed > 0 else 0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
        }

        return self.metrics

    @staticmethod
    def _execute_request(func: Callable, args: tuple, kwargs: dict) -> float:
        """Execute request and measure latency"""
        start = time.perf_counter()
        func(*args, **kwargs)
        return (time.perf_counter() - start) * 1000

    def print_results(self):
        """Print endurance test results"""
        print("\n" + "=" * 60)
        print("ENDURANCE TEST RESULTS")
        print("=" * 60)

        for key, value in self.metrics.items():
            if isinstance(value, float):
                print(f"{key:20s}: {value:12.2f}")
            else:
                print(f"{key:20s}: {value:12d}")

        print("\n" + "=" * 60)


class FailureSimulator:
    """Simulate failures and recovery"""

    def __init__(self, failure_rate: float = 0.1):
        self.failure_rate = failure_rate
        self.recovery_attempts = 0
        self.successful_recoveries = 0

    def execute_with_retry(
        self,
        func: Callable,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        *args,
        **kwargs,
    ) -> bool:
        """Execute function with retry logic"""
        for attempt in range(max_retries):
            try:
                # Randomly fail based on failure rate
                if random.random() < self.failure_rate:
                    raise Exception("Simulated failure")

                func(*args, **kwargs)
                if attempt > 0:
                    self.successful_recoveries += 1
                return True

            except Exception:
                self.recovery_attempts += 1
                if attempt < max_retries - 1:
                    time.sleep(backoff_seconds * (2**attempt))

        return False

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get recovery statistics"""
        return {
            "total_attempts": self.recovery_attempts,
            "successful_recoveries": self.successful_recoveries,
            "recovery_rate": (
                self.successful_recoveries / self.recovery_attempts * 100 if self.recovery_attempts > 0 else 0
            ),
        }
