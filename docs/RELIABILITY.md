---
title: Reliability — operational expectations
status: skeleton
last_updated: 2026-05-04
---

# RELIABILITY

Operational targets for the MES once a paying customer is in production. Skeleton — populated when the first deployment lands.

## SLOs (provisional)

| Service                 | Latency target          | Availability target |
|-------------------------|-------------------------|---------------------|
| HTTP API (read)         | p99 < 300 ms            | 99.5% monthly       |
| HTTP API (write)        | p99 < 800 ms            | 99.5% monthly       |
| OPC-UA event ingestion  | < 5 s end-to-end (PLC → event bus) | 99% monthly |
| Dashboard refresh       | < 2 s after event       | best effort         |

These numbers will be adjusted with the first customer's contract.

## Failure modes the system MUST tolerate

- **Redis temporarily unreachable.** OPC-UA workers buffer events on disk (configurable cap); HTTP handlers degrade gracefully, returning 503 with retry-after.
- **Postgres replica lag.** Reads to projections fall back to primary if lag > 5 s on critical queries.
- **PLC offline.** Equipment shows `unknown` status; downtime is not auto-attributed; operator can record manually.
- **ERP unreachable.** Outbound confirmations queue locally with idempotency keys; retry with exponential backoff; alert at 1 hour stuck.

## Backups

- Postgres: WAL archiving + nightly base backup. Restore-tested monthly (Harness-Fix ticket scaffolds the test).
- Redis: AOF persistence; treated as cache, not source of truth.

## Observability

- **Logs:** structured JSON to stdout, shipped to customer's preferred sink (Loki, ELK, CloudWatch).
- **Metrics:** Prometheus scrape on `/metrics`. Per-context counters and latency histograms.
- **Traces:** OpenTelemetry; sampled at 1% in production.

## Disaster recovery

- RPO target: 5 minutes.
- RTO target: 1 hour.
- DR runbook lives in this file once the first deployment exists.
