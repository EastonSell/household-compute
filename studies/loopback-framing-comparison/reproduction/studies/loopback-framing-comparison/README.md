# Two-process loopback framing comparison

Prepared additive experiment, not collected results. It compares the unchanged baseline codec to the exact accepted finite-validation candidate at both ends of one loopback TCP connection. There are no network, mesh, household-device or model performance findings yet.

Read PROTOCOL.md for the exact outcome boundary, complete denominators, pairing, byte accounting, bounds and limitations. IMPLEMENTATION_PLAN.md is the preparation checklist. PRE_DATA_SHA256.json binds the reviewable candidate. BASELINE_INVENTORY.json preserves all 92 previously tracked files in this source-subset checkout. The published context commit and the local source-subset commit are deliberately distinguished.

## Safe preparation tests

Run from the repository root. These tests use fake clocks, scripted in-memory sockets and fake owned children. They do not open sockets, spawn receiver processes or collect empirical timing observations.

```
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s studies/loopback-framing-comparison -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -O -m unittest discover -s studies/loopback-framing-comparison -p 'test_*.py' -v
```

The historical codec, serialization-overhead and finite-validation-optimization suites are also source-only/fake-clock correctness checks. The root tests are NOT run at this preparation checkpoint because some invoke real process/timing experiments. This is a scoped preparation pass, not a complete root-suite pass. Red preparation logs are retained: initially missing implementation modules, two corrected fake-driver fixture expectations, and a genuine close-error cleanup bug caught by a new test before fixing. That bug could skip child cleanup on socket-close failure; the corrected driver attempts cleanup despite a close error and rejects the run. Additional retained red checks cover late syscall-byte retention, partial failure evidence, cleanup exhaustion, terminal-journal failure, and strict numeric schema rejection. None of these are empirical failures or timing observations.

## Separate admission checkpoints

No admission receipt is bundled. Only after independent pre-data review, the designated reviewer can create a canary receipt with exactly schema=1, stage="canary", freeze_sha256 equal to the SHA-256 of PRE_DATA_SHA256.json. The runner rejects absent, mismatched or wrong-stage admission before any socket creation.

The future canary command, from the repository root, is:

```
python -B studies/loopback-framing-comparison/benchmark.py --mode canary --admission REVIEWER_CANARY_ADMISSION.json --output studies/loopback-framing-comparison/canary-001
python -B studies/loopback-framing-comparison/verify_results.py --canary studies/loopback-framing-comparison/canary-001
```

After separate review of that canary, the designated reviewer can create a collection receipt with exactly schema=1, stage="collection", freeze_sha256 and canary_result_sha256. The canary must have exited cleanly and verified completely. Merely obtaining a canary result is not collection approval.

Only after that second admission:

```
python -B studies/loopback-framing-comparison/benchmark.py --mode run-001 --admission REVIEWER_COLLECTION_ADMISSION.json --canary-result studies/loopback-framing-comparison/canary-001/result.json --output studies/loopback-framing-comparison/run-001
python -B studies/loopback-framing-comparison/benchmark.py --mode run-002 --admission REVIEWER_COLLECTION_ADMISSION.json --canary-result studies/loopback-framing-comparison/canary-001/result.json --previous-result studies/loopback-framing-comparison/run-001/result.json --output studies/loopback-framing-comparison/run-002
python -B studies/loopback-framing-comparison/verify_results.py studies/loopback-framing-comparison/run-001 studies/loopback-framing-comparison/run-002
```

Run the second measurement command only when the first returned zero and its evidence is intact. Each command refuses an existing output directory. Do not retry a failed observation, replace an outlier, edit source after canary or publish before reviewed results. The authoritative performance denominator is 160 rows / 1,600 acknowledged measured exchanges across two runs, with 32 warmup exchanges and 8 canary exchanges reported separately.

## Resource and inference limits

Only literal 127.0.0.1, an ephemeral port, one owned receiver and one driver. Standard library, two Python processes at most, no installations/configuration/credentials, no external endpoints. Work deadline 85 seconds and operational gate 90 seconds per invocation, with at most three one-second cleanup waits. These are user-space operational bounds, not hard OS containment. Final terminal-journal/result writes occur after the retained elapsed gate and are bounded by file size, not a timed syscall guarantee. File failure or abrupt process death may leave incomplete evidence. Never call an unreaped child or partial journal success.

Each run sends approximately 76.7 MB of measured application frame bytes plus 12,800 ACK bytes, with warmup and control bytes separately accounted. These are application counts, not TCP/IP wire bytes. The largest frame is 196,676 bytes. Each artifact is capped at 1 MiB; there are three per invocation. Fixed payload objects and codec buffers are small, but Python/OS memory is not capped or measured.

One-host descriptive batch-latency summaries cannot establish internet/LAN throughput, household suitability, model speed, energy efficiency, concurrent service rate or distributed memory savings. Both ends change together. Receiver equality checks and ACK work are part of the measured operation, not a transport-only cost. Independent verification proves internal consistency and hash custody, not a malicious producer's honesty.
