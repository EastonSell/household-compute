# Retained finite-validation comparison

This post-data report supersedes the status statements in the unchanged [pre-data package README](README.md). That README, its source freeze, and all other pre-data artifacts are deliberately preserved as historical records.

## Observed result

On this one CPython 3.12.14 cloud host, the candidate had lower paired median wall time in every planned size/operation cell in both runs. The change retained finite-value rejection and wire-byte behavior in the executed correctness tests; it was not integrated into the original codec.

| Operation | Range of paired candidate/baseline wall-median ratios across the eight run/case cells | Corresponding observed reduction |
| --- | ---: | ---: |
| finite_scan | 0.243–0.258 | 74.2%–75.7% |
| frame_pack | 0.250–0.355 | 64.5%–75.0% |
| frame_decode | 0.254–0.409 | 59.1%–74.6% |

These ranges span separately reported run/case summaries. They are not confidence intervals or pooled independent samples. Ratios below one favor the candidate; ratios are summarized from matched blocks, not calculated by dividing marginal medians.

For the 2,304-byte activation payload, baseline frame-pack medians were 39.7–40.7 µs and candidate medians 13.4–14.4 µs; decode was 44.0–44.4 µs versus 17.6–17.9 µs. For the 196,612-byte audit payload, pack was 3.040–3.045 ms versus 0.757–0.805 ms; decode was 3.051–3.119 ms versus 0.799–0.800 ms. These are the two run medians, not a broader device range.

**Allocation evidence is much narrower than the latency change.** Every paired retained-byte delta was zero. Peak traced-byte deltas were either zero or minus eight bytes: minus eight for isolated scans and audit frame pack/decode, zero for the activation frame pack/decode cases. No meaningful payload-scale live-memory saving or reduction in total allocation churn is established.

## Collection and integrity

Exactly two planned fresh-process invocations ran, sequentially, on 2026-10-25. Both completed on the first attempt. There were no retries, replacement runs, discarded observations, post-data changes to the frozen implementation or protocol, or adaptive settings. Each invocation retained 240 latency and 96 separate allocation rows: 480 latency plus 192 allocation observations total. [Collection receipt](COLLECTION_RECEIPT.json) records commands and process outcomes; [verifier output](VERIFICATION_RESULTS.json) covers the full pair.

The exact implementation and [protocol](PROTOCOL.md) were frozen at 2026-10-25T07:49:54.072204+00:00, before collection, and independently passed technical pre-data review. Freeze SHA-256: `5053f3212d4469f69b3d59110153646d2eada24d4153f2b312f6ab9d8c595e89`. This is a local source freeze, not public preregistration, cryptographic attestation, or independent hardware replication.

The 180-second internal limit is cooperative and its monotonic accounting ends before terminal journal/result-file writes. Each actual invocation also had an external GNU timeout supervisor configured to send SIGKILL at 190 seconds; neither limit fired. A forced termination could leave only partial evidence and would not count as success. Output files are limited to 4 MiB each; journals flush ordinary progress but do not provide power-loss durability.

Both runs reported Linux 6.18.55, x86_64, AMD EPYC 9V74 80-Core Processor, CPython 3.12.14, nine logical CPUs and IEEE little-endian native floats. The native candidate path was active in both. Cgroup CPU quota was unavailable, so effective capacity and exclusive-core availability are unknown. GC stayed enabled at thresholds 700/10/10. Affinity, governor, priority and security settings were unchanged. Reported timer resolution was 1 ns, not demonstrated timing accuracy.

## Complete latency and paired summaries

Each variant cell has ten batch observations, each batch containing 50 calls. Values below are `median / inclusive-quartile IQR / minimum–maximum`. Marginal wall and CPU times are µs per call. Paired ratios are dimensionless; paired differences are candidate minus baseline in µs per call. Negative differences favor the candidate. No observations are removed.

### run-001

UTC: 2026-10-25T07:55:42.012430+00:00 to 2026-10-25T07:55:54.014150+00:00. Internal monotonic interval: 12.001735 seconds. [Raw result](runs/run-001/result.json) · [Journal](runs/run-001/journal.jsonl).

