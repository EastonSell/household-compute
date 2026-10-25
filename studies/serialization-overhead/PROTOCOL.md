# Single-host framing-cost controls: pre-data protocol v1

Status: prospective protocol. Timing collection requires source freeze and independent review. This is a bounded, standard-library, single-process benchmark, not a socket, network, mesh, model, inference, energy, or device experiment. Historical studies remain unchanged.

## Question and chosen approach

Measure the local cost of constructing and validating the existing binary frames, using identical deterministic payload bytes for every applicable operation at a given size. Existing framing source is `../tcp-framing-codec/mesh_codec.py` at upstream commit `9e3215eebf92a3a4ae3f74275494cc754a45c06b`. Its Python finite-float scan, packing, copying, and decoder behavior are included where the operation says so. This adds measurements for an unmeasured local component without opening a listener or suggesting real mesh throughput.

Alternatives considered: real TCP would add transport and supervision gates; a JSON comparison would confound representation and validation semantics. Neither is included. Controls below describe distinct operations, not an additive decomposition. No timing is subtracted from another to estimate a pure component.

## Fixed inputs and operations

Four cases, all synthetic and preconstructed outside timing:

| Case | Kind / metadata | Tensor floats | Payload bytes | Frame bytes |
| --- | --- | ---: | ---: | ---: |
| activation_decode | ACTIVATION_RESULT, stage 0, TOKEN, prior 1, length 1 | 576 | 2,304 | 2,368 |
| activation_prefill_16 | ACTIVATION_RESULT, stage 0, TOKEN, prior 0, length 16 | 9,216 | 36,864 | 36,928 |
| activation_prefill_64 | ACTIVATION_RESULT, stage 0, TOKEN, prior 0, length 64 | 36,864 | 147,456 | 147,520 |
| audit_reply | AUDIT, stage 1, AUDIT, prior 1, length 1 | 49,152 | 196,612 | 196,676 |

All frames use run ID bytes 0..15, epoch 0, sequence 1. Tensor element i is `((i % 257) - 128) / 128`, exactly representable finite binary32, packed little-endian. Audit prepends token ID 7 as unsigned big-endian. Values are not model activations or a representative activation distribution. SHA-256 of each payload and frame is retained. Each frame must pass an untimed exact pack/decode round trip before collection, and every operation is checked before and after its timed batches.

Six operations per case:
- `noop`: Python function call and loop floor, returning None.
- `payload_copy`: `memoryview(payload).tobytes()`, a new full-payload copy; no validation.
- `header_pack`: existing `Header.pack()`, including header validation; no body.
- `finite_scan`: same `all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', tensor))` predicate as the codec; excludes the audit token prefix and does no framing.
- `frame_pack`: existing `Frame.pack()` on the preconstructed frame, including finite-float validation, repeated header validation, and frame allocation.
- `frame_decode`: a new existing `Decoder()` per call consuming the whole prepacked frame in one chunk, including copies, parsing, and structural/finite validation. No Session gate, transcript execution, fragmentation, sockets, or blocked-I/O cancellation.

Different operations intentionally do different amounts of work. A frame decoder versus copy ratio does not isolate validation cost. The binary32 payload already exists before `frame_pack`; this is not Python-number-to-wire tensor conversion or JSON serialization.

## Fixed collection and retention

Two consecutive full runs, each a fresh Python invocation, labeled run-001 and run-002. Within each run: 5 untimed warmup operations per case/operation; 9 timed blocks; 50 iterations per batch. Each block contains all 24 case/operation cells once in an order shuffled by a local `random.Random(20261025)` instance, sequentially across blocks. The complete schedule is retained. No adaptive iteration selection, early success stopping, outlier filtering, retiming individual rows, or replacement of a slower run.

For each of the 216 rows per run retain case, operation, block, order index, iteration count, wall `perf_counter_ns` batch duration, CPU `process_time_ns` batch duration, and derived per-operation durations. Calls return normally; the last result is retained until timing ends and validated outside the interval. Payloads, functions, expected bytes, and schedule are prepared outside timing. Batch durations include Python iteration/call overhead and allocation/reclamation within the interval; garbage collection is left in its existing state and reported. No affinity, governor, process priority, environment, or security setting is changed.

Each run records UTC start/end, Python version/implementation, platform/kernel/machine, logical CPU count, readable Linux CPU model and cgroup CPU quota when available, timer implementations/resolutions, GC state/thresholds, source hashes, config, and payload hashes. Do not record hostnames, usernames, environment-variable values, or filesystem paths. CPU quota is context, not a capacity guarantee. A new exclusively created run directory contains `journal.jsonl` (metadata, flushed rows, terminal event) and `result.json` (the complete or failed record). Existing evidence must never be replaced. Ordinary failures retain partial rows and failure status; abrupt kill may leave only a partial journal and must not be treated as success. Flush is not an fsync or power-loss durability guarantee. No silent retry as success.

## Analysis, validity, and stopping

The complete expected grid is verified from raw rows before reporting. Reject missing/duplicate rows, non-finite/negative/zero timings, booleans masquerading as numeric values, mismatched source/config/input hashes, inconsistent derived statistics, wrong order, or malformed evidence. A separate monotonic interval spans each run's setup through finalization and must be positive and below 180 seconds. Reject batch durations over the run budget or summed batch wall durations exceeding that monotonic run interval. Also require the sum to fit the UTC run interval plus a fixed 1 ms timestamp tolerance. A clock discontinuity causing inconsistency invalidates the run rather than permitting adjustment. Recompute median, min, max, and inclusive-quartile IQR from 9 wall-time per-operation observations for each case/operation; CPU-time summary is separate. Report both runs, all sizes, and all controls. No p-values, confidence intervals, significance claims, or pooled pseudo-replicates: repeated batches and runs share one host and correlated system conditions.

Stop after the two valid fixed runs, or on a failed integrity/correctness/resource gate. Record failure without deleting evidence. A nonpositive wall or CPU batch duration aborts the run; there is no adaptive retry or timer-resolution tuning. Each run has a 180-second cooperative wall-time budget checked before/after warmup and each batch; this is not an interrupt of a single blocked operation or a hard OS resource cap. Each output file is capped at 4 MiB; the fixed grid is far smaller. Test-only fake clocks may establish accounting behavior, but must not generate retained empirical observations. No timing collection occurs in unit tests. Maximum retained timing rows are 432, with no tensors or per-iteration records in the result files. No installations, paid resources, credentials, endpoints, external mutation, inference, child processes, or network access by this benchmark.

## Engineering and verification plan

1. Add test-first deterministic fixture and operation validation, schedule, summaries, exclusive output, frozen-source gate, and result-validator behavior. Tests use fake clocks for runner accounting; no empirical timing data before freeze.
2. Implement the small runner and independent raw-row verifier; run new tests, all root tests, and the original framing tests. Disclose optional skips separately.
3. Freeze protocol, runner, verifier, tests, and original framing dependency with SHA-256; record the local freeze commit outside the manifest (informational chronological evidence, not a self-referential source hash). Retain a pre-data and post-data SHA-256 inventory of every baseline file present in the checkout, checked against upstream Git blob hashes; no existing file may change except the study index's additive link after collection. The checkout is a source subset, not a full repository clone, and the inventory must say so. Obtain independent source/protocol review before real timings. Any pre-data revision requires a new freeze and review.
4. Collect exactly two runs; independently verify every retained row and produce a concise README with all operation/size summaries and limitations. No change to source or protocol after observing data; fixes require preserving the failed run and a newly labeled protocol/version, not relabeling.
