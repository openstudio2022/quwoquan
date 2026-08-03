# travel-service Agent Guide

本目录是 metadata domain `travel` 的自治服务边界；同时遵守仓库根和 `quwoquan_service/AGENTS.md`。

- 先修改 `contracts/`，再执行契约校验/codegen；禁止手改 `generated/`。
- 人工源码只放 `internal/<context>/<object>/<layer>`；跨对象只依赖对方 domain/application 公开端口，组合只发生在 `cmd/api`。
- `TripPlan`、`TripPlanRevision`、`TripMoment` 等对象分别拥有自身事实；Timeline/Map/ShareSnapshot 只保存声明过的投影或不可变快照。
- `config/schema.yaml`、`resources/`、`deploy/base` 是共享基线；四环境差异只放 `environments/<env>`，环境之间禁止继承。
- 服务不得导入其他服务的 `internal` 或 `generated`；跨服务协作只走公开 typed operation/event。
- 测试归 `tests/local_contract/<context>/<object>` 或 `tests/api_integration/<context>/<object>`；环境与真机证据不得由 fixture 替代。
