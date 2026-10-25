# Pre-data review record

The effective source/protocol freeze was created on 2026-10-25 at 06:44:39 UTC, before timing collection.

- Freeze manifest SHA-256: `f008a2a321c6729468280baa6515a04148d8786f67a55e37a3e51ba893f6cae2`.
- Informational local freeze commit: `23e8bece68c0f69c0b0e06ffbbb2f9dea142df1e`. This is a local source-preparation commit, not a commit expected to exist in the upstream repository.
- The manifest pins eight source/protocol/provenance files, including the byte-identical original framing implementation.

Independent pre-data inspection initially found two correctness gaps: a setup exception could escape before failure retention, and a self-consistent but impossible timing interval could pass the result verifier. Both were reproduced without empirical timing, fixed, tested, and refrozen before measurement. The final review passed 23 new tests both normally and with Python optimization enabled, all 34 original framing tests, the eight frozen hashes, and the unchanged 39-file upstream source-subset inventory. No result rows had been collected at that point.

This is a local source/protocol freeze and engineering review, not a public preregistration, independent replication, signed timestamp attestation, or security certification. A separate results review checks retained measurements and the report. Source/protocol changes after the effective freeze would invalidate its collection approval; no such changes are permitted for these two runs.
