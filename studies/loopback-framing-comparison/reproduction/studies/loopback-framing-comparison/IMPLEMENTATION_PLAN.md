# Loopback comparison implementation plan

Goal: prepare a standard-library, hash-frozen two-process framing comparison for independent pre-data review, without opening sockets or taking timing observations.

1. Write socket-free tests for deadline retry/EOF/backward clocks, loopback address validation, owned-child normal/escalated cleanup and admission. Use deterministic scripted sockets/select/clock and fake Popen so no test can open a socket or signal a real PID.
2. Implement deadline_adapter.py with nonblocking absolute-deadline operations and owned-child cleanup. Preserve the baseline codec and accepted candidate unchanged.
3. Write fixture/schedule/row-accounting tests and fake-clock timing-boundary tests, then implement benchmark.py. Include only fixed schedules, bounded exclusive output, strict admission and a separate canary mode.
4. Write independent artifact-verifier rejection tests using synthetic artifacts, then implement verify_results.py without importing measured code.
5. Run this suite in normal and optimized Python plus existing source-only codec/finite/serialization suites. Run root suite only after checking it cannot violate the pre-admission socket prohibition; otherwise mark unrun, not passed.
6. Inventory historical files, freeze source/protocol/tests, retain red/green evidence and all failures. Return candidate manifest and exact future commands to the designated reviewer; do not collect or publish.
