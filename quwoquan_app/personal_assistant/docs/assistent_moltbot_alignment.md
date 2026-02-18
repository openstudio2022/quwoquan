# Assistent v1 vs Moltbot Alignment

## Scope

This document captures how `assistent v1` aligns with patterns observed in moltbot and what was strengthened for commercial rollout.

## 1) Adapter Verify Strategy

Moltbot pattern:
- Uses channel-specific signature verification with HMAC and safe comparison.
- Validates raw body + timestamp for webhook authenticity.

Assistent v1 implementation:
- `AssistentSignatureValidator` supports `none|token|hmac_sha256`.
- Feishu/OpenClaw adapters now use configurable signature policy.
- Constant-time comparison is applied for both token and HMAC values.
- Timestamp skew guard is supported by policy (`maxSkewSeconds`).

## 2) Provider Routing Policy

Moltbot pattern:
- Tracks provider usage snapshots and performs health probing.
- Timeout and resilience are treated as first-class concerns.

Assistent v1 implementation:
- `AssistentProviderPolicy` links cost/latency with health + SLO snapshots.
- `AssistentProviderHealthService` probes candidates before route decisions.
- Route context includes channel/device/cost/latency/availability threshold.
- Gateway switches model before run based on selected provider.

## 3) SLO and Alert Trigger

Moltbot pattern:
- Health snapshot and heartbeat style monitoring for runtime state.

Assistent v1 implementation:
- `AssistentSloMonitor` records per-provider run events and computes windowed snapshot.
- Alert evaluation (`warning|critical`) triggered on threshold violation.
- `AssistentAlertDispatcher` stores recent alerts for release verification.
- Commercial endpoint `GET /v1/assistent/alerts` exposes alert stream for canary acceptance.

## Conclusion

The current implementation adopts moltbot’s proven mechanisms (signature verification, health probing, runtime monitoring) and extends them with explicit provider-route/SLO linkage for gray-release readiness in `assistent v1`.

