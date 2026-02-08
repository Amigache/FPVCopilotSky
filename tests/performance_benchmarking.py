"""
Performance Benchmarking Tools

Utilities and helpers for performance profiling and benchmarking.
"""

import time
import psutil
import json
from contextlib import contextmanager
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, asdict


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""

    operation: str
    duration_ms: float
    cpu_percent: float
    memory_mb: float
    throughput_rps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"Operation: {self.operation}\n"
            f"  Duration: {self.duration_ms:.2f}ms\n"
            f"  CPU: {self.cpu_percent:.1f}%\n"
            f"  Memory: {self.memory_mb:.2f}MB\n"
            f"  Throughput: {self.throughput_rps:.2f} req/s"
        )


class PerformanceProfiler:
    """Main performance profiler class"""

    def __init__(self):
        self.process = psutil.Process()
        self.metrics: List[PerformanceMetrics] = []

    @contextmanager
    def profile(self, operation_name: str, iterations: int = 1):
        """Context manager for profiling a code block"""
        initial_memory = self.process.memory_info().rss / 1024 / 1024

        start_time = time.perf_counter()
        start_cpu = self.process.cpu_percent(interval=0.01)

        try:
            yield
        finally:
            end_time = time.perf_counter()
            end_cpu = self.process.cpu_percent(interval=0.01)

            final_memory = self.process.memory_info().rss / 1024 / 1024

            duration = (end_time - start_time) * 1000  # ms
            memory_used = final_memory - initial_memory
            avg_cpu = (start_cpu + end_cpu) / 2
            throughput = iterations / (end_time - start_time) if duration > 0 else 0

            metrics = PerformanceMetrics(
                operation=operation_name,
                duration_ms=duration,
                cpu_percent=avg_cpu,
                memory_mb=memory_used,
                throughput_rps=throughput,
            )

            self.metrics.append(metrics)

    def measure_latency(self, func: Callable, *args, iterations: int = 10, **kwargs) -> float:
        """Measure function latency"""
        latencies = []

        for _ in range(iterations):
            start = time.perf_counter()
            func(*args, **kwargs)
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        return sum(latencies) / len(latencies)

    def measure_memory(self, func: Callable, *args, **kwargs) -> float:
        """Measure memory used by function"""
        initial_memory = self.process.memory_info().rss

        func(*args, **kwargs)

        final_memory = self.process.memory_info().rss
        return (final_memory - initial_memory) / 1024 / 1024

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        if not self.metrics:
            return {}

        total_duration = sum(m.duration_ms for m in self.metrics)
        avg_duration = total_duration / len(self.metrics)
        avg_cpu = sum(m.cpu_percent for m in self.metrics) / len(self.metrics)
        avg_memory = sum(m.memory_mb for m in self.metrics) / len(self.metrics)
        total_throughput = sum(m.throughput_rps for m in self.metrics)

        return {
            "total_operations": len(self.metrics),
            "total_duration_ms": total_duration,
            "avg_duration_ms": avg_duration,
            "avg_cpu_percent": avg_cpu,
            "avg_memory_mb": avg_memory,
            "total_throughput_rps": total_throughput,
        }

    def get_slowest(self, n: int = 5) -> List[PerformanceMetrics]:
        """Get slowest operations"""
        return sorted(self.metrics, key=lambda x: x.duration_ms, reverse=True)[:n]

    def get_most_memory_intensive(self, n: int = 5) -> List[PerformanceMetrics]:
        """Get most memory-intensive operations"""
        return sorted(self.metrics, key=lambda x: x.memory_mb, reverse=True)[:n]

    def print_report(self):
        """Print performance report"""
        print("\n" + "=" * 60)
        print("PERFORMANCE PROFILING REPORT")
        print("=" * 60)

        summary = self.get_summary()
        print("\nSummary:")
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

        print("\nSlowest Operations:")
        for i, metric in enumerate(self.get_slowest(5), 1):
            print(f"  {i}. {metric.operation}: {metric.duration_ms:.2f}ms")

        print("\nMost Memory-Intensive:")
        for i, metric in enumerate(self.get_most_memory_intensive(5), 1):
            print(f"  {i}. {metric.operation}: {metric.memory_mb:.2f}MB")

        print("\n" + "=" * 60)

    def to_json(self) -> str:
        """Export metrics as JSON"""
        return json.dumps(
            {
                "metrics": [m.to_dict() for m in self.metrics],
                "summary": self.get_summary(),
            },
            indent=2,
        )