| Case | Operation | Variant | Wall µs: median / IQR / min–max | CPU µs: median / IQR / min–max |
| --- | --- | --- | ---: | ---: |
| activation_decode | finite_scan | baseline | 34.976 / 6.175 / 32.786–50.185 | 34.955 / 6.166 / 32.761–50.157 |
| activation_decode | finite_scan | candidate | 8.731 / 0.333 / 8.012–11.080 | 8.720 / 0.327 / 8.005–11.057 |
| activation_decode | frame_pack | baseline | 40.671 / 2.788 / 37.110–51.494 | 40.643 / 2.793 / 37.090–51.463 |
| activation_decode | frame_pack | candidate | 14.357 / 1.773 / 12.778–17.830 | 14.333 / 1.770 / 12.768–17.808 |
| activation_decode | frame_decode | baseline | 44.035 / 8.033 / 41.235–59.355 | 44.008 / 7.771 / 41.219–59.326 |
| activation_decode | frame_decode | candidate | 17.930 / 3.328 / 15.781–39.835 | 17.905 / 3.304 / 15.769–39.795 |
| activation_prefill_16 | finite_scan | baseline | 565.689 / 31.994 / 520.239–686.144 | 565.568 / 32.071 / 520.190–686.058 |
| activation_prefill_16 | finite_scan | candidate | 140.796 / 4.387 / 125.673–151.182 | 140.768 / 4.392 / 125.640–151.143 |
| activation_prefill_16 | frame_pack | baseline | 578.090 / 33.114 / 533.234–603.106 | 578.035 / 33.111 / 533.193–603.044 |
| activation_prefill_16 | frame_pack | candidate | 147.279 / 3.717 / 142.055–166.718 | 147.070 / 3.720 / 142.026–166.667 |
| activation_prefill_16 | frame_decode | baseline | 583.790 / 34.160 / 536.437–615.648 | 583.747 / 34.166 / 536.386–615.183 |
| activation_prefill_16 | frame_decode | candidate | 144.736 / 6.531 / 140.695–159.344 | 144.702 / 6.506 / 140.668–159.311 |
| activation_prefill_64 | finite_scan | baseline | 2261.515 / 189.728 / 2097.234–2497.429 | 2261.092 / 189.635 / 2097.124–2497.056 |
| activation_prefill_64 | finite_scan | candidate | 557.264 / 45.470 / 511.175–644.467 | 557.201 / 45.912 / 511.123–644.395 |
| activation_prefill_64 | frame_pack | baseline | 2256.082 / 122.850 / 2179.654–2400.213 | 2255.755 / 123.413 / 2179.087–2400.074 |
| activation_prefill_64 | frame_pack | candidate | 581.120 / 34.369 / 540.697–674.989 | 580.852 / 34.370 / 540.660–674.926 |
| activation_prefill_64 | frame_decode | baseline | 2329.779 / 100.173 / 2148.862–2441.422 | 2329.429 / 100.246 / 2148.766–2440.555 |
| activation_prefill_64 | frame_decode | candidate | 598.458 / 48.521 / 544.928–650.438 | 598.383 / 49.759 / 544.877–647.904 |
| audit_reply | finite_scan | baseline | 3045.518 / 140.260 / 2824.222–3544.906 | 3045.374 / 140.413 / 2824.090–3544.731 |
| audit_reply | finite_scan | candidate | 741.379 / 63.461 / 709.331–891.891 | 741.307 / 63.471 / 709.135–891.802 |
| audit_reply | frame_pack | baseline | 3045.367 / 156.200 / 2837.844–3315.360 | 3043.903 / 154.235 / 2837.717–3315.181 |
| audit_reply | frame_pack | candidate | 757.039 / 23.423 / 710.466–924.717 | 756.888 / 25.663 / 708.843–924.635 |
| audit_reply | frame_decode | baseline | 3118.564 / 119.796 / 2931.508–3276.047 | 3117.393 / 118.967 / 2931.382–3263.891 |
| audit_reply | frame_decode | candidate | 798.704 / 43.263 / 706.306–847.245 | 798.636 / 40.973 / 706.253–847.157 |

