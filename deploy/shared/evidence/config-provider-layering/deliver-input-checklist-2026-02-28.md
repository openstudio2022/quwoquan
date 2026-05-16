# config-provider-layering deliver input checklist (2026-02-28)

## Deliver readiness checklist

- [x] 测试报告
  - `make build && make test-contract` (quwoquan_service)
  - `make gate-full` (repo root)
  - recommendation-service Python tests mandatory in gate-full
- [x] 门禁报告
  - `scripts/verify_service_config_layout.sh`
  - `scripts/verify_service_env_contract.sh`
  - `scripts/verify_config_release_version_mapping.sh`
  - `scripts/verify_config_image_compat.sh`
  - `scripts/verify_config_gray_parallel_binding.sh`
  - `scripts/verify_deployment_domain_mapping.sh`
  - `scripts/verify_topology_contract_regression.sh`
- [x] 回滚演练记录
  - `deploy/service/config-release/reports/2026-02-27-config-release-drill.md`
  - `agent_ops/deploy/prod/config_release_rollback.sh` idempotent rollback
- [x] 拓扑影响报告
  - `scripts/report_deployment_mapping_impact.sh` (base-aware impact diff)

## Scope conclusion

- recommendation-service 已实现配置分层加载（default/env/version/env vars）并 fail-fast
- split-dev 与 composed integration/prod 拓扑校验已自动化并接入 CI
- 灰度配置新老版本并行绑定链路（from/to image + config）可执行并可审计
