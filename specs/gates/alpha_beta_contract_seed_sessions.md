# Alpha/Beta Contract Seed 独立会话执行说明

## 会话一：助手真实链路

执行输入：

- `specs/gates/assistant_alpha_beta_real_chain_spec.md`
- `quwoquan_service/contracts/metadata/assistant/test_fixtures/scenarios/assistant_scenarios.json`
- `scripts/verify_assistant_beta_real_chain_report.py`

完成口径：

- 端侧 alpha 使用 fixture mock 云接口。
- 云侧 alpha reset+seed 到 assistant-service 自身 store/cache 后测真实 service/handler。
- 端侧 beta remote 调本地 assistant-service。
- 云侧 beta 必须真实访问模型与搜索 provider。
- 最终报告通过 `python3 scripts/verify_assistant_beta_real_chain_report.py <report> --log <assistant-log>`。

## 会话二：业务对象 DB Seed

执行输入：

- `specs/gates/business_alpha_beta_db_seed_spec.md`
- `quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json`
- `quwoquan_service/contracts/metadata/messages/chat/test_fixtures/scenarios/chat_scenarios.json`
- `quwoquan_service/contracts/metadata/social/circle/test_fixtures/scenarios/circle_scenarios.json`
- `scripts/verify_business_beta_db_seed_report.py`

完成口径：

- 端侧 alpha 从同一 fixture 构造 MockRepository。
- 云侧 alpha reset+seed 到对应服务数据库/缓存后测真实接口。
- 云侧 beta reset+seed 后开放本地 HTTP API。
- 端侧 beta RemoteRepository 通过本地接口读取 content/chat/circle 数据。
- 最终报告通过 `python3 scripts/verify_business_beta_db_seed_report.py <report>`。

## 总体验收

两个会话完成后，总会话只做聚合验收：

- 检查助手报告不存在 fake/mock 模型与搜索证据。
- 检查业务对象报告不存在 Dart mock 数据来源。
- 检查 alpha/beta 端云职责未混淆。
- 保留报告路径、服务日志路径与 seedRefs。
