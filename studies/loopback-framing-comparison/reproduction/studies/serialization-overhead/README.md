# Single-host framing-cost controls

This additive study measures a local component the [source-only framing codec](../tcp-framing-codec/README.md) did not measure: the cost of copying, scanning, constructing, and decoding its synthetic binary frames. It opens no socket and runs no model. It does not alter the original codec or any historical result.

## Main result

On this one cloud host, validating/packing a 2,304-byte activation payload took about 38.5–38.8 microseconds per operation at the two run medians; decoding took 45.2–45.9 microseconds. At the 196,612-byte audit payload, packing took 2.84–3.09 milliseconds and decoding 2.91–3.08 milliseconds. A full-payload copy measured about 0.21 microseconds and 4.03 microseconds respectively.

The finite-float scan control was on the same scale as full-frame packing/decoding for the larger payloads. This identifies a plausible local validation optimization target, not a measured optimization, pure network overhead, or a performance guarantee. The controls are not an additive decomposition, and no component time is estimated by subtraction.

[Full results](RESULTS.md) report all four payload sizes, all six operations, both runs, wall and CPU medians, ranges, and IQRs. [Raw run 1](results/run-001/result.json) and [raw run 2](results/run-002/result.json) retain all 432 planned batch observations with input/source hashes, schedule, and environment. Their adjacent journals retain the corresponding metadata and row events. Both runs completed on the first attempt; no outlier removal, adaptive changes, or retries occurred.

## What was controlled

- Exactly the same finite, deterministic FP32 payload bytes at a given size; no random tensors, model weights, or downloads.
- Four payloads: 2,304; 36,864; 147,456; and 196,612 bytes, with a 64-byte frame header.
- Six operations: no-op loop/call floor, fresh payload copy, validated header pack, finite-float scan, validated full-frame pack, and full-frame decode with a new decoder.
- Two fresh Python invocations; each used 5 untimed warmups per cell, 9 shuffled full-grid blocks, and 50 iterations per timed batch. The schedule seed was fixed before collection.
- Untimed exact-output checks before and after each batch, distinct wall/CPU timers, exclusive output creation, partial-failure journals, a cooperative 180-second run budget, and 4 MiB/file limits.

These are warm, preconstructed-byte measurements. Payload construction, number-to-binary conversion, model operations, session checks, fragmentation, sockets, and network transfer are outside scope. Repeated batches and the second invocation are not independent hosts or workloads. The synthetic finite values do not represent measured activation distributions.

## Environment and evidence

Collected 2026-10-25 06:46:28–06:46:44 UTC on CPython 3.12.14, Linux 6.18.55, x86_64. The reported CPU model was AMD EPYC 9V74 80-Core Processor; Python reported 9 logical CPUs. The cgroup CPU quota file was unavailable, so no effective capacity or exclusive-core claim is made. GC remained enabled. No affinity, governor, priority, or security setting was changed. Clock metadata reports 1 ns resolution, not proven accuracy. Monotonic run durations were 8.022907 and 8.331949 seconds.

The [protocol](PROTOCOL.md), runner, verifier, tests, and original codec dependency were [hash-frozen](PRE_DATA_SHA256.json) before collection and independently reviewed. [Review history](REVIEW.md) records pre-data fixes and the evidence boundary. This was a local source freeze, not public preregistration or independent replication.

The independent artifact verifier reconstructs wire bytes without importing the codec or benchmark, checks the complete planned grid, verifies every derived timing and summary, compares the journal, and rejects impossible timing totals against the recorded monotonic interval. Hashes provide consistency, not proof that timings were genuinely observed or a security signature.

## Reproduce or verify

Use an existing Python 3.10+ standard-library runtime. From this directory:

```sh
python -m unittest -v
python verify_results.py results/run-001 results/run-002
```

To collect the same fixed study on another host, choose two fresh output directories; the commands refuse to overwrite existing evidence:

```sh
python benchmark.py --run-id run-001 --output YOUR_NEW_RUN_1
python benchmark.py --run-id run-002 --output YOUR_NEW_RUN_2
python verify_results.py YOUR_NEW_RUN_1 YOUR_NEW_RUN_2
```

The reproduction commands run local CPU work only. Do not relabel another host's observations as these retained runs. Leave failed output directories intact. A changed frozen source file must be reviewed/refrozen as a new study before collection, not used to overwrite these results.

## Verification scope

The 39 baseline files present in the source-subset checkout matched the upstream Git blobs at `9e3215eebf92a3a4ae3f74275494cc754a45c06b` before and after collection. This was not a full repository clone; no claim is made to rerun every historical study. All existing repository files are left untouched, including the historical study index and publication inventory.

The new suite has 23 passing tests, including fake-clock accounting, failure durability, bounded/exclusive outputs, malformed/duplicate/boolean evidence rejection, journal matching, and impossible timing detection. Root suite: 65 discovered, 62 passed and 3 optional model tests skipped. Original framing suite: 34 passed. A skip is not an executed pass. Test durations are test-runner logs, not experimental data.

No household throughput, network latency, speedup, memory saving, task quality, energy efficiency, or deployment safety is established. A useful next engineering step is a separately frozen, semantics-preserving finite-validation optimization comparison, retaining all malformed/nonfinite rejection behavior.
