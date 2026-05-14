# Config Release Drill Report (2026-02-27)

## Scope

- Service: `content-service`
- Stable: `IMAGE_VERSION=1.7.2`, `CONFIG_VERSION=v2026.02.27.1`
- Canary target: `IMAGE_VERSION=1.8.0`, `CONFIG_VERSION=v2026.02.28.0`

## Drill Commands Executed

1. Stage rollout state update:

```bash
make config-gray-rollout \
  SERVICE=content-service \
  FROM_IMAGE=1.7.2 TO_IMAGE=1.8.0 \
  FROM_CONFIG=v2026.02.27.1 TO_CONFIG=v2026.02.28.0 \
  STEP=5
```

2. SLO gate decision check:

```bash
make config-slo-gate ERROR_RATE=0.005 P95_MS=180 REDIS_ERROR_RATE=0.001
```

3. Rollback idempotency check:

```bash
make config-rollback SERVICE=content-service TO_CONFIG=v2026.02.28.0
```

4. Integrated stage apply (rollout + gate + conditional rollback):

```bash
agent_ops/deploy/prod/config_release_apply_stage.sh \
  --service content-service \
  --step 25 \
  --from-image 1.7.2 --to-image 1.8.0 \
  --from-config v2026.02.27.1 --to-config v2026.02.28.0 \
  --error-rate 0.006 --p95-ms 210 --redis-error-rate 0.002
```

## Result

- Stage state updated successfully.
- SLO gate returned `continue` for healthy metrics.
- Rollback command proved idempotent when target version already active.
- Audit logs created under `.release-state/content-service.audit.log`.

## Conclusion

`G/R/S` minimal closed loop is runnable:
- gray rollout plan (`G`)
- rollback execution (`R`)
- SLO judgment and linkage (`S`)