class LatencyAnalyzer:
    """Analyze latency patterns"""

    def __init__(self):
        self.samples: Dict[str, List[float]] = {}

    def add_sample(self, operation: str, latency_ms: float):
        """Add latency sample"""
        if operation not in self.samples:
            self.samples[operation] = []
        self.samples[operation].append(latency_ms)

    def get_percentiles(self, operation: str) -> Dict[str, float]:
        """Get latency percentiles"""
        if operation not in self.samples or not self.samples[operation]:
            return {}

        sorted_samples = sorted(self.samples[operation])
        n = len(sorted_samples)

        return {
            "min": sorted_samples[0],
            "p50": sorted_samples[n // 2],
            "p95": sorted_samples[int(n * 0.95)],
            "p99": sorted_samples[int(n * 0.99)],
            "max": sorted_samples[-1],
            "mean": sum(sorted_samples) / n,
        }

    def get_all_percentiles(self) -> Dict[str, Dict[str, float]]:
        """Get percentiles for all operations"""
        return {op: self.get_percentiles(op) for op in self.samples}

    def print_analysis(self):
        """Print latency analysis"""
        print("\n" + "=" * 60)
        print("LATENCY ANALYSIS")
        print("=" * 60)

        for operation, percentiles in self.get_all_percentiles().items():
            print(f"\n{operation}:")
            for percentile, value in percentiles.items():
                print(f"  {percentile:4s}: {value:8.2f}ms")


class ThroughputBenchmark:
    """Benchmark throughput"""

    def __init__(self):
        self.results: Dict[str, Dict[str, float]] = {}

    def measure(self, name: str, func: Callable, duration_seconds: int = 5) -> float:
        """Measure throughput of function calls"""
        start = time.perf_counter()
        count = 0

        while time.perf_counter() - start < duration_seconds:
            func()
            count += 1

        elapsed = time.perf_counter() - start
        throughput = count / elapsed

        self.results[name] = {
            "requests": count,
            "duration_seconds": elapsed,
            "throughput_rps": throughput,
        }

        return throughput

    def compare(self) -> List[tuple]:
        """Compare throughput across operations"""
        sorted_results = sorted(
            self.results.items(),
            key=lambda x: x[1]["throughput_rps"],
            reverse=True,
        )
        return sorted_results

    def print_comparison(self):
        """Print throughput comparison"""
        print("\n" + "=" * 60)
        print("THROUGHPUT BENCHMARK")
        print("=" * 60)

        for name, result in self.compare():
            print(f"\n{name}:")
            print(f"  Requests: {result['requests']}")
            print(f"  Duration: {result['duration_seconds']:.2f}s")
            print(f"  Throughput: {result['throughput_rps']:.2f} req/s")

        print("\n" + "=" * 60)


class MemoryProfiler:
    """Profile memory usage"""

    def __init__(self):
        self.process = psutil.Process()
        self.samples: List[Dict[str, Any]] = []

    def take_sample(self, label: str = ""):
        """Take memory snapshot"""
        mem_info = self.process.memory_info()

        sample = {
            "label": label,
            "rss_mb": mem_info.rss / 1024 / 1024,
            "vms_mb": mem_info.vms / 1024 / 1024,
            "timestamp": time.time(),
        }

        self.samples.append(sample)
        return sample

    def get_delta(self, start_idx: int = 0, end_idx: int = -1) -> float:
        """Get memory delta between samples"""
        if not self.samples or abs(end_idx) > len(self.samples):
            return 0

        start = self.samples[start_idx]["rss_mb"]
        end = self.samples[end_idx]["rss_mb"]

        return end - start

    def print_samples(self):
        """Print memory samples"""
        print("\n" + "=" * 60)
        print("MEMORY PROFILING")
        print("=" * 60)

        for i, sample in enumerate(self.samples):
            delta = ""
            if i > 0:
                prev_mem = self.samples[i - 1]["rss_mb"]
                delta = f" ({sample['rss_mb'] - prev_mem:+.2f}MB)"

            print(f"{i+1}. {sample['label']:20s} {sample['rss_mb']:8.2f}MB{delta}")

        print("\n" + "=" * 60)
