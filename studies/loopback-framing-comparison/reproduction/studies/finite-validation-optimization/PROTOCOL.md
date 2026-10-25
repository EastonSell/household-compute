# Paired finite-validation optimization: pre-data protocol v1

Status: prospective and frozen before observations. Collection is forbidden until source freeze, correctness tests, and independent source/protocol review pass. This is a bounded, standard-library, single-host study of local Python framing work. It opens no sockets and runs no model. All historical study files remain unchanged.

## Question, treatment, and limits

Does replacing the existing finite-binary32 predicate reduce local finite-scan, complete frame-pack, and complete frame-decode cost without changing the protocol's accepted data or output bytes?

Baseline is the unchanged `../tcp-framing-codec/mesh_codec.py`, preserved in published commit `ce945115f7fcf8f4da559cc5026d8a0157b5fa7d`, with SHA-256 `3fcb2b2dffd7d95e56d4887ce02a63482ff612b4a7c0313e9fbcb715a419b5aa`. Its finite scan is `all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', tensor))`. The candidate is a separate complete codec module, not a monkey patch of baseline. Its only functional change is a finite-scan helper: `all(map(math.isfinite, memoryview(tensor).cast('f')))` when `sys.byteorder == 'little'` and the Python native float format is `IEEE, little-endian`; otherwise the original explicit little-endian tuple/generator predicate is used. Both module identities and native-format selection are recorded or checked. Helper inputs here are aligned contiguous tensor bytes already valid in length.

The fallback is portability protection, not evidence of the native optimization. If either run reports the fallback path, results must be labeled fallback-host measurements and cannot support a native-path speedup claim. The study does not remove validation, change wire precision, or substitute real model data. The method still creates Python float values; it is not zero-allocation processing. Complete framing results include any helper dispatch overhead introduced by the candidate. Isolated scan functions use symmetric one-helper-call wrappers for the two predicates.

No result from this study establishes TCP throughput, cross-host behavior, model inference speed, device suitability, energy use, RSS reduction, or cumulative allocation churn. Negative results and mixed size/operation outcomes are reported, not filtered. No subtraction of controls estimates a pure subsystem cost.

## Exact inputs and work

The same four preconstructed payloads as the prior serialization-overhead study are used:

| Case | Tensor floats | Payload bytes | Frame bytes | Metadata |
| --- | ---: | ---: | ---: | --- |
| activation_decode | 576 | 2,304 | 2,368 | ACTIVATION_RESULT, stage 0, TOKEN, prior 1, length 1 |
| activation_prefill_16 | 9,216 | 36,864 | 36,928 | ACTIVATION_RESULT, stage 0, TOKEN, prior 0, length 16 |
| activation_prefill_64 | 36,864 | 147,456 | 147,520 | ACTIVATION_RESULT, stage 0, TOKEN, prior 0, length 64 |
| audit_reply | 49,152 | 196,612 | 196,676 | AUDIT, stage 1, AUDIT, prior 1, length 1 |

Tensor element i is `((i % 257) - 128) / 128`, packed as little-endian binary32. Every value is exactly representable and finite. Audit prepends unsigned big-endian token ID 7. Run ID is bytes 0..15, epoch 0, sequence 1. Payload and full-wire SHA-256 and byte lengths are retained and independently reconstructed by the verifier. These synthetic values are neither measured activations nor a representative activation distribution.

For each case and each independently imported codec:

- `finite_scan`: scan the tensor bytes only, excluding the audit token prefix; return exactly True.
- `frame_pack`: call the preconstructed frame's existing pack method; include full body validation, header validation, and wire allocation.
- `frame_decode`: construct a fresh decoder and consume one complete prepacked wire frame; include copies, parsing, structural validation, and finite validation. Require exact consumed length and the expected variant's exact Frame type and value.

The two frame objects share the very same immutable payload object. Baseline wire bytes are the expected output for both codecs. Fixture construction includes exact pack/decode checks for both. Every sampled operation is checked immediately before measurement and its retained final return value is checked after measurement. No assertion statement implements a correctness or integrity gate, so optimized Python does not remove gates. No Session execution, fragmentation, network, I/O cancellation, tensor-number-to-wire conversion, or JSON representation comparison is timed.

## Fixed paired schedule and collection

