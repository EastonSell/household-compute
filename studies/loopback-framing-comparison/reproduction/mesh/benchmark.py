"""Real Python CPU matvec microbenchmark, NOT a device/inference benchmark."""
import platform
import statistics
import sys
import time


def benchmark(size=64, iterations=20, repeats=5):
    for name, value, limit in [('size', size, 512), ('iterations', iterations, 10000), ('repeats', repeats, 100)]:
        if type(value) is not int or not 1 <= value <= limit:
            raise ValueError(f'{name} must be an integer between 1 and {limit}')
    # Deterministic normalized values; initialization is excluded from timing.
    matrix = [[((row + col) % 17 - 8) / (size * 8) for col in range(size)] for row in range(size)]
    vector = [(index % 7 - 3) / 7 for index in range(size)]

    def run():
        output = []
        for _ in range(iterations):
            output = [sum(a * b for a, b in zip(row, vector)) for row in matrix]
        return sum(output)

    run()  # Warm-up, not included in samples.
    samples = []
    checksum = 0.0
    for _ in range(repeats):
        start = time.perf_counter()
        checksum = run()
        samples.append(time.perf_counter() - start)
    operations = 2 * size * size * iterations
    median = statistics.median(samples)
    return {
        'kind': 'local_cpu_measurement',
        'kernel': 'pure_python_dense_matvec',
        'python': sys.version.split()[0],
        'implementation': platform.python_implementation(),
        'machine': platform.machine(),
        'size': size, 'iterations': iterations, 'repeats': repeats,
        'samples_seconds': samples, 'median_seconds': median,
        'operations_per_sample': operations,
        'operation_count_convention': '2 scalar operations per multiply-accumulate; excludes Python overhead',
        'median_ops_per_second': operations / median,
        'checksum': checksum,
        'scope': 'This process only; not measured model inference, GPU throughput, ESP32, or network throughput.',
    }