| Case | Operation | Wall ratio: median / IQR / min–max | CPU ratio: median / IQR / min–max | Wall delta µs: median / IQR / min–max | CPU delta µs: median / IQR / min–max |
| --- | --- | ---: | ---: | ---: | ---: |
| activation_decode | finite_scan | 0.2430 / 0.0444 / 0.1886–0.3203 | 0.2427 / 0.0445 / 0.1884–0.3199 | -26.237 / 6.810 / -40.722–-23.512 | -26.231 / 6.820 / -40.709–-23.511 |
| activation_decode | frame_pack | 0.3471 / 0.0744 / 0.2812–0.4366 | 0.3469 / 0.0742 / 0.2807–0.4363 | -26.550 / 4.539 / -37.016–-21.946 | -26.546 / 4.535 / -37.018–-21.941 |
| activation_decode | frame_decode | 0.4088 / 0.0771 / 0.3307–0.7275 | 0.4083 / 0.0766 / 0.3306–0.8015 | -24.971 / 4.292 / -33.312–-14.919 | -24.972 / 4.276 / -33.298–-9.858 |
| activation_prefill_16 | finite_scan | 0.2475 / 0.0171 / 0.2115–0.2601 | 0.2474 / 0.0160 / 0.2114–0.2600 | -426.025 / 26.624 / -541.051–-387.217 | -425.935 / 28.439 / -541.002–-387.194 |
| activation_prefill_16 | frame_pack | 0.2554 / 0.0148 / 0.2411–0.2832 | 0.2553 / 0.0148 / 0.2410–0.2831 | -423.482 / 33.315 / -449.617–-384.527 | -423.466 / 33.319 / -449.670–-384.513 |
| activation_prefill_16 | frame_decode | 0.2576 / 0.0205 / 0.2391–0.2725 | 0.2574 / 0.0205 / 0.2391–0.2725 | -429.869 / 35.315 / -465.243–-392.998 | -429.859 / 35.223 / -464.847–-392.974 |
| activation_prefill_64 | finite_scan | 0.2494 / 0.0231 / 0.2293–0.2702 | 0.2496 / 0.0231 / 0.2297–0.2702 | -1702.015 / 159.083 / -1886.090–-1573.736 | -1700.301 / 156.033 / -1885.794–-1573.536 |
| activation_prefill_64 | frame_pack | 0.2551 / 0.0102 / 0.2418–0.3018 | 0.2552 / 0.0102 / 0.2418–0.3021 | -1686.929 / 116.898 / -1813.119–-1561.738 | -1686.868 / 116.873 / -1813.038–-1558.998 |
| activation_prefill_64 | frame_decode | 0.2542 / 0.0144 / 0.2455–0.2805 | 0.2542 / 0.0146 / 0.2444–0.2795 | -1738.854 / 79.076 / -1825.033–-1603.934 | -1739.089 / 77.586 / -1824.219–-1603.888 |
| audit_reply | finite_scan | 0.2462 / 0.0096 / 0.2416–0.2693 | 0.2462 / 0.0096 / 0.2416–0.2693 | -2269.739 / 79.004 / -2653.015–-2105.598 | -2269.662 / 79.073 / -2652.929–-2105.524 |
| audit_reply | frame_pack | 0.2502 / 0.0098 / 0.2295–0.2789 | 0.2499 / 0.0098 / 0.2294–0.2789 | -2281.291 / 166.231 / -2435.828–-2127.378 | -2279.897 / 166.882 / -2435.427–-2128.874 |
| audit_reply | frame_decode | 0.2562 / 0.0113 / 0.2377–0.2706 | 0.2562 / 0.0106 / 0.2377–0.2706 | -2289.180 / 70.188 / -2475.602–-2168.929 | -2289.603 / 69.836 / -2463.510–-2168.854 |

### run-002

UTC: 2026-10-25T07:55:54.119319+00:00 to 2026-10-25T07:56:06.028252+00:00. Internal monotonic interval: 11.908947 seconds. [Raw result](runs/run-002/result.json) · [Journal](runs/run-002/journal.jsonl).