Exactly two consecutive full runs, `run-001` then `run-002`, each launched in a fresh Python process. A random process-instance identifier is created when the runner module is imported and retained. The run-set verifier requires different identifiers, ordered run labels, nonoverlapping UTC intervals, identical environment metadata, and the same freeze. This detects accidental same-module-instance reuse but is not an OS attestation or proof of identical physical hardware.

Each run has 5 untimed warmup calls per case/operation/variant, then all latency samples, then all allocation samples. No tuning or adaptive phase is permitted.

Latency: 10 blocks, 50 calls per timed batch, 12 case/operation pairs per block, two variants adjacent within each pair. A fixed cell index is assigned in case-major order using the table above and operation order `finite_scan`, `frame_pack`, `frame_decode`. For each block, a single local `random.Random(20261025)` shuffles the 12 cells, sequentially across blocks. Baseline is A and candidate is B. A cell uses AB when `(block + fixed_cell_index) % 2 == 0`, otherwise BA. Each cell therefore gets exactly five AB and five BA pairs. Both variants finish before another cell is sampled. Untimed correctness checks, budget checks, and journal writes occur between samples, including between pair members; adjacency does not imply an uninterrupted CPU reservation.

Allocation: after latency has finished, a separate phase uses 4 blocks and one call per sample, with the same pairing rule and a fresh `random.Random(20261026)` schedule. Every cell gets exactly two AB and two BA pairs. There are 240 latency rows and 96 allocation rows per run, 480 and 192 respectively across the two planned runs. Both full schedules are retained.

No adaptive iteration count, early success stopping, retimed rows, replacement runs, dropped outliers, selective operation omission, or post-data tuning. Stop after the two runs or the first correctness, integrity, resource, or execution failure. A failure is retained and ends this protocol version; do not silently replace a failed run with a successful retry. Any source fix after observations requires a separately labeled future protocol and preservation of the old evidence.

### Latency accounting

Use `perf_counter_ns` wall time and `process_time_ns` CPU time. Wall starts before CPU starts; CPU ends before wall ends. Both raw durations must be positive integer nanoseconds. Retain both durations, iteration count, and exact per-call divisions. Include Python loop/call overhead and within-batch allocation/reclamation. Only the last returned object is retained through timer end, validated untimed, and explicitly released before the next sample. Neither tracemalloc nor another measurement phase is active during latency. Existing tracemalloc activity makes the run fail rather than stopping a tracer owned elsewhere.

### Allocation accounting

Each one-call sample gets a fresh `tracemalloc.start(1)` session. Read baseline current/peak counters, reset peak, invoke the operation once, and read current/peak while its result is still retained. Stop tracing in a finally clause, including on ordinary operation failure. No wall or CPU latency is measured in this phase. Record raw before/current/peak byte counters, signed `retained_bytes = current - before`, and `peak_increment_bytes = max(0, peak - before)`. Require nonnegative integer raw counters, peak at least current, and exact derived deltas. Verifier permits counters only through 2^53 bytes so the byte-summary float representation remains exact at input conversion.

Retained can be negative because the measurement shim itself releases objects; peak increment can be zero. The counters include Python allocations attributable to the narrow sampling shim and result retention. They do not count every allocate/free event, do not measure process RSS, do not show native allocations outside tracemalloc coverage, and do not prove a reduction in total object churn. Fresh tracing and its overhead change execution conditions, so allocation-phase measurements never serve as latency evidence. Neither whole-process memory nor peak overlap across distributed devices is inferred.

## Retention, integrity, and resource bounds

Before collection, freeze protocol, runner, verifier, three test files, candidate codec, baseline inventory, original baseline codec, and original baseline codec tests in `PRE_DATA_SHA256.json`. Exact top-level keys: schema (integer 1), baseline_commit, frozen_at_utc (UTC-aware), and sources. The exact ten source paths are enumerated in runner and verifier. Manifest bytes receive their own SHA-256 in each result. No empirical measurements are made in tests: fake clocks and a fake tracer/sampler exercise accounting; synthetic artifacts are not observations.

`BASELINE_PRE_DATA.json` inventories all 62 tracked files present in this source-subset checkout, not a full repository clone. The runner checks every inventory member's SHA-256 and Git blob SHA-1 at setup and finalization, and the independent verifier checks them again. Unrelated baseline files cannot change unnoticed merely because the inventory file itself still hashes correctly. Baseline directories and published data remain byte-for-byte unchanged. There are no installations, credentials, endpoints, paid resources, child processes, or external mutation in this runner.

