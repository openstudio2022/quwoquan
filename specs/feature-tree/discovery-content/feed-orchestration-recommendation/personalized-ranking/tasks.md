# 开发任务：personalized-ranking

## 规划任务（metadata → codegen → 业务逻辑 → 测试）

- [x] T1 contracts-first：更新 `contracts/metadata/content/post/service.yaml`，为 `GetFeed` 增加 `sort` 参数与 opaque cursor 协同语义。
- [x] T2 contracts-first：更新 `contracts/metadata/content/post/tests/contract.yaml`，新增“sort=recommend + cursor 无重复 + 未来窗口动态”契约场景。
- [x] T3 codegen：执行 `make verify-metadata && make codegen && make codegen-app`，同步云侧路由绑定与端侧 metadata 常量。
- [x] T4 实现（云侧）：改造 `runtime/recommendation/engine.go` 为 token offset 分页，移除“cursor 跳过重排”的临时逻辑。
- [x] T5 实现（云侧）：在 `feed_service.go` / `content_handler.go` 透传 `sort` 并沿用引擎返回的 `nextCursor`。
- [x] T6 实现（端侧）：在 `content_repository.dart` 与 discovery provider 接入 `sort=recommend` 透传与已看窗口队列稳定策略。
- [x] T7 测试（云侧）：更新 `post_feed_contract_test.go`，覆盖 recommend 排序与 cursor 连续翻页无重复。
- [x] T8 测试（端侧）：补 provider/journey 场景，验证“回滚记录不变 + 翻页未来可变且不重复”。
- [x] T9 gate：执行 `make gate` / `make gate-full`，记录产物与风险。
