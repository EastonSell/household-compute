# Finite FP32 validation candidate: pre-data package

This additive study follows the [retained serialization-overhead study](../serialization-overhead/README.md) published at [`ce945115`](https://github.com/EastonSell/household-compute/commit/ce945115f7fcf8f4da559cc5026d8a0157b5fa7d). The earlier observations identified finite-value validation as a plausible local optimization target. They did not establish an optimized implementation or a speedup.

**Current status: correctness tested; timing and allocation collection not started.** Independent review of the exact frozen implementation and protocol is required before collection. There is no optimization result to report yet.

## One candidate, one bounded change

[`candidate_codec.py`](candidate_codec.py) is an isolated copy of the unchanged framing codec. The only functional change is the finite FP32 predicate used by `Frame.validate`; a readable [source diff](CANDIDATE_DIFF.patch) exposes the entire change.

On hosts whose native C float format is IEEE little-endian, the candidate uses `all(map(math.isfinite, memoryview(tensor).cast('f')))`. This removes the original scan's per-element singleton tuples and Python generator frame. It still constructs Python floats, invokes `isfinite`, and traverses the whole tensor when values are finite. The view does not rewrite payload bytes. Avoided tuple/generator work is a mechanism hypothesis, not a measured latency or total allocation reduction.

A native view is not an endian-neutral decoder. The candidate checks both `sys.byteorder` and the interpreter's reported native C float format. Big-endian or unknown formats use the original explicit `struct.iter_unpack('<f', tensor)` path. This preserves the wire's little-endian semantics without claiming an optimization on those hosts. The fallback has been forced in tests on this host; actual big-endian hardware has not been tested.

Header validation, opcode and token checks, payload size/type checks, error precedence, decoder fragmentation, session behavior, I/O accounting, and all other codec code stay unchanged. Audit slicing and full-frame copies stay in both implementations. This is not a production replacement or deployment.

## Correctness evidence

The 13 candidate tests include:

- 262,144 structured FP32 patterns covering every upper 16-bit word with four lower-word boundaries, through both the selected native path and forced portable fallback; 4,096 additional fixed-seed full-width draws. An integer exponent-bit oracle supplies the expected classification. This is not an exhaustive test of all 2^32 patterns.
- Positive/negative zero, subnormals, normal boundaries, largest finite values, signed infinity, and quiet/signaling NaN payloads; nonfinite words at the first, middle and last positions of activation and audit tensors.
- Exact packed-byte and decoded-payload parity, every two-chunk split of a 2,368-byte activation frame, byte-at-a-time delivery, and coalesced surplus handling.
- Invalid header/body/token/error cases, incomplete EOF, and terminal decoder state.
- All 34 unchanged original codec contract tests executed against the candidate, including session and callback I/O behavior.

Test-first construction observed the unimplemented predicate fail its finite/nonfinite classification tests before implementation. The complete new-study suite passes 49 tests normally and under `python -O`. The benchmark and independent verifier use synthetic clocks/samplers in tests, not retained observations; a full synthetic runner output is checked by the independent verifier. Strict per-batch 180-second boundaries and on-disk freeze/preservation gates are covered.

The original framing suite passes 34 tests. The prior serialization study suite passes 23 tests. The root suite discovers 65 tests: 62 pass and 3 optional model tests are skipped. Root regression tests include their pre-existing tiny kernel benchmark smoke tests, which are not this candidate experiment. Test-runner durations are not experimental evidence.

## Planned comparison

See the fixed [protocol](PROTOCOL.md) for the adjacent, balanced baseline/candidate pairs across the same four payload sizes and three operations: finite scan, full-frame pack, and full-frame decode. Allocation observations are a separate phase with tracing disabled throughout latency collection. Traced peak and retained bytes describe live traced memory, not total allocator churn, RSS, resident model memory, or memory saved by distributed inference.

No sockets, endpoint, model execution, installations, credentials, paid resources, or cross-host work are involved. There is no household throughput, energy, device, quality, security, or deployment claim. Two invocations on one cloud host would remain one-host evidence, not independent hardware replication.

## Verification and reproduction

From this directory, run the new correctness/accounting/verifier suite without collecting observations:

```sh
python -m unittest -v
python -O -m unittest -v
```

Original tests, from the repository root:

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s studies/tcp-framing-codec -v
(cd studies/serialization-overhead && python -m unittest -v)
```

The [pre-data manifest](PRE_DATA_SHA256.json) freezes the exact protocol, candidate, runner, verifier and tests. [Baseline inventory](BASELINE_PRE_DATA.json) covers every one of the 62 already-tracked files present in this local source-subset checkout. All earlier frozen source and result packages are unchanged. This checkout does not contain the whole remote repository, and no full-repository verification is claimed.

Do not run the measurement CLI until independent pre-data review admits this exact freeze. Any pre-data revision requires a new freeze and review. After data exists, preserve it and use a newly labeled study/version for changes; never overwrite failed or inconvenient evidence.