Record UTC start/end, positive monotonic elapsed seconds, Python version and implementation, platform/kernel/machine, logical CPU count, readable CPU model and cgroup CPU quota if available, timer properties, GC state/thresholds, byte order, native float format, candidate fast-path flag, and hashes. No hostname, username, environment-variable contents, or local filesystem paths are recorded. CPU quota is context, not a capacity guarantee. Leave GC, affinity, governor, priority, and environment/security settings unchanged.

Each run exclusively creates its new output directory and exclusively opens `journal.jsonl` and `result.json`. Each file is capped at 4 MiB. Journal events are start metadata, 240 latency row events, 96 allocation row events, and one terminal event. Each accepted event is flushed outside measurement. Reserve 4 KiB for ordinary failure termination. Flush is not fsync or power-loss durability. A write failure, abrupt termination, or full disk may leave only a partial journal; missing terminal/result evidence is not success. Normal exceptions retain preceding rows and failure type/phase without copying arbitrary exception messages into artifacts.

The monotonic budget spans setup through finalization. Check before and after warmups and samples; reject backward/nonfinite clocks and require final elapsed greater than zero and below 180 seconds. This is a cooperative budget, not a hard OS limit or an interrupt of one blocked operation. Individual wall and CPU batches must be below the run budget. Sum of latency wall intervals must fit within the monotonic run interval and within UTC elapsed plus 1 ms. Clock discontinuities invalidate the run rather than allowing time adjustments. Allocation-phase duration is included in the enclosing run budget but is not reported as latency. Working payloads are bounded by the four fixed fixtures; no per-iteration outputs or tensor bytes are retained in results.

## Prespecified summaries and independent acceptance

For each case/operation/variant in each run, report the median, minimum, maximum, and inclusive-quartile IQR of the 10 wall and CPU per-call observations separately. Also pair by the exact block/case/operation and summarize the 10 candidate/baseline ratios and candidate-minus-baseline differences. Ratios below one favor candidate; differences below zero favor candidate. Report paired-ratio medians, not a ratio of independently aggregated medians. Never pool 50 iterations as independent samples.

For allocation, separately summarize each variant's 4 signed retained and peak-increment observations, and the 4 paired candidate-minus-baseline byte differences. Do not form allocation ratios when baseline counters can be zero or negative. All summary values are floats, with inclusive quartiles linearly interpolated. Raw rows remain primary evidence.

The independent verifier imports neither runner nor codec. It rebuilds expected wire bytes and schedules; rejects malformed, duplicate-key, extra-field, nonfinite, bool-as-number, missing-row, duplicate-row, relabeled-pair, reordered, changed-hash, wrong-native-path, contradictory-duration, and inconsistent-summary artifacts; verifies the complete journal; and requires both planned sequential process instances for run-set acceptance. Partial/failed runs are retained but cannot pass complete-run acceptance. Verification checks internal consistency and provenance hashes, not honesty against a malicious producer.

Report both runs and every size/operation, including contrary latency and allocation findings. No p-values, significance language, confidence intervals, pooled pseudo-replicates, or population/physical-device generalization: all observations share one host and correlated conditions. AB/BA balance reduces simple order effects but does not remove cache, CPU frequency, scheduling, thermal, interpreter-specialization, or system-load effects. Two process instances are not independent hosts.

## Commands after independent freeze review

Engineering checks, with bytecode writes disabled to preserve old study trees:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s studies/finite-validation-optimization -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -O -m unittest discover -s studies/finite-validation-optimization -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s studies/tcp-framing-codec -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s studies/serialization-overhead -v
```

Only after source freeze and approval to collect, from the repository root, use new never-existing output directories:

```sh
PYTHONDONTWRITEBYTECODE=1 python studies/finite-validation-optimization/benchmark.py --run-id run-001 --output studies/finite-validation-optimization/runs/run-001
PYTHONDONTWRITEBYTECODE=1 python studies/finite-validation-optimization/benchmark.py --run-id run-002 --output studies/finite-validation-optimization/runs/run-002
PYTHONDONTWRITEBYTECODE=1 python studies/finite-validation-optimization/verify_results.py studies/finite-validation-optimization/runs/run-001 studies/finite-validation-optimization/runs/run-002
```

Run the second command only if the first succeeded and all integrity gates hold. Do not execute these collection commands while preparing or reviewing this protocol. The standalone verifier may inspect one run programmatically, but the CLI accepts exactly the planned pair and is the complete-study acceptance command.
