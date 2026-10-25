# Retained single-host framing-control observations

All values below are microseconds per operation: batch duration divided by 50 iterations. Each cell has 9 batch observations, not 450 independent samples. IQR uses inclusive quartiles. Both runs share one host; no confidence interval, p-value, or general-device claim is made. No observations were filtered, replaced, or pooled. Raw integer nanoseconds and CPU-time observations remain in each result and journal.

## run-001

UTC: 2026-10-25T06:46:28.525631+00:00 to 2026-10-25T06:46:36.548517+00:00. Monotonic elapsed: 8.022907 seconds. Status: complete; 216/216 planned batch rows.

### activation_decode

Payload: 2,304 bytes. Full frame: 2,368 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.051 | 0.009 | 0.042–0.070 | 0.042 | 0.007 | 0.034–0.060 |
| payload_copy | 0.209 | 0.015 | 0.197–0.242 | 0.202 | 0.011 | 0.191–0.230 |
| header_pack | 1.911 | 0.103 | 1.841–2.313 | 1.900 | 0.101 | 1.832–2.303 |
| finite_scan | 32.959 | 2.695 | 32.252–37.810 | 32.941 | 2.692 | 32.237–37.775 |
| frame_pack | 38.789 | 0.881 | 36.825–42.796 | 38.768 | 0.873 | 36.810–42.764 |
| frame_decode | 45.928 | 3.165 | 41.057–59.418 | 45.897 | 3.175 | 41.019–59.383 |

### activation_prefill_16

Payload: 36,864 bytes. Full frame: 36,928 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.052 | 0.020 | 0.038–0.069 | 0.043 | 0.020 | 0.032–0.059 |
| payload_copy | 0.959 | 0.063 | 0.887–1.266 | 0.950 | 0.056 | 0.881–1.260 |
| header_pack | 1.848 | 0.057 | 1.780–2.241 | 1.839 | 0.056 | 1.773–2.225 |
| finite_scan | 532.921 | 8.570 | 516.286–583.193 | 532.853 | 8.576 | 516.213–583.113 |
| frame_pack | 546.022 | 34.756 | 523.935–626.181 | 545.927 | 34.749 | 523.880–626.105 |
| frame_decode | 550.550 | 15.267 | 531.297–660.830 | 550.493 | 15.265 | 531.217–660.746 |

### activation_prefill_64

Payload: 147,456 bytes. Full frame: 147,520 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.041 | 0.004 | 0.035–0.066 | 0.034 | 0.003 | 0.030–0.054 |
| payload_copy | 3.691 | 1.080 | 2.986–4.207 | 3.676 | 1.074 | 2.972–4.189 |
| header_pack | 1.859 | 0.101 | 1.826–1.959 | 1.848 | 0.097 | 1.817–1.943 |
| finite_scan | 2144.362 | 103.586 | 2099.362–2510.978 | 2143.754 | 103.578 | 2098.944–2505.908 |
| frame_pack | 2151.767 | 95.832 | 2092.743–2345.446 | 2148.438 | 96.299 | 2092.578–2345.300 |
| frame_decode | 2219.364 | 36.911 | 2149.260–2495.927 | 2215.908 | 37.315 | 2149.059–2492.213 |

### audit_reply

Payload: 196,612 bytes. Full frame: 196,676 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.048 | 0.023 | 0.040–0.091 | 0.041 | 0.018 | 0.034–0.070 |
| payload_copy | 4.031 | 0.635 | 3.757–4.686 | 4.019 | 0.630 | 3.746–4.667 |
| header_pack | 2.005 | 0.122 | 1.940–2.266 | 1.997 | 0.119 | 1.931–2.255 |
| finite_scan | 2952.431 | 149.140 | 2809.950–3038.440 | 2951.866 | 148.626 | 2809.589–3035.827 |
| frame_pack | 2841.361 | 121.606 | 2791.634–3015.847 | 2841.059 | 121.938 | 2791.324–3015.676 |
| frame_decode | 2911.671 | 116.318 | 2862.090–3191.765 | 2911.432 | 116.436 | 2861.910–3187.287 |

## run-002

UTC: 2026-10-25T06:46:36.602227+00:00 to 2026-10-25T06:46:44.934155+00:00. Monotonic elapsed: 8.331949 seconds. Status: complete; 216/216 planned batch rows.

### activation_decode

