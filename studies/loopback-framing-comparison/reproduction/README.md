# Household Compute

Could a household's consenting devices run a model together that none could run alone? When would sharing the work improve response time, and when would slow workers or communication make it worse?

This project studies memory, compute and communication limits through explicit calculations and single-host experiments. All participating devices are assumed to have informed consent. Physical-device and cross-host inference remain future work.

## Start here

- [Build intuition with a small offline example](docs/START_HERE.md).
- [Read the research overview](docs/RESEARCH_OVERVIEW.md) for hypotheses, controls and the evidence boundary.
- [Read the household feasibility paper](docs/HOUSEHOLD_INFERENCE_FEASIBILITY.md) for resource bounds and scaling assumptions.
- [Follow the study guide](studies/README.md) to inspect retained evidence before running an optional model experiment.

## Watch the narrated explanation

[![Narrated concept illustration](docs/animations/narrated/poster.png)](docs/animations/narrated/concept.mp4)

[58.8-second narrated MP4](docs/animations/narrated/concept.mp4) · [Complete transcript](docs/animations/narrated/transcript.txt) · [Captions](docs/animations/narrated/captions.vtt) · [Editable source and reproduction](docs/animations/narrated/RENDERING.md)

Speech-led Manim animation with a synthetic stock voice. Calculated assumptions · not device or model measurements. This is an explanatory upgrade, not a new experimental result. Captions have approximate sentence timing. The [static-first viewer](docs/animations/narrated/index.html), poster and complete transcript provide a no-motion alternative. The original silent version and its historical QA remain unchanged below.

## Watch the concept in 24 seconds

[![An analytical one-token serial graph shows increasing communication time as stage count grows. Under declared link assumptions, 16 stages give an optimistic communication-only ceiling of 2.511 tokens per second, not an achieved rate.](docs/animations/poster.png)](docs/animations/concept.mp4)

[24-second Manim MP4](docs/animations/concept.mp4) · [Optional GIF preview](docs/animations/concept.gif) · [Text transcript](docs/animations/transcript.txt) · [Captions](docs/animations/captions.vtt)

Rendered with Manim Community 0.22.0. Calculated assumptions · not device or model measurements. No audio. The poster and transcript provide a no-motion alternative. The downloaded [HTML viewer](docs/animations/index.html) is static by default and never autoplays.

## What is established

**The household scenarios are calculations.** [Device exemplars and capacity scenarios](HOUSEHOLD_ATLAS.md) document 14 cited devices, explicit memory baskets and 27 model-capacity cases. Available memory, supported kernels and effective links must be measured before a scenario describes a real household. Reusable smart-fridge capacity is still unknown.

**A small pretrained model was split correctly on one host.** The [local-process studies](PROCESS_EXPERIMENT.md), [repeated timings](REPEATED_EXPERIMENT.md) and [pretrained split results](PRETRAINED_RESULTS.md) test execution and accounting with private pipes and, where specified, injected communication delays.

**Transport choices changed outputs.** In [216 retained transport measurements](studies/transport-codecs/TRANSPORT_RESULTS.md), FP16 preserved next-token argmax on all 12 fixed diagnostic prefixes; the tested global-scale INT8 codec preserved none. This is a narrow codec diagnostic, not a language-quality benchmark.

**Cached decoding matched the reference, with overhead.** Two [36-row retained runs](studies/cached-decode/CACHED_RESULTS.md) reproduced full-vocabulary FP32 logits and greedy tokens exactly. Split median decode was slower. A full reference model, duplicated embedding/head weights and audit traffic prevent a total-memory-saving claim.

The [TCP framing codec](studies/tcp-framing-codec/README.md) has synthetic tests and byte accounting. It implements neither sockets nor model execution; its forecasts are not TCP measurements.

## Run

Python 3.10+ standard library only, from the repository root:

```sh
python -m unittest discover -s tests -v
python -m mesh simulate examples/illustrative.json
python -m mesh benchmark --size 64 --iterations 20 --repeats 5
```

The last two commands print JSON. Redirect to a new file to retain your own output. Simulation rates and device budgets in the example are invented assumptions. The benchmark measures a pure-Python matrix-vector kernel; its operation rate cannot be used as an LLM token-rate estimate. Optional pretrained studies require their separately documented runtime and pinned local weights.

## Read the limits correctly

Model parameter count describes a resource budget. Capability requires separate task measurements; fitting a larger model does not establish greater intelligence. Pooling memory also leaves per-device placement, runtime workspace, KV caches, critical-path latency and communication costs to solve.

The baseline requires `consent: true` for selected devices. That field exercises placement logic; actual deployment needs owner enrollment, authenticated peers, encrypted transport, resource quotas and revocation. The root program has no device discovery or network listener. [The overview](docs/RESEARCH_OVERVIEW.md) and [feasibility paper](docs/HOUSEHOLD_INFERENCE_FEASIBILITY.md) distinguish safe test design from a deployed consent system.

The next empirical step is a bounded, authenticated cross-host comparison with the best measured single-device placement, reporting latency, throughput, memory, quality and energy separately. Original code and documentation are [MIT licensed](LICENSE); external models and sources retain their own terms.

## Bounded placement study

[Placement certificates, complete scenario grid and reproduction](studies/bounded-placement-certificates/README.md) test the gap between aggregate memory and per-device placement. An expressly synthetic 43.616 GiB envelope needs 12 modeled devices/stages in the baseline four-home inventory; small per-stage reserves can make the placement impossible despite aggregate slack. This is assumption-conditional capacity/connectivity analysis, not deployment validation. The stage-count-first solver can choose a slower path than greedy: fewer stages are not a latency guarantee.