| Case | Operation | Variant | Wall µs: median / IQR / min–max | CPU µs: median / IQR / min–max |
| --- | --- | --- | ---: | ---: |
| activation_decode | finite_scan | baseline | 32.466 / 2.835 / 31.765–41.795 | 32.447 / 2.839 / 31.751–41.754 |
| activation_decode | finite_scan | candidate | 8.203 / 1.338 / 7.980–11.162 | 8.193 / 1.329 / 7.967–11.147 |
| activation_decode | frame_pack | baseline | 39.714 / 5.368 / 35.593–49.379 | 39.689 / 5.366 / 35.577–49.358 |
| activation_decode | frame_pack | candidate | 13.433 / 2.744 / 12.123–19.623 | 13.412 / 2.732 / 12.110–19.592 |
| activation_decode | frame_decode | baseline | 44.358 / 4.666 / 39.945–54.754 | 44.333 / 4.673 / 39.920–54.005 |
| activation_decode | frame_decode | candidate | 17.591 / 1.630 / 16.045–27.599 | 17.571 / 1.633 / 16.032–27.567 |
| activation_prefill_16 | finite_scan | baseline | 555.122 / 34.525 / 531.868–602.961 | 554.979 / 34.507 / 531.801–602.783 |
| activation_prefill_16 | finite_scan | candidate | 138.116 / 3.873 / 134.084–153.356 | 138.087 / 3.853 / 133.934–153.304 |
| activation_prefill_16 | frame_pack | baseline | 563.485 / 11.598 / 527.316–589.907 | 563.087 / 12.068 / 527.278–589.846 |
| activation_prefill_16 | frame_pack | candidate | 146.007 / 5.342 / 133.411–152.872 | 145.968 / 5.340 / 133.372–152.843 |
| activation_prefill_16 | frame_decode | baseline | 576.098 / 34.044 / 517.477–599.943 | 576.040 / 34.080 / 517.448–599.873 |
| activation_prefill_16 | frame_decode | candidate | 151.155 / 11.836 / 140.427–166.734 | 151.118 / 11.825 / 140.386–166.697 |
| activation_prefill_64 | finite_scan | baseline | 2194.603 / 59.503 / 2082.259–2354.830 | 2194.481 / 59.346 / 2082.159–2354.711 |
| activation_prefill_64 | finite_scan | candidate | 543.171 / 28.136 / 515.170–597.253 | 543.108 / 28.351 / 515.118–597.179 |
| activation_prefill_64 | frame_pack | baseline | 2248.791 / 101.871 / 2111.394–2407.426 | 2247.851 / 101.981 / 2111.292–2407.299 |
| activation_prefill_64 | frame_pack | candidate | 582.256 / 72.859 / 533.619–735.214 | 582.134 / 72.860 / 533.581–734.999 |
| activation_prefill_64 | frame_decode | baseline | 2304.500 / 114.039 / 2136.460–2824.369 | 2303.745 / 114.112 / 2136.370–2823.916 |
| activation_prefill_64 | frame_decode | candidate | 601.902 / 24.723 / 542.685–662.862 | 601.846 / 24.997 / 542.634–662.807 |
| audit_reply | finite_scan | baseline | 3007.671 / 150.190 / 2815.868–3516.211 | 3007.546 / 150.413 / 2815.754–3515.750 |
| audit_reply | finite_scan | candidate | 741.725 / 52.522 / 699.482–791.864 | 741.672 / 49.510 / 699.401–791.813 |
| audit_reply | frame_pack | baseline | 3040.366 / 135.547 / 2830.686–3370.132 | 3039.917 / 127.392 / 2830.566–3365.455 |
| audit_reply | frame_pack | candidate | 804.615 / 55.575 / 725.124–955.183 | 804.474 / 55.651 / 725.046–955.104 |
| audit_reply | frame_decode | baseline | 3051.147 / 185.219 / 2762.923–3281.448 | 3050.844 / 184.687 / 2762.821–3281.319 |
| audit_reply | frame_decode | candidate | 799.544 / 73.079 / 749.367–893.674 | 799.383 / 73.061 / 749.293–893.579 |

