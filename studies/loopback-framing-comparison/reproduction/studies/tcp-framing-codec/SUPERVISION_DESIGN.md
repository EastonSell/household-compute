# Three-child supervisor design (not implemented)

This is a prospective design, not a runnable manager or an acceptance claim. The existing single-worker supervisor is not imported, wrapped three times, or treated as aggregate coverage.

## Ownership and topology

A new lightweight manager directly launches and exclusively reaps exactly three trusted single-process children: controller, stage0 and stage1. Stage workers never launch descendants, and the controller never launches/reaps workers. Model work uses one compute thread per child and does not overlap reference and split computation. All executable paths, environment settings and arguments are fixed locally. Neither network input nor startup records select code, executable paths or functions.

Use one launch/reap owner and one independent wall-deadline watchdog thread within that manager. The watchdog requests cancellation from the ownership layer; it never performs an unchecked PID signal. Keep a locked registry of child role, PID, manager-parent identity, verified process-start identity, private process-group identity and unreaped/reaped state. Reject booleans/noninteger PIDs, PID <= 1, duplicate roles or duplicate identities. Do not use process-name lookup. Prefer supported pidfds for stable per-process signaling; they do not replace exclusive wait ownership. If stable identity or required accounting is unavailable, fail closed before model execution.

The owner serializes signal decisions and reaping, validates identity/ownership immediately before signaling, and never signals a reaped child or a private group after ownership loss. For the trusted no-descendant contract, signal the three direct children individually, not guessed process groups. A group kill cannot be claimed safe merely because a former child once led that group. Unexpected descendants violate the contract: record failure and do not claim whole-tree cleanup. A stronger descendant-containment solution needs a separate design and authorization.

All mocks use signal stubs that raise immediately if invoked outside a declared fake-identity registry. Fake PIDs must never reach real kill/syscall implementations.

## Retained accounting and final acceptance

Launch without a competing automatic process reaper. Only the registry owner calls wait4 for these specific child PIDs. Retain each returned raw status, decoded exit/signal status, rusage user/system CPU, maximum RSS with documented platform units, identity and reap timestamp. Do not use Popen.poll/wait or a generic waiter that consumes final status before wait4. A nonblocking wait4 loop may reap early exits only if it retains the entire result immediately. ECHILD or external reaping is lost evidence and terminal failure, not a successful cleanup.

Sum final wait4 CPU across all three model children; report manager CPU separately from its own measurements. Sample current RSS and CPU for manager plus all three known identities every 50 ms, with monotonic timestamps and missed-sample gaps. Final maximum-RSS values are per-process peaks, not a simultaneous aggregate; never call their sum a measured concurrent peak. Keep the sampled concurrent sum separately. Fail closed on missing/unusable required accounting. Final wait4 does not account for arbitrary escaped descendants.

Acceptance requires all three exact retained exit statuses, aggregate resource evidence, explicit socket closure, joined I/O threads, no owned live/unreaped children, complete output manifest, and a separate manager acceptance record bound to frozen source/protocol/model/runtime identifiers. A controller completion marker is insufficient. Missing manager evidence, accounting gaps that invalidate limits, failed publication, or incomplete cleanup means incomplete/failure, never accepted.

## Bounded startup, cancellation and shutdown

The manager supplies fixed-size local startup records; workers bind literal IPv4 127.0.0.1 ephemeral ports, validate the intended peer, send bounded ready records and close listeners. The controller connects but does not own worker lifetimes. Startup does not silently proceed from a partially ready pair. Sockets must use nonblocking operations with absolute deadlines and a cancellation wakeup, or an equivalently reviewed mechanism. The in-memory codec callback interface does not itself interrupt blocking I/O.

An independent watchdog tracks the absolute 120-second session deadline from before launch, including cleanup. Reserve the final four seconds for two seconds graceful termination and two seconds scoped escalation; do not grant a fresh cleanup allowance beyond the wall budget. Startup/model-ready deadline is 45 seconds, paired exchange deadline 10 seconds, reset/stop deadline 2 seconds, each also bounded by the remaining session budget. Model calls may not promptly observe cooperative cancellation: the manager must retain authority to terminate those owned processes while they are loading or computing. Close/cancel socket operations, request graceful exit, then escalate only against still-owned identities. Record late/incomplete cleanup honestly even if a signal was sent. Watchdog scheduling and OS termination are not real-time guarantees.

Any malformed frame, transport failure, failed computation, deadline breach, evidence failure or missing second reset ACK poisons the entire session. Never retry a computation with uncertain completion, continue one worker after the other fails, or reuse the errored session for reset. Stop the retained batch on its first unexplained failure and preserve partial evidence.

## Operational budgets, not hard containment

Before launch require at least 3 GiB effective available host/cgroup memory and 512 MiB output space; document how these are established. Aggregate sampled RSS threshold: 3 GiB including manager. Model-child CPU: 90 seconds/session, 720 seconds/eight-session batch. Session evidence: 32 MiB; batch artifacts: 256 MiB; batch wall: 20 minutes. Check write budgets before each bounded artifact write and retain incremental failure evidence when possible. Do not promise records after SIGKILL, filesystem failure or power loss.

RSS/CPU sampling, user-space deadlines and filesystem checks can overshoot. Already executing model calls, buffers, allocator overhead, scheduler delays and failed cleanup can exceed forecasts. No cgroup, security, kernel, privileged network or installation changes are proposed. If genuinely hard limits or hostile-process containment are required, this design is insufficient.

## Mandatory integration tests before execution approval

Test direct-child launch failure at each role; worker/controller crash; startup timeout; blocked reads/writes; cancellation during model-load, reference and stage compute; ownership mismatch; external reap; invalid identities; accounting failure; output failure/budget exhaustion; watchdog lateness; and escalation. Verify all remaining owned children are accounted for and reaped with retained final wait4 records, without signaling unrelated processes. Freeze/review the manager and transport together before a separately bounded synthetic real-I/O canary, and separately authorize model canary and retained batch. None of those tests or executions are provided by this source-only slice.
