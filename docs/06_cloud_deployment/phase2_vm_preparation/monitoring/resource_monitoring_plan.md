# VM Resource Monitoring Plan

## Objective

Collect synchronized infrastructure and application metrics during every Phase II workload so that performance results can be interpreted together with actual resource consumption.

## Metrics to collect

- CPU utilization: host and containers
- Memory utilization: used, available, swap, and container memory
- Disk utilization: capacity, read/write activity, and Docker storage
- Network activity: received and transmitted traffic
- Container status, restarts, and health
- Application response time, throughput, failures, P95, and P99 latency

## Required collection points

- Five-minute idle baseline before testing
- Warm-up period before each measured workload
- Entire test duration
- Five-minute recovery period after testing

## Workload sequence

- 10 concurrent users
- 50 concurrent users
- 100 concurrent users
- 200 concurrent users
- Mixed clinical workload
- Endurance workload

## Core Linux commands

```bash
date -Is
uptime
nproc
free -h
df -h
docker compose ps
docker stats --no-stream
```

## Optional monitoring commands

Use these only when installed and authorized:

```bash
vmstat 1
iostat -xz 1
sar -u 1
sar -r 1
sar -n DEV 1
```

## Synchronization requirements

- Record the VM date, time zone, and clock status before every experiment.
- Start resource monitoring immediately before the load generator.
- Preserve the exact test start and end timestamps.
- Use the same test duration and ramp-up settings for comparable workloads.
- Keep raw monitoring logs without manual modification.

## Evidence naming convention

Use ISO-style timestamps and workload names, for example:

```text
2026-08-05_200users_cpu.log
2026-08-05_200users_docker_stats.log
2026-08-05_200users_locust.csv
```

## Reporting rule

A single resource snapshot must not be presented as steady-state utilization. Report baseline, average, peak, and test-period measurements where available.
