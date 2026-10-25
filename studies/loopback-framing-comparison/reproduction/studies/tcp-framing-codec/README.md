# Consent compute mesh: source-only binary protocol slice

Status: standard-library codec and deterministic in-memory tests only. No sockets, process manager, model loading, inference, installation, or external mutation. Existing studies are not modified. This is not authorization to execute the proposed TCP/model study.

## Files and use

- `mesh_codec.py`: immutable numeric frames, 64-byte header, bounded decoder, controller-relay transcript state machine, directed byte ledger, and callback-only read/write loops.
- `test_mesh_codec.py`: deterministic synthetic unit tests; run `python -m unittest -v` in this directory.
- `TEST_RESULTS.txt`: actual retained test output.
- `SUPERVISION_DESIGN.md`: prospective direct-three-child manager; not implemented or executed.

Protocol choices filling unspecified constants in the proposal: magic `CMTP`, version 1, stage 0/1, mode TOKEN=1/AUDIT=2, kind and error-code numeric values as declared by the closed enums. Wire integers are unsigned big-endian; tensor bytes are contiguous little-endian FP32. Header flags and reserved bytes are always zero. These assignments must be frozen with the source before any interoperating implementation or measurements.

HELLO/READY, RESET/ACK and STOP/ACK are serialized stage0 then stage1, a deliberate stricter ordering than the proposal requires. STOP echoes the current epoch, last committed sequence and cache length with input length zero. ERROR echoes outstanding request metadata, or current committed metadata with length zero when idle; its code is closed and terminal. No arbitrary error text goes on wire.

## Integration contract

`Session` checks the entire relay transcript, not a worker's local cache implementation. Invoke its header gate before buffering a received body, then `accept` after the entire frame validates. For outbound frames, accept/validate the intended transcript step before transmission; any failed or uncertain send must poison the session. A local stage must separately validate its controller-facing state and commit its actual cache only on successful execution; that worker implementation remains a gate. The transcript validator never proves a cache was cleared or inference was correct.

Example receive wiring: construct `Decoder(lambda h: session.check_header(h, 'response'), session.fail)`, call `read_frame`, then `session.accept(frame, 'response')`. Catch failures at the operation boundary, call `session.fail`, and settle pending ledger transfers as failed. No reset/retry after failure. Controller global sequence/cache commits only on the accepted stage1 reply; both reset ACKs are required before global reset commit. Relay activation bytes must be identical and decode inputs must equal the previously accepted token.

`Decoder.consume` accepts arbitrary fragmentation, returns one frame and the number of input bytes consumed, and leaves coalesced surplus with the caller. It never accumulates a frame queue. Header identity/state/length validation happens before body buffering. Its persistent buffer is capped at one maximum frame. Temporary bounded copies exist during frame validation and serialization; this is not an allocation-free codec or a whole-process memory bound. Empty feed is not EOF; `eof()` is terminal unless the transport already completed normal shutdown and is no longer reading.

`read_frame` and `write_frame` take pure callbacks and the same absolute deadline across header, body and every partial transfer. They count positive actual transfers even if the callback returns after the deadline, then fail. They cannot interrupt a blocked callback. The eventual adapter must enforce absolute deadline/cancellation while blocked; simulated late callbacks are not proof of socket cancellation. Invalid callback return counts are integration failures, not plausible traffic accounting.

The ledger has fixed directed-link keys: c0 (controller to stage0), 0c, c1 and 1c. Actual sent/received counts are distinct; delivered totals use receive counts only. Settle all pending transfers as inference only after a complete paired operation commits, lifecycle after a complete lifecycle operation, or failed on any failure. Reconcile only finalized complete evidence; unmatched sent/received counts are retained and fail reconciliation. This is application-byte accounting, not TCP/IP or Wi-Fi wire accounting. No per-frame log queue or measurements are implemented here.

## Test coverage and remaining gates

The retained result currently contains 34 passing unittest methods (with additional deterministic subcases). These establish synthetic codec/state/accounting behavior, not network performance or full proposal acceptance.

Covered: all header offsets and fixed bounds; invalid enums/flags/reserved fields; header gate before body; one-byte fragmentation; every split of a token frame; coalesced frames; short-header/body EOF; token limits; nonfinite activation/logit rejection; mode-specific replies; stage/run/cache/epoch/sequence validation; sequence/epoch overflow; exact response echo; unchanged activation relay; greedy-token chaining; two-ACK reset and replay; failed reset; terminal STOP/ERROR/external failure; partial transfers; deadline expiry across header/body and after validation; failure-byte retention; send/receive reconciliation; and analytical 4,872-byte token versus 201,480-byte audit decode forecasts.

Not implemented or established:

1. Actual loopback socket adapter, literal-address validation, peer/listener controls, TCP_NODELAY, blocked-I/O cancellation and real absolute deadline behavior.
2. Worker-local state/cache execution and invalid-request rejection before computation; model/reference exactness, argmax correctness, token-chain reference equality, full-logit byte equality and retained replay/cross-run gates. Finite audit logits are accepted structurally; the codec does not assert token = argmax.
3. Application pacing S1/S2, requested/achieved timing records, timing decomposition and retained per-frame evidence.
4. Direct-three-child supervisor, identity-safe termination, final wait4 accounting, resource guards, evidence budgets, failure durability and independently checked acceptance manifest.
5. Independent source review/freeze, separately bounded real-I/O tests and canary authorization, model canary authorization, and retained eight-session batch authorization. Unit success is not permission to advance these gates.

The implementation uses only the Python standard library and has no model dependency.
