# Loopback framing comparison

[Results](RESULTS.md) · [Full-precision table](reproduction/studies/loopback-framing-comparison/SUMMARY.csv) · [Protocol](reproduction/studies/loopback-framing-comparison/PROTOCOL.md)

The accepted finite-validation optimization had lower paired-median complete delivery-and-ACK latency across all four fixed synthetic payloads in two retained runs. Candidate/baseline ratios ranged from 0.256 to 0.612. This extends earlier in-memory codec measurements to one two-process loopback path, not a household mesh, cross-host network, throughput or model benchmark. Both endpoints change together; their contributions are not separately isolated.

The evidence contains 160 measured rows / 1,600 measured exchanges, 32 separate warmup exchanges and an eight-exchange untimed capability canary. Every prespecified condition and raw row is retained. Both receivers exited cleanly and were reaped without escalation. The original frozen experiment and independent postrun audit passed before this public-package adaptation.

## Verify without sockets or timing

From this directory:

```
python -B verify_publication.py
python -B -m unittest test_verify_publication -v
python -B -O -m unittest test_verify_publication -v
python -B -m unittest discover -s reproduction/studies/loopback-framing-comparison -p 'test_*.py' -v
```

These commands check retained artifacts and synthetic tests only. They do not open sockets, launch receivers, run models or recollect timing data. Verification covers all 92 historical baseline files, 12 frozen source entries, 50 reviewed evidence files, exact original/public file pairs, the external admission/review chain, raw results and journals, all per-run statistics, and the reader-facing table. A complete public inventory also rejects unlisted or missing files.

## Original evidence versus public metadata

The reproduction directory is a self-contained source-subset snapshot, not the full upstream repository. It is deliberately additive and does not replace any existing repository package. All measured result/receiver/journal bytes, codec and experiment code, tests, numerical tables, historical manifests, and admission receipt bytes are unchanged.

PUBLIC_ADAPTATIONS.json documents 17 exact prose/log/review metadata derivatives: neutral reviewer/operator wording, package-relative traceback locations, and current reader-facing status/links. ORIGINAL_PUBLIC_FILE_PAIRS.json pins the original and public hashes for all 149 copied files. Neither document permits arbitrary pattern-based edits. The original private snapshot is preserved separately, including the earlier report sentence and its documented qualification after independent review. The revised report treats the smallest-frame overhead explanation as a hypothesis, not an isolated causal finding.

The original PRE_DATA_SHA256.json and POST_DATA_SHA256.json remain historical provenance. Their hashes still identify the original reviewed experiment, including its original prose bytes. They are not relabeled as a pre-data freeze of this later public editorial package. Use verify_publication.py, which validates every exact mapped original/public pair and then invokes the byte-identical independent data verifier against the original freeze identity. It does not monkey-patch that verifier or skip historical baseline checks. PUBLICATION_SHA256.json is the current public inventory, excluding itself.

Historical preparation READMEs/protocols and collection receipts describe their original checkpoint, so prospective or audit-pending wording there is historical. The review receipts under reviews/ establish the later PASS decisions. Their historical test-harness hashes are provenance; those separate review executables are not bundled here. The public verifier and its adversarial mutation tests are provided directly.

## Reproduction limits

Do not execute the historical benchmark command against this editorial derivative and mistake it for a newly approved experiment. Its original strict freeze intentionally does not accept altered prose bytes. A fresh empirical reproduction requires a separately named output/version, a newly reviewed source inventory/freeze and independent canary/collection admission. Existing result paths must never be overwritten, failed observations must not be replaced, and no synthetic result establishes real household efficacy.

The full original repository test suite was not rerun during this task because it contains other timing/process experiments. The new source-only suite passed 39 tests in both normal and optimized Python; independent guarded review ran 46. Prior source-only suites passed 34 codec tests, 49 finite-validation tests and 23 serialization tests. Skipped or unrun tests are not passes. Operational deadlines are user-space checks, not hard resource containment; final evidence writes lie outside the retained elapsed gate.
