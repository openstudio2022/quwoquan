# Notification Service Seed Gap

## 结论

`notification` 目前已有 metadata 与端侧/网关 fixture：

- `quwoquan_service/contracts/metadata/notification/test_fixtures/scenarios/notification_scenarios.json`
- `quwoquan_service/contracts/metadata/_shared/test_fixtures/app_beta_seed_manifest.json`
- `scripts/dev_assistant_beta_gateway.py` 的 `/v1/app-messages` fixture route

但 `quwoquan_service/services/` 下暂无独立 `notification-service` 目录，因此不能声称已完成真实 Go service 的 reset+seed。

## 当前验收口径

- alpha：端侧 mock/fixture 读取 `notification_core`。
- beta/gamma：本地 gateway fixture harness 提供 `/v1/app-messages` smoke。
- prod/prod-gray：禁止 test fixture 与 seedRefs。

## 后续补齐条件

当新增 `notification-service` 后，必须补齐：

- `services/notification-service/configs/default|alpha|beta|gamma|prod-gray|prod/config.yaml`
- `services/notification-service/tests/contract_fixture_seed_test.go`
- `services/notification-service/tests/contract_fixture_seed_contract_test.go`
- `app_beta_seed_manifest.json` 的 `targetStore` 从 `notification-service:test_store` 对齐到真实测试存储
- `scripts/run_business_beta_db_seed.py` 纳入 notification 真实 seed report
