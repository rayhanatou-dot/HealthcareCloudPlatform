# Resource and Cost-Efficiency Analysis

## Consolidated efficiency table

| Scenario | Users | Failures | Failure rate | Successful RPS | Avg ms | P95 ms | P99 ms | CPU % | Memory MiB | RPS/CPU% | RPS/GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 users | 10 | 0 | 0.00% | 7.94 | 26.72 | 71.00 | 290.00 | N/A | N/A | N/A | N/A |
| 50 users | 50 | 0 | 0.00% | 38.35 | 19.48 | 59.00 | 230.00 | 36.66 | 82.59 | 1.0461 | 475.49 |
| 100 users | 100 | 0 | 0.00% | 76.46 | 39.27 | 130.00 | 450.00 | 288.31 | 87.42 | 0.2652 | 895.62 |
| 200 users initial | 200 | 357 | 23.99% | 3.98 | 33132.66 | 90000.00 | 91000.00 | N/A | N/A | N/A | N/A |
| 200 users optimized | 200 | 0 | 0.00% | 146.77 | 29.27 | 110.00 | 240.00 | 0.35 | 102.10 | 419.3429 | 1472.01 |

## Interpretation

- Highest validated zero-failure load: **200 users**, **146.77 successful requests/s**.
- At 200 users, failed requests decreased from **357** to **0**.
- Reliability-adjusted throughput changed from **3.98** to **146.77 requests/s**.
- Relative throughput change at 200 users: **3587.69%**.
- Relative mean-latency change at 200 users: **-99.91%** (a negative value indicates improvement).
- Docker resource snapshots were available for **3** scenarios. RPS/CPU% and RPS/GiB are reported only where the backend container could be parsed reliably.

## Monetary cost model

The file `cost_input_template.csv` contains the performance denominator required for a cost model. Enter verified monthly infrastructure and operations costs before calculating monetary cost-effectiveness.

Recommended formula:

`cost per million successful requests = monthly total cost / (estimated successful monthly requests / 1,000,000)`

The maximum-load throughput measured by Locust must not automatically be treated as continuous monthly production traffic. Apply a realistic utilization factor and expected workload profile.

## Thesis use

- Report reliability-adjusted throughput rather than raw throughput alone.
- Separate software optimization gains from hardware scaling gains.
- State that financial conclusions require deployment-specific prices and utilization assumptions.
- Use the initial 200-user failure as evidence of a connection-pool bottleneck and the optimized result as evidence of remediation.
