# Config Release Runbook

## Required Env Contract

- `APP_ENV`
- `SERVICE_NAME`
- `CONFIG_VERSION`
- `IMAGE_VERSION`
- `CONFIG_ROOT`

## Rollout Steps

1. Prepare new config version file in `releases/config/<service>/v*.yaml`
2. Run stage rollout:

```bash
agent_ops/deploy/prod/config_release_apply_stage.sh \
  --service content-service \
  --step 5 \
  --from-image 1.7.2 --to-image 1.8.0 \
  --from-config v2026.02.27.1 --to-config v2026.02.28.0 \
  --error-rate 0.005 --p95-ms 180 --redis-error-rate 0.001
```

3. Repeat for `25`, `50`, `100`.

## Rollback

```bash
agent_ops/deploy/prod/config_release_rollback.sh \
  --service content-service \
  --to-config-version v2026.02.27.1
```

Rollback is idempotent and writes an audit line to `.release-state/<service>.audit.log`.
