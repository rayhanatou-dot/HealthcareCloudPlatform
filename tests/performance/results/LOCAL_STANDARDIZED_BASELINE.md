# Local Standardized Performance Baseline

Date: 2026-08-17
Workload: tests/performance/locustfile.py
Target: http://localhost:8000
Locust: 2.45.0

| Users | Spawn rate | Duration | Requests | Failures | RPS | Avg ms | Median ms | P95 ms | P99 ms | Max ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 2 users/s | 1 min | 474 | 0 | 8.01 | 24 | 15 | 65 | 220 | 350 |
| 50 | 5 users/s | 2 min | 4580 | 0 | 38.40 | 17 | 10 | 52 | 220 | 292 |
| 100 | 10 users/s | 3 min | 13900 | 0 | 77.53 | 15 | 8 | 39 | 91 | 463 |
| 200 | 20 users/s | 5 min | 46555 | 0 | 155.53 | 19 | 10 | 56 | 140 | 946 |

All four runs used automatic --run-time termination. Ramp-up time is included in the configured run duration. All runs completed with 0 failures.

Integrity manifest: SHA256_STANDARDIZED_BASELINE.txt
Manifest validation: TOTAL=20 VALID=20
