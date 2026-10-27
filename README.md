# Household Compute

## Abstract

Pooling device memory does not by itself make a distributed model feasible or fast. This project combines analytical placement bounds, synthetic capacity examples and single-host model/transport experiments to separate those constraints. The published loopback experiment found lower complete delivery-and-acknowledgement latency after a narrow frame-validation change: all eight case/run paired-median candidate/baseline ratios were **0.256–0.612**. Earlier cached split decoding reproduced the reference outputs exactly but was slower. These results establish bounded placement counterexamples and a local message-exchange improvement—not faster inference, memory savings or useful model deployment across real household devices.

## Research question

**Under the stated placement and communication assumptions, why is aggregate memory insufficient—and can a finite-value validation change reduce complete local message-exchange latency without changing the frame contract?**

The motivating question is broader: could a household's consenting devices run a useful model together that none could run alone, and when would sharing improve response time? The released studies answer parts of the placement/communication problem, not that deployment question.

## Methods and evidence scope

- **Analytical and synthetic placement:** explicit memory budgets, per-stage reserves, allowed logical transfers and bounded placement certificates. These are assumptions and calculations, not measured household resources.
- **Single-host model studies:** local worker processes, private pipes and, where specified, injected delays; separate checks of output correctness, timing and resource accounting.
- **Latest transport study:** two fixed runs on one host, two Python processes and one persistent TCP loopback connection with one frame in flight. Four fixed synthetic payload cases compare the original framing codec with a finite-FP32-validation candidate; both endpoints use the selected variant. These are not measured model activations or cross-host tests.

## Answer and results

**Aggregate memory does not guarantee a valid per-device placement; the selected validation change did reduce complete delivery-and-ACK latency in the tested loopback cases while preserving accepted frame bytes and decoded frames.** Neither result establishes a faster or more capable household model. Read the [measured results and figure](RESULTS.md) for the latest empirical answer and its full denominators.

### Complete local message exchange improved

Across the [two retained loopback runs](studies/loopback-framing-comparison/RESULTS.md), all eight case/run paired-median candidate/baseline latency ratios were below one, ranging from **0.255694 to 0.611762** (rounded **0.256–0.612**). The study retained **160 measured batch rows, 80 pairs and 1,600 exchanges**; 32 warmup exchanges and the eight-exchange untimed canary are separate and excluded.

Each reported ratio is the **median of ten per-block candidate/baseline batch-mean latency ratios**. Each batch contains ten exchanges. It is not a ratio of pooled medians or a throughput measure; the two runs are reported separately, with no population-effect or confidence-interval claim.

Timing includes validation/packing, loopback delivery, receiver decoding and exact-frame equality, ACK return/validation, deadline checks and completion bookkeeping. Setup, warmups and cleanup are excluded. Because both endpoints change together, the result does not isolate sender, receiver or network-speed improvements. See the [protocol and reproduction boundary](studies/loopback-framing-comparison/README.md).

The earlier [TCP framing codec](studies/tcp-framing-codec/README.md) alone has synthetic tests and byte accounting but implements neither sockets nor model execution. The **later loopback study does use actual TCP sockets**; it still performs no model inference or household-network experiment. Its isolated candidate is not a production replacement.

### Placement and earlier model results constrain the claim

- **Placement, not just total memory, matters.** The [bounded placement study](studies/bounded-placement-certificates/README.md) uses an expressly synthetic 43.616 GiB envelope requiring 12 modeled devices/stages in its baseline four-home inventory. Adding 256 MiB reserve per used stage makes that surrogate impossible despite aggregate slack. Its stage-count-first solver can choose a slower path than greedy: fewer stages do not guarantee lower latency. The separate [cycle-capacity bound](studies/cycle-capacity-bound/README.md) is a necessary, not sufficient, condition in its stated one-stage-per-device feedback model; logical transfer edges must not be confused with physical links.
- **A small pretrained model was split correctly on one host.** The [local-process studies](PROCESS_EXPERIMENT.md), [repeated timings](REPEATED_EXPERIMENT.md) and [pretrained split results](PRETRAINED_RESULTS.md) test execution and accounting, not a deployed mesh.
- **Cached decoding matched the reference, with overhead.** Two [36-row retained runs](studies/cached-decode/CACHED_RESULTS.md) reproduced full-vocabulary FP32 logits and greedy tokens exactly, but split median decode was slower. A full reference model, duplicated embedding/head weights and audit traffic prevent a total-memory-saving claim.
- **Transport choices changed outputs.** In [216 retained transport measurements](studies/transport-codecs/TRANSPORT_RESULTS.md), FP16 preserved next-token argmax on all 12 fixed diagnostic prefixes; the tested global-scale INT8 codec preserved none. This is a narrow codec diagnostic, not a language-quality benchmark.

## Check the saved results first