| Case | Operation | Wall ratio: median / IQR / min–max | CPU ratio: median / IQR / min–max | Wall delta µs: median / IQR / min–max | CPU delta µs: median / IQR / min–max |
| --- | --- | ---: | ---: | ---: | ---: |
| activation_decode | finite_scan | 0.2578 / 0.0281 / 0.2013–0.3211 | 0.2576 / 0.0278 / 0.2013–0.3209 | -23.824 / 2.513 / -31.785–-22.763 | -23.812 / 2.503 / -31.764–-22.759 |
| activation_decode | frame_pack | 0.3546 / 0.0672 / 0.2744–0.4069 | 0.3544 / 0.0670 / 0.2744–0.4064 | -25.483 / 5.270 / -32.059–-21.697 | -25.481 / 5.270 / -32.028–-21.699 |
| activation_decode | frame_decode | 0.3952 / 0.0327 / 0.2951–0.5613 | 0.3950 / 0.0326 / 0.2990–0.5610 | -26.508 / 1.650 / -38.596–-20.995 | -26.501 / 1.649 / -37.855–-20.987 |
| activation_prefill_16 | finite_scan | 0.2486 / 0.0167 / 0.2331–0.2584 | 0.2485 / 0.0167 / 0.2330–0.2583 | -420.496 / 36.485 / -449.605–-394.459 | -420.431 / 36.484 / -449.479–-394.415 |
| activation_prefill_16 | frame_pack | 0.2577 / 0.0159 / 0.2321–0.2818 | 0.2577 / 0.0163 / 0.2321–0.2818 | -415.581 / 23.714 / -449.341–-378.705 | -415.566 / 24.284 / -449.324–-378.707 |
| activation_prefill_16 | frame_decode | 0.2661 / 0.0110 / 0.2523–0.2801 | 0.2660 / 0.0110 / 0.2522–0.2801 | -425.310 / 26.395 / -441.312–-372.678 | -425.286 / 26.344 / -441.279–-372.687 |
| activation_prefill_64 | finite_scan | 0.2457 / 0.0089 / 0.2323–0.2683 | 0.2457 / 0.0091 / 0.2323–0.2684 | -1637.674 / 57.021 / -1807.842–-1567.089 | -1637.612 / 57.566 / -1807.784–-1567.041 |
| activation_prefill_64 | frame_pack | 0.2597 / 0.0190 / 0.2420–0.3244 | 0.2598 / 0.0190 / 0.2420–0.3243 | -1664.308 / 78.986 / -1781.219–-1531.227 | -1663.499 / 78.168 / -1781.162–-1531.335 |
| activation_prefill_64 | frame_decode | 0.2611 / 0.0178 / 0.1972–0.2768 | 0.2609 / 0.0177 / 0.1972–0.2768 | -1696.760 / 68.313 / -2267.327–-1593.775 | -1696.695 / 67.972 / -2266.933–-1593.736 |
| audit_reply | finite_scan | 0.2480 / 0.0113 / 0.2001–0.2628 | 0.2480 / 0.0116 / 0.2001–0.2628 | -2238.346 / 154.689 / -2812.738–-2107.753 | -2238.271 / 155.973 / -2812.343–-2107.691 |
| audit_reply | frame_pack | 0.2626 / 0.0084 / 0.2551–0.2834 | 0.2626 / 0.0090 / 0.2538–0.2838 | -2229.127 / 62.091 / -2414.949–-2105.563 | -2226.933 / 43.754 / -2410.351–-2105.521 |
| audit_reply | frame_decode | 0.2663 / 0.0102 / 0.2445–0.2789 | 0.2663 / 0.0102 / 0.2446–0.2791 | -2270.941 / 147.155 / -2466.095–-2013.556 | -2270.748 / 146.668 / -2464.572–-2013.528 |

## Separate traced-allocation observations

Each variant cell has four one-call observations, in a separate phase after latency. In these retained data every cell had identical values in all four samples, so every listed value is simultaneously its minimum, median and maximum; every inclusive-quartile IQR is zero. The same applies to each paired delta. Each row below therefore reports the complete prespecified allocation summaries, not just selected medians.

All units are bytes. Retained is current minus the before counter with the return object still alive; peak increment is max(0, peak minus before). Differences are candidate minus baseline. Fresh tracing, instrumentation and retained results affect these counters. They do not measure cumulative allocations, all native allocations, process RSS, model memory, or distributed-device peak overlap.

### run-001 allocation

