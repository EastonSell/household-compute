# A fully consenting household compute atlas

**Research premise: every participating device is enrolled with complete, informed consent.** Consent is not a variable being withheld in these scenarios. Earlier refusal tests are safety negative controls for software, not the research premise. No household devices were accessed for this study.

## The useful result

With an **assumed 12 GiB of simultaneously allocatable memory per household**, ideal nominal 4-bit weights for representative **8B / 70B / 405B** dense models imply memory-only lower bounds of **1 / 3 / 16 households**. Adding an explicitly illustrative runtime envelope yields **1 / 4 / 20**. These are reproducible capacity scenarios, **not a claim that those households could deliver usable inference** and not estimates of an average American home's available compute.

![Calculated household capacity](figures/household_memory_headline.svg)

The 405B result is a particularly useful distinction: 16 homes could have enough aggregate bytes for ideal weights while still lacking a feasible shard placement, runtime, network or useful token rate. The illustrative 20-home envelope is not an upper bound or guarantee.

## What US household evidence actually tells us

The US Census Bureau's 2021 ACS data, published June 2024, reports household presence of a desktop/laptop at **80.5%**, smartphone at **90.0%**, and tablet at **63.8%**. These overlapping ownership percentages do not establish counts, processor generations, available RAM or programmable accelerator access. [Census ACS-56, computer and Internet use](https://www2.census.gov/library/publications/2024/demo/acs-56.pdf)

Deloitte's Q2 2023 US survey of 2,018 consumers reports **21 connected devices across 13 types per household**. It is a dated survey average, not 21 equivalent inference workers and not a current national hardware inventory. Multiplying that count by an invented average TOPS or RAM value would be misleading. [Deloitte 2023 Connected Consumer Survey](https://www.deloitte.com/us/en/insights/industry/telecommunications/connectivity-mobile-trends-survey/2023/connectivity-mobile-trends-survey-full-report.html)

A defensible population-average compute estimate would require a representative inventory by exact hardware generation, count, accessible memory, runtime support and measured sustained workloads. Those data are not supplied by either survey. We therefore keep empirical ownership statistics separate from device exemplars and hypothetical baskets.

## Everyday devices: documented capabilities, not invented spare capacity

These 14 named exemplars are **not a population sample**. RAM below is the vendor's installed-memory label, not measured available application memory. GB, MB and KB are retained as advertised; model arithmetic separately uses binary GiB. Dedicated GPU VRAM, unified memory and MCU SRAM are not interchangeable pools. **Usable RAM and measured LLM token rate are unknown for every row.**

