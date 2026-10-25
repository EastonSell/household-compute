# Two-process loopback framing comparison: retained results

Status: both prespecified runs were collected, independently reconstructed and reviewed. This public-package report is an editorial status derivative; original measured artifacts and the pre-data freeze identity remain unchanged.

## Result and limits

The exact finite-validation candidate had lower paired-median complete delivery-and-ACK latency in all four synthetic payload cases in both runs. Candidate/baseline paired-median ratios ranged from 0.256 to 0.612, depending on case and run. Both sending and receiving processes used the same selected codec. This is one host, two Python processes and one persistent loopback TCP connection with one frame in flight, not household-device, mesh, cross-host, throughput, inference or model-quality evidence.

The timed operation includes per-exchange deadline/ledger setup, sender validation and frame packing, kernel loopback I/O, receiver incremental decoding and exact-frame equality, a fixed ACK return, driver ACK validation, and completion-counter/loop overhead. It excludes process/connection setup, fixtures, warmups, command/READY control messages, journal writes and cleanup. Neither timing subtraction nor a transport-only cost is reported.

## Prespecified medians

Latency values below are microseconds per exchange, obtained from ten-exchange batch means. Each variant/case/run has ten batch observations. Ratio and difference columns are medians of the ten paired values, not ratios or differences of independently aggregated medians.

| Run | Synthetic case | Baseline median µs | Candidate median µs | Paired candidate/baseline median | Paired difference median µs |
| --- | --- | ---: | ---: | ---: | ---: |
| run-001 | activation_decode | 178.178 | 104.301 | 0.611762 | -69.683 |
| run-001 | activation_prefill_16 | 1293.231 | 440.392 | 0.336393 | -877.537 |
| run-001 | activation_prefill_64 | 4789.260 | 1287.464 | 0.267633 | -3493.225 |
| run-001 | audit_reply | 6353.349 | 1610.679 | 0.255694 | -4751.858 |
| run-002 | activation_decode | 148.707 | 74.523 | 0.534605 | -72.678 |
| run-002 | activation_prefill_16 | 1276.082 | 387.576 | 0.307109 | -866.876 |
| run-002 | activation_prefill_64 | 4872.223 | 1334.752 | 0.274522 | -3559.103 |
| run-002 | audit_reply | 6879.637 | 1737.276 | 0.263573 | -5092.691 |

Full precision medians, minima, maxima and inclusive IQRs for each prespecified statistic are retained in SUMMARY.csv and each result.json. Raw rows and ordered journals remain primary evidence. The maximum baseline prefill-64 batch mean in run-001 was 8,768.768 µs per exchange and is retained, not removed or replaced.

## Denominator and byte accounting

- Exactly two runs in the frozen order, run-001 then run-002. The first run passed standalone artifact verification before the second began.
- Each run: 80 measured rows, 40 adjacent pairs, 800 measured exchanges and 16 separately retained warmup exchanges. Each case has five AB and five BA pairs.
- Across the study: 160 measured rows, 80 pairs, 1,600 measured exchanges and 32 warmup exchanges. The eight-exchange untimed capability canary is separate and contributes no latency observation.
- Each run: 76,698,400 measured frame bytes and 12,800 measured ACK bytes; warmups add 1,533,968 frame bytes and 256 ACK bytes.
- Each run: 744 driver control/handshake bytes and 720 receiver control/handshake bytes. Total driver send/receive is 78,233,112 / 13,776 bytes; receiver receive/send is exactly the same.
- These are application bytes observed by send/recv, not TCP/IP packet or network-wire traffic.
- No empirical failures, retries, replacement runs, discarded rows or adaptive iteration changes occurred. Historical preparation failure tests remain retained, but are not observations.

## Correctness, custody and lifecycle

- Exact baseline codec SHA-256: 3fcb2b2dffd7d95e56d4887ce02a63482ff612b4a7c0313e9fbcb715a419b5aa.
- Exact candidate SHA-256: 0cde18f73e790b7e7f600bf1dc25f6a9059e2a6289396584698bee0f6e77a58b.
- Frozen manifest SHA-256: c8367af12ccb2434ea5a15d6f3fe162e521994768c74e75c98eb40b4b4c68f65.
- Both runs selected the native little-endian IEEE FP32 candidate path. The accepted frame bytes and exact decoded frames matched throughout.
- Both receiver processes exited with status zero and were reaped without termination or kill requests. There were no in-flight commands or recorded cleanup errors at completion.
- Independent artifact verification reconstructs payload/frame hashes, ordered denominators, per-command and total byte counts, paired summaries, receipt chain, complete journals and clean child lifecycle records.
- All 92 historical baseline files, scientific code, raw observations and numerical summaries are byte-identical. Three frozen prose files in the public snapshot are exact mapped editorial derivatives, not unchanged original bytes. The original 12-entry freeze remains provenance, and the exact original archive is preserved separately.

## Interpretation

The observed reduction carries through this particular loopback delivery-and-ACK path, extending the earlier in-memory codec measurement without establishing a broader systems result. Synthetic payloads are fixed finite values, not measured model activations or a representative workload. Both endpoint codecs change together; sender and receiver contributions are not separately identified. ACK/equality/accounting work remains part of the endpoint. The smaller reduction for the smallest frame could reflect a greater proportional contribution from fixed overhead or scheduling; this study does not isolate that explanation.

Runs are reported separately. They share one host and correlated conditions, and do not establish population effects. AB/BA balance does not eliminate scheduling, cache, CPU-frequency, interpreter specialization, temperature or system-load effects. No p-values, confidence intervals, significance language, cumulative allocation, RSS, energy or concurrent throughput claims are made.

Operational bounds are user-space checks, not hard OS containment. The final terminal-journal/result writes are bounded in bytes but lie after the retained elapsed gate. The successful clean reaps support these particular invocations, not arbitrary hostile-child containment.

## Evidence

- reproduction/studies/loopback-framing-comparison/PROTOCOL.md and its PRE_DATA_SHA256.json: frozen questions, exact boundary, controls and analysis.
- reproduction/studies/loopback-framing-comparison/canary-001/: admitted untimed capability result, receiver result and journal.
- reproduction/studies/loopback-framing-comparison/run-001/ and run-002/: raw measured rows, all warmup commands, receiver accounting and ordered journals.
- reproduction/studies/loopback-framing-comparison/SUMMARY.csv: complete prespecified numerical summaries without rounding.
- reproduction/studies/loopback-framing-comparison/COLLECTION_RECEIPT.json: exact result/source/review/admission hashes and execution order.
- PUBLICATION_SHA256.json: current public inventory. Original POST_DATA_SHA256.json remains historical provenance; PUBLIC_ADAPTATIONS.json explains the exact mapped prose/log derivatives.