Payload: 2,304 bytes. Full frame: 2,368 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.055 | 0.015 | 0.039–0.080 | 0.041 | 0.012 | 0.032–0.061 |
| payload_copy | 0.217 | 0.012 | 0.204–0.331 | 0.209 | 0.016 | 0.198–0.314 |
| header_pack | 1.921 | 0.773 | 1.845–3.765 | 1.905 | 0.779 | 1.834–3.744 |
| finite_scan | 36.296 | 3.331 | 33.674–38.729 | 36.258 | 3.330 | 33.601–38.690 |
| frame_pack | 38.508 | 0.326 | 38.027–40.750 | 38.490 | 0.334 | 37.994–40.716 |
| frame_decode | 45.172 | 4.497 | 42.379–84.894 | 45.140 | 4.483 | 42.340–84.850 |

### activation_prefill_16

Payload: 36,864 bytes. Full frame: 36,928 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.058 | 0.023 | 0.035–0.074 | 0.046 | 0.016 | 0.029–0.062 |
| payload_copy | 0.946 | 0.031 | 0.888–0.991 | 0.938 | 0.023 | 0.880–0.975 |
| header_pack | 1.932 | 0.057 | 1.867–2.778 | 1.922 | 0.058 | 1.857–2.766 |
| finite_scan | 549.118 | 18.413 | 537.258–640.564 | 549.065 | 17.862 | 537.028–640.464 |
| frame_pack | 559.663 | 44.041 | 550.430–637.380 | 559.585 | 44.574 | 550.354–637.281 |
| frame_decode | 569.952 | 12.667 | 558.838–597.081 | 569.253 | 12.651 | 558.783–593.803 |

### activation_prefill_64

Payload: 147,456 bytes. Full frame: 147,520 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.039 | 0.004 | 0.036–0.059 | 0.033 | 0.004 | 0.029–0.048 |
| payload_copy | 3.698 | 1.280 | 3.021–7.085 | 3.682 | 1.267 | 3.004–7.051 |
| header_pack | 1.887 | 0.051 | 1.848–3.081 | 1.878 | 0.055 | 1.841–3.062 |
| finite_scan | 2246.082 | 70.241 | 2155.837–2496.482 | 2245.870 | 70.680 | 2155.718–2496.267 |
| frame_pack | 2219.603 | 77.228 | 2186.552–2355.459 | 2219.331 | 73.804 | 2186.253–2351.292 |
| frame_decode | 2320.301 | 109.994 | 2216.536–2449.295 | 2320.099 | 110.043 | 2216.438–2447.089 |

### audit_reply

Payload: 196,612 bytes. Full frame: 196,676 bytes.

| Operation | Wall median | Wall IQR | Wall min–max | CPU median | CPU IQR | CPU min–max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| noop | 0.053 | 0.019 | 0.040–0.063 | 0.043 | 0.014 | 0.033–0.050 |
| payload_copy | 4.031 | 0.886 | 3.761–6.552 | 4.014 | 0.898 | 3.749–6.524 |
| header_pack | 2.001 | 0.068 | 1.937–2.070 | 1.986 | 0.059 | 1.928–2.056 |
| finite_scan | 2975.587 | 78.456 | 2892.875–3142.350 | 2970.308 | 78.155 | 2892.537–3140.756 |
| frame_pack | 3087.605 | 135.649 | 2949.925–3233.738 | 3087.083 | 130.396 | 2949.261–3227.825 |
| frame_decode | 3084.539 | 294.217 | 2945.831–3447.047 | 3079.608 | 294.286 | 2941.427–3446.516 |

## Interpretation boundaries

These are different amounts of work, not additive components. The finite scan alone can time above or below full-frame operations in separate batches. Do not subtract medians or sum control timings to attribute a precise percentage to validation. The measured payload-copy operation allocates a fresh bytes object; frame packing starts with already-encoded tensor bytes. Decode uses one complete chunk and a fresh decoder with no session gate. None measures tensor-number conversion, network transfer, TCP framing on a socket, trained-model execution, endpoint authentication, a physical mesh, or household-device performance.

The nominal 1 ns timer resolution is metadata, not demonstrated timing accuracy. Loop/call overhead, allocations, reclamation, cache warming, timer calls, system activity, virtualization, and CPU scheduling remain in the observations. Small-control medians are especially close to measurement overhead.
