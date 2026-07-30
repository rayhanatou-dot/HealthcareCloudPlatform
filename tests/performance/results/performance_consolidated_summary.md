# Consolidated Performance Results

| Scenario | Users | Requests | Failures | Failure rate | Avg (ms) | Median (ms) | P95 (ms) | P99 (ms) | RPS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 users | 10 | 465 | 0 | 0.00% | 26.72 | 16.00 | 71.00 | 290.00 | 7.94 |
| 50 users | 50 | 4557 | 0 | 0.00% | 19.48 | 10.00 | 59.00 | 230.00 | 38.35 |
| 100 users | 100 | 13695 | 0 | 0.00% | 39.27 | 15.00 | 130.00 | 450.00 | 76.46 |
| 200 users initial | 200 | 1488 | 357 | 23.99% | 33132.66 | 29000.00 | 90000.00 | 91000.00 | 5.23 |
| 200 users optimized | 200 | 43814 | 0 | 0.00% | 29.27 | 13.00 | 110.00 | 240.00 | 146.77 |

## Interpretation

- Maximum validated load with zero failures: **200 concurrent users** at **146.77 requests/s**.
- The optimized 200-user configuration reduced failures from **357** to **0**, a reduction of **357 failed requests**.
- Throughput at 200 users increased from **5.23** to **146.77 requests/s**, a gain of **141.54 requests/s**.
- Mean response time at 200 users improved by approximately **99.91%**.

## Evidence files

- `locust_10_users_stats.csv`
- `locust_50_users_stats.csv`
- `locust_100_users_stats.csv`
- `locust_200_users_stats.csv`
- `locust_200_users_fixed_stats.csv`

## Notes

- The initial 200-user result is retained as evidence of the original connection-pool bottleneck.
- The optimized 200-user result is the final scalability result.
- These results describe the tested Docker environment and should not be generalized beyond the measured configuration without additional experiments.
