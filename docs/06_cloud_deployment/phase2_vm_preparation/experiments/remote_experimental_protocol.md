# Phase II Remote Experimental Protocol

## Objective

Evaluate the deployed healthcare platform under controlled remote workloads and determine its performance, scalability, stability, and resource utilization on the authorized UESTC virtual machine.

## Experimental control requirements

- Use the same application commit and configuration for all comparable tests.
- Record the Git commit hash before every experiment.
- Keep the database state consistent between comparable runs.
- Use a separate load-generation computer whenever possible.
- Record the network location of the load generator.
- Synchronize the clocks of the VM and load generator.
- Perform a warm-up before measured requests begin.
- Keep the workload duration, spawn rate, and endpoint distribution identical across repeated runs.
- Document every configuration change between experiments.

## Planned workloads

### Scalability tests

- 10 concurrent users
- 50 concurrent users
- 100 concurrent users
- 200 concurrent users

### Mixed clinical workload

Include representative authenticated operations such as login, patient access, encounter access, observation access, prescription access, diagnostic-report metadata access, and authorized FHIR-inspired API requests.

### Endurance test

Run a sustained representative workload long enough to observe memory growth, container restarts, storage pressure, error accumulation, and performance degradation. The final duration must be recorded before execution.

## Repetition policy

- Execute each principal scalability workload at least three times when infrastructure time permits.
- Preserve every raw result, including unsuccessful runs.
- Report the median or mean across comparable valid runs together with variability.
- Do not remove outliers without a documented technical reason.

## Metrics

- Total requests
- Successful requests
- Failed requests
- Failure rate
- Requests per second
- Average response time
- Median response time
- P95 latency
- P99 latency
- Minimum and maximum latency
- CPU average and peak
- Memory average and peak
- Disk utilization and I/O
- Network traffic
- Container restarts and health status

## Execution sequence

1. Verify VM and container status.
2. Record baseline CPU, memory, disk, network, and application health.
3. Start synchronized resource monitoring.
4. Start the selected workload.
5. Preserve load-generator and server timestamps.
6. Stop the workload after the predefined duration.
7. Continue monitoring during the recovery period.
8. Export raw performance and infrastructure logs.
9. Record anomalies, errors, and configuration changes.
10. Verify application health after the test.

## Acceptance interpretation

Results must be interpreted using response times, failure rates, throughput, and resource saturation together. A workload must not be declared successful solely because the application remained online.

## Status rule

This file defines the planned methodology only. No result may be marked as completed until the workload has been executed on the authorized remote VM and the raw evidence has been preserved.