| Category / named exemplar | Installed memory | Documented compute / practical interpretation | Source |
|---|---|---|---|
| Laptop: MacBook Air 13-inch M4 (2025) | 16–32 GB (vendor labels) | Apple M4; 10 cores. Strong candidate for measured local model worker | [Vendor](https://support.apple.com/en-us/122209) |
| Desktop GPU: GeForce RTX 4060 desktop graphics card (2023) | 8 GB (vendor labels) | NVIDIA Ada Lovelace; Host CPU unspecified. Strong candidate; do not count GPU VRAM twice as host RAM | [Vendor](https://www.nvidia.com/en-us/geforce/news/ultimate-guide-to-4060/) |
| Phone: Google Pixel 9 (2024) | 12 GB (vendor labels) | Google Tensor G4; Not quantified by cited specification. Potential compact-model worker while charging; thermal and battery limits | [Vendor](https://support.google.com/pixelphone/answer/7158570?hl=en) |
| Tablet: iPad Pro 11-inch M4 (2024) | 8–16 GB (vendor labels) | Apple M4; 9 or 10 cores depending storage tier. Potential compact-model worker; not an always-on server by assumption | [Vendor](https://support.apple.com/en-us/119892) |
| Game console: Xbox Series X (2020) | 16 GB (vendor labels) | Custom AMD Zen 2 / RDNA 2; 8 cores 3.8GHz (3.6GHz SMT per launch article). Hardware-rich theoretical candidate; exclude from deployable baseline until runtime validated | [Vendor](https://news.xbox.com/en-us/2020/03/16/xbox-series-x-tech/) |
| Streaming box/stick: Fire TV Stick 4K Max 2nd gen (2023) | 2 GB (vendor labels) | MediaTek MT8696T; 4x ARM Cortex-A55 up to 2.0GHz. Small task candidate, not assumed LLM accelerator | [Vendor](https://developer.amazon.com/docs/device-specs/device-specifications-fire-tv-streaming-media-player.html) |
| Smart TV: Fire TV Omni QLED Series (2022) | 2 GB (vendor labels) | Not named in cited entry; ARM Cortex-A55 up to 1.5GHz. Small task candidate; not interchangeable with all smart TVs | [Vendor](https://developer.amazon.com/docs/device-specs/device-specifications-fire-tv-edition-smart-tv-na.html) |
| Router: GL.iNet Flint 2 GL-MT6000 | 1 GB (vendor labels) | MediaTek; Quad-core 2.0GHz. Coordinator or tiny task candidate; do not degrade household connectivity | [Vendor](https://www.gl-inet.com/products/gl-mt6000/) |
| NAS: Synology DS224+ | 2–6 GB (vendor labels) | Intel Celeron J4125; 4 cores. Potential CPU worker/coordinator; not desktop-GPU equivalent | [Vendor](https://global.download.synology.com/download/Document/Hardware/DataSheet/DiskStation/24-year/DS224+/enu/DS224+_Data_Sheet_enu.pdf) |
| Smart display/speaker: Google Nest Hub 2nd gen | **Unknown** | Not named; Quad-core 64-bit ARM 1.9GHz. Theoretical hidden compute; exclude unknown memory/throughput from totals | [Vendor](https://support.google.com/googlehome/answer/7072284?hl=en) |
| Smart refrigerator: Samsung 2024 Bespoke 4-Door Flex with AI Family Hub+ | **Unknown** | Not disclosed in cited announcement; Unknown. Compelling example of embedded intelligence, not a quantified LLM resource | [Vendor](https://news.samsung.com/global/samsung-electronics-to-showcase-how-enhanced-ai-and-connectivity-enable-expansive-kitchen-experiences-at-ces-2024) |
| Network camera: AXIS M3085-V (professional camera exemplar, NOT household average) | 1,024 MB (vendor label) | CV25; Not specified in cited datasheet. Embedded vision worker example; not evidence of ordinary home-camera prevalence | [Vendor](https://www.axis.com/dam/public/fd/be/2e/datasheet-axis-m3085-v-dome-camera-en-US-417639.pdf) |
| MCU / connected sensor: ESP32-S3 SoC (not a specific appliance) | 512 KB internal SRAM; external PSRAM unknown | ESP32-S3; Dual Xtensa LX7 up to 240MHz. TinyML/vision tasks; these latencies cannot be converted into LLM token/s | [Vendor](https://www.espressif.com/en/products/socs/esp32-s3) |
| Robot vacuum: Roborock S8 MaxV Ultra | **Unknown** | Not verified; Unknown. Research gap; do not assign generic RAM/TOPS | [Vendor](https://ca.roborock.com/pages/roborock-s8-maxv-ultra) |

The fridge is a genuine computer with embedded AI, not an imaginary accelerator: Samsung documents recognition of 33 fresh-food categories, but does not establish spare RAM, processor throughput or a validated arbitrary-model interface in that announcement. “Unknown/uncredited” is not zero physical capability. A consenting fridge, vacuum, camera or router might contribute small independent workloads, local preprocessing or coordination instead of large-model weight shards. The camera exemplar is a professional AXIS device, not a claimed typical home camera.

Apple advertises 38 trillion operations/s for the M4 Neural Engine; the cited announcement does not state enough precision/sparsity detail to normalize it into dense FP32 FLOPS. Xbox GPU TFLOPS and NPU TOPS must not be added or treated as measured LLM throughput. [Apple M4 announcement](https://www.apple.com/newsroom/2024/05/apple-introduces-m4-chip/)

There is also real tiny-device inference evidence: Espressif reports ESP32-S3 vision inference of **123.4 ms** for ESPDet-Pico at 224×224 and **26,057.1 ms** for YOLO11n at 640×640, plus separate preprocessing/postprocessing. The source does not establish the exact precision or PSRAM configuration. These are **vision workload measurements**, not LLM tokens/s or proof of fitting the entire task into bare 512 KB SRAM. [Espressif official comparison, retrieved October 22, 2026](https://esp32-s31.espressif.com/en/official-projects/6)

Full per-device evidence includes processor, memory type, advertised versus measured scope, power caveats, runtime-access limitations, source date and URLs: [JSON](data/household/device_evidence.json), [CSV](results/household/device_atlas.csv). Published adapter/gaming/nameplate power is not incremental inference power.

## Three device-informed baskets, not household averages

| Assumed allocatable budget | Illustrative inventory | Assumed contribution |
|---|---|---|
| 4 GiB | One 8 GB M1 MacBook Air (2020) | Laptop contributes 4 GiB |
| 12 GiB | One 16 GB M4 MacBook Air (2025), two 12 GB Pixel 9 phones | Laptop 8 GiB + phones 2 GiB each |
| 24 GiB | One 32 GB M4 MacBook Air, two 12 GB Pixel 9 phones | Laptop 16 GiB + phones 4 GiB each |

Installed capacities are documented by [Apple M1 Air](https://support.apple.com/en-us/111883), [Apple M4 Air](https://support.apple.com/en-us/122209), and [Google Pixel specifications](https://support.google.com/pixelphone/answer/7158570?hl=en). Counts, chosen configurations and allocated **GiB** budgets are analyst assumptions, not measured free memory, application limits, a conversion of vendor GB labels, wealth percentiles or Census-derived distributions. Other consenting electronics remain uncredited pending technical evidence. We do not silently give each appliance positive capacity or assert zero capability. [Machine-readable basket definitions](data/household/household_baskets.json)

## Reproducible capacity arithmetic

For rounded parameter count `P`, nominal weight bits `q`, and allocatable household budget `B` bytes:

- Ideal weight bytes: `W = P × q / 8`.
- Weight-only lower bound: `ceil(W / B)`.
- FP16 KV cache: `2 × layers × KV_heads × head_dimension × context_tokens × batch × 2 bytes`.
- Separate illustrative envelope: `ceil((1.20 × W + KV + 2 GiB) / B)`.

Model dimensions come from **Llama 3.1 8B/70B/405B**, not a claim about today's state-of-the-art model. All three have eight KV heads and head dimension 128; layer counts are 32/80/126. At context 8,192 and batch one, FP16 KV is 1 / 2.5 / 3.9375 GiB. The 20% weight overhead and 2 GiB aggregate workspace are declared assumptions, **not measured runtime requirements** or per-device reserves. [Meta paper, Table 3](https://arxiv.org/html/2407.21783v3#S3.T3)

| Model | 4-bit floor / envelope | 8-bit floor / envelope | 16-bit floor / envelope |
|---|---:|---:|---:|
| 8B | 1 / 1 | 1 / 1 | 2 / 2 |
| 70B | 3 / 4 | 6 / 7 | 11 / 14 |
| 405B | 16 / 20 | 32 / 39 | 63 / 76 |

All entries above assume **12 GiB per household**. Full 27-case sensitivity:

![Precision and memory sensitivity](figures/household_capacity_sensitivity.svg)

The 4–24 GiB range is a scenario sensitivity, not a confidence interval. Nominal 4-bit storage excludes actual format metadata: llama.cpp's Q4_K encoding uses 4.5 bits/weight, and real files can mix tensor types. Lower bits do not guarantee preserved model quality or supported fast kernels. The illustrative 20% multiplier does not validate any particular quantized artifact. [llama.cpp encoding documentation](https://github.com/ggml-org/llama.cpp/wiki/Tensor-Encoding-Schemes)

### Recent methods do not turn capacity into guaranteed quality or speed

NVIDIA's January 2026 quantization-aware distillation work reports model-specific quality recovery using a quantized student and BF16 teacher, targeting its evaluated Nemotron/Blackwell setup. That is not a guarantee for arbitrary household hardware. NVFP4 stores 4-bit values plus block scales, already about 4.5 bits/value before the per-tensor scale/alignment. [NVIDIA QAD research](https://research.nvidia.com/labs/nemotron/nemotron-qad/), [NVFP4 technical description](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/)

The 2025 MDI-LLM paper studies recurrent pipeline parallelism across edge devices and multiple independent sequences. It motivates further experiments, not linear single-sequence acceleration. A real study must specify checkpoint, weight/activation/KV formats, calibration or recovery training, accuracy evaluation, runtime kernels and measured sustained latency. [MDI-LLM original paper](https://arxiv.org/html/2505.18164v1)

## Why more memory can still mean slower interaction

![Communication-only sensitivity](figures/household_communication_sensitivity.svg)

This is a **hypothetical single-sequence, serial contiguous-layer pipeline**, with one stage per home and `H−1` boundaries. For a 70B hidden width of 8,192, one FP16 activation vector is 16 KiB. At every boundary we assume the same payload bandwidth `R` in **bytes/second** (Mbps × 1,000,000 / 8) and one-way latency `L` in seconds:

`communication_seconds_per_token = (H−1) × (L + 16384 / R)`

The reciprocal is only a **communication-derived token-rate ceiling under this topology**, not measured or predicted throughput. At 16 households and the assumed 20 Mbps/20 ms setting, that ceiling is about **2.51 tokens/s before any computation**. The three link settings are hypothetical, not US broadband statistics. The plot stops at 64 stages, below the model's 80 layers; extending whole-layer staging beyond the available layers would be invalid. Intra-home transfers, compute, serialization, token return, contention, jitter, losses, encryption and recovery can lower the actual rate. Tensor parallel collectives and multi-sequence batching need different models.

The CSV also includes an 8,192-token **nonstreaming whole-prompt store-and-forward** communication calculation. It is not a universal prefill lower bound: chunked/streamed prefill changes overlap and latency.

A real research anchor is Petals: Table 2 reports 2.29 sequential steps/s for Llama 2 70B NF4 on three 16 GB T4 GPUs with a single client, sequence length 128, 100 Mbit/s and RTT below 5 ms, versus 1.57 at RTT 100 ms. These are specified research conditions, not measured fridge/phone households. [Petals original paper, Table 2](https://arxiv.org/html/2312.08361v1#S4.T2)

## What would establish practical household inference?

1. Verify every assigned shard, local KV and workspace fits a specific addressable pool. Aggregate bytes are a necessary check, not sufficient placement. Do not double-count unified memory or assume NPU allocations equal all system RAM.
2. Benchmark supported operators, prefill and decode on exact devices, with sustained thermals and household duties preserved. Complete consent does not supply missing manufacturer APIs or accelerator kernels.
3. Measure real boundary transfers under contention, disconnects and re-enrollment. Independent necessary-node availability would be `a^k`; real outages may be correlated and need a measured joint model. Common-mode failures can defeat redundancy. Full consent does not mean 100% uptime.
4. Evaluate model quality after quantization and compare against a monolithic reference. Measure energy per token as incremental whole-system watts divided by sustained tokens/s, not appliance nameplate wattage.

Until those steps exist, the graphs answer **“How much memory would this explicit scenario require?”**, not **“How many average homes will serve this model well?”**

## Reproduce and inspect

The calculator and tables need only Python 3.10+ standard library:

```sh
python -m mesh.household_report
python -m unittest discover -s tests -v
```

Charts additionally use matplotlib and NumPy (already present in the development environment; no package installation was performed for this atlas). With those optional packages available:

```sh
python -m mesh.household_charts
```

Renderer tested with matplotlib 3.10.8 and NumPy 2.3.5; this is not a fresh-install compatibility claim. Published SVGs and locally generated PNGs come from the same computed rows, not illustrative image generation. [Capacity CSV](results/household/memory_scenarios.csv), [capacity JSON](results/household/memory_scenarios.json), [communication CSV](results/household/communication_scenarios.csv), [communication JSON](results/household/communication_scenarios.json), [source assumptions](data/household/scaling_assumptions.json).

Evidence flags are field-scoped: device `advertised` describes vendor specifications; the ESP32 `measured` flag applies only to its cited vision benchmark. Scenario rows are `assumed`, not measured household performance. Null device capabilities mean unknown. All sources were checked October 22, 2026; living pages and unknown publication dates are labeled instead of invented. Existing local process and pretrained experiments remain separate, actual single-machine measurements, not validation of household-network performance.