| Case | Operation | Baseline retained | Candidate retained | Retained delta | Baseline peak increment | Candidate peak increment | Peak delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| activation_decode | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| activation_decode | frame_pack | 2401 | 2401 | 0 | 2498 | 2498 | 0 |
| activation_decode | frame_decode | 2670 | 2670 | 0 | 7856 | 7856 | 0 |
| activation_prefill_16 | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| activation_prefill_16 | frame_pack | 36961 | 36961 | 0 | 37058 | 37058 | 0 |
| activation_prefill_16 | frame_decode | 37230 | 37230 | 0 | 111536 | 111536 | 0 |
| activation_prefill_64 | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| activation_prefill_64 | frame_pack | 147553 | 147553 | 0 | 147650 | 147650 | 0 |
| activation_prefill_64 | frame_decode | 147822 | 147822 | 0 | 443312 | 443312 | 0 |
| audit_reply | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| audit_reply | frame_pack | 196709 | 196709 | 0 | 197182 | 197174 | -8 |
| audit_reply | frame_decode | 196978 | 196978 | 0 | 591373 | 591365 | -8 |

### run-002 allocation

| Case | Operation | Baseline retained | Candidate retained | Retained delta | Baseline peak increment | Candidate peak increment | Peak delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| activation_decode | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| activation_decode | frame_pack | 2401 | 2401 | 0 | 2498 | 2498 | 0 |
| activation_decode | frame_decode | 2670 | 2670 | 0 | 7856 | 7856 | 0 |
| activation_prefill_16 | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| activation_prefill_16 | frame_pack | 36961 | 36961 | 0 | 37058 | 37058 | 0 |
| activation_prefill_16 | frame_decode | 37230 | 37230 | 0 | 111536 | 111536 | 0 |
| activation_prefill_64 | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| activation_prefill_64 | frame_pack | 147553 | 147553 | 0 | 147650 | 147650 | 0 |
| activation_prefill_64 | frame_decode | 147822 | 147822 | 0 | 443312 | 443312 | 0 |
| audit_reply | finite_scan | 0 | 0 | 0 | 504 | 496 | -8 |
| audit_reply | frame_pack | 196709 | 196709 | 0 | 197182 | 197174 | -8 |
| audit_reply | frame_decode | 196978 | 196978 | 0 | 591373 | 591365 | -8 |

## Interpretation and remaining limitations

The measured local improvement is consistent with avoiding singleton tuple production and a Python generator frame in the finite predicate. This comparison does not isolate a causal allocation-count contribution: native-view iteration, map dispatch, helper dispatch, float conversion and interpreter execution differ together. Python float objects and finite checks remain. Audit slicing and frame copies remain unchanged.

All payloads were the same preconstructed synthetic finite bytes, with no tensor-number conversion in timing. Exact output checks ran before and after each sample, and the source-only codec retained its structural and nonfinite rejection checks. Correctness tests cover 262,144 structured bitpatterns through selected and forced-fallback paths, fixed-seed full-width draws, signed zero/subnormals/extremes, NaN/Inf, fragmentation, malformed frames and the original contract suite. These tests are not an exhaustive proof over all possible messages or all 2^32 bitpatterns. No actual big-endian hardware was exercised.

All ten frozen sources, all 20 pre-data artifacts and the 62 previously tracked baseline files remain unchanged. The complete study suite passes 49 tests normally and under optimized Python; the root suite has 62 passes and three optional model skips, not 65 executed passes. The original codec has 34 passes and the prior serialization study 23. Test-runner durations and pre-existing kernel benchmark smoke tests are regression evidence, not additional candidate observations.

The baseline/candidate pair schedule balances AB/BA order but cannot remove caching, CPU frequency, scheduling, thermal, garbage-collection, specialization or shared-host effects. Both invocations share one host. No p-values, confidence intervals, statistical-significance claim, cross-host replication, total-memory-saving claim, TCP/network measurement, model-quality result, household throughput estimate or deployment-security claim follows. This is one tested local validation optimization, not an end-to-end household-compute speedup.

The original codec and all earlier published studies are unchanged. Any future integration should preserve these acceptance tests and obtain measurements in the intended runtime/workload; there is no authorization or evidence here for a network deployment.