Python 3.10+ and the standard library suffice. From the repository root:

```sh
python -B studies/loopback-framing-comparison/verify_publication.py
python -B tools/plot_loopback_results.py --check
python -B -m unittest discover -s tests -p 'test_plot_loopback_results.py' -v
python -O -B -m unittest discover -s tests -p 'test_plot_loopback_results.py' -v
```

These commands verify retained evidence or run synthetic figure regressions. **They open no sockets, launch no receivers, run no models and collect no timing observations.** The publication verifier checks the study's complete public inventory and provenance; the figure checker independently rebuilds all 128 summary statistics from the 160 raw rows and checks the retained CSV, results table and deterministic SVG. Passing these checks establishes consistency of this saved package, not independent experimental replication or household efficacy.

For a new empirical replication, follow the study's [reproduction limits](studies/loopback-framing-comparison/README.md#reproduction-limits): use a new source freeze and admission, and never overwrite historical result paths. Optional pretrained studies require their separately documented runtime and pinned local weights.

## Limits and open question

Two loopback runs on the same host do not establish population effects. Balanced order does not remove scheduling, cache, CPU-frequency or system-load effects. Real-device latency, concurrent throughput, end-to-end model quality, energy and total-memory benefits remain unestablished by the loopback result.

Model parameter count describes a resource budget. Capability requires separate task measurements; fitting a larger model does not establish greater intelligence. Pooling memory also leaves per-device placement, runtime workspace, KV caches, critical-path latency and communication costs to solve. The [household atlas](HOUSEHOLD_ATLAS.md) documents 14 cited devices and 27 capacity cases, but available memory, supported kernels and effective links must be measured before a scenario describes a real household. Reusable smart-fridge capacity is still unknown.

All participating devices are assumed to have informed consent. The baseline requires `consent: true` for selected devices; that field exercises placement logic, not actual consent enforcement. Deployment would need owner enrollment, authenticated peers, encrypted transport, resource quotas and revocation. The root program has no device discovery or network listener; the separate loopback experiment is not a deployed consent system.

**Open question:** can a bounded, authenticated cross-host system outperform the best measured single-device placement on a useful workload? Answering it would require separate latency, throughput, memory, quality and energy measurements. It remains outside the completed released study set, not a conclusion supplied by these calculations or local tests.

## Explore the project

- [Build intuition with a small offline example](docs/START_HERE.md).
- [Read the research overview](docs/RESEARCH_OVERVIEW.md) for hypotheses, controls and the evidence boundary.
- [Read the household feasibility paper](docs/HOUSEHOLD_INFERENCE_FEASIBILITY.md) for resource bounds and scaling assumptions.
- [Follow the study guide](studies/README.md) to inspect retained evidence before running an optional model experiment.

For optional exploration, these standard-library commands print JSON:

```sh
python -m mesh simulate examples/illustrative.json
python -m mesh benchmark --size 64 --iterations 20 --repeats 5
```

The simulation uses invented rates and device budgets. The benchmark collects fresh timings of a pure-Python matrix-vector kernel; its operation rate cannot be used as an LLM token-rate estimate. Redirect to a new file to retain your own output. The broader `python -m unittest discover -s tests -v` suite includes process/timing tests and is distinct from the saved-only checks above.

## Watch the narrated explanation

[![Narrated concept illustration](docs/animations/narrated/poster.png)](docs/animations/narrated/concept.mp4)

[58.8-second narrated MP4](docs/animations/narrated/concept.mp4) · [Complete transcript](docs/animations/narrated/transcript.txt) · [Captions](docs/animations/narrated/captions.vtt) · [Editable source and reproduction](docs/animations/narrated/RENDERING.md)

Speech-led Manim animation with a synthetic stock voice. Calculated assumptions · not device or model measurements. This is an explanatory upgrade, not a new experimental result. Captions have approximate sentence timing. The [static-first viewer](docs/animations/narrated/index.html), poster and complete transcript provide a no-motion alternative. The original silent version and its historical QA remain unchanged below.

## Watch the concept in 24 seconds

[![An analytical one-token serial graph shows increasing communication time as stage count grows. Under declared link assumptions, 16 stages give an optimistic communication-only ceiling of 2.511 tokens per second, not an achieved rate.](docs/animations/poster.png)](docs/animations/concept.mp4)

[24-second Manim MP4](docs/animations/concept.mp4) · [Optional GIF preview](docs/animations/concept.gif) · [Text transcript](docs/animations/transcript.txt) · [Captions](docs/animations/captions.vtt)

Rendered with Manim Community 0.22.0. Calculated assumptions · not device or model measurements. No audio. The poster and transcript provide a no-motion alternative. The downloaded [HTML viewer](docs/animations/index.html) is static by default and never autoplays.

Original code and documentation are [MIT licensed](LICENSE); external models and sources retain their own terms.
