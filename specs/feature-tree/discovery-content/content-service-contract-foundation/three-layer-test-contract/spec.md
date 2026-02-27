# L3：three-layer-test-contract

## 功能说明

将分散在 service.yaml contract_test 块中的测试场景迁出，建立独立的三层测试契约目录
（tests/mock.yaml / contract.yaml / e2e.yaml），并扩展 make gate 的场景覆盖校验（G7），
确保 YAML 场景声明与实际测试代码之间有强绑定。

## 范围

**tests/mock.yaml**（端侧独立，不依赖云）：
- DTO 解析场景（四类类型分发 + alias 解析 + 计算属性）
- 错误码解析场景（全量 errors.yaml codes 覆盖）
- 行为上报格式场景（batch events 格式 + dedicated route 不入 batch）
- data_source: fields.yaml constraints → codegen mock fixture

**tests/contract.yaml**（云侧独立，真实 DB）：
- 从 service.yaml contract_test.service_side 迁移全部场景
- 补充错误码返回场景（每个 errors.yaml code 至少一个）
- 补充幂等场景（LikePost x2 → counter=1）
- 与 Go 测试函数名强绑定（G7 gate）

**tests/e2e.yaml**（端云集成，staging advisory）：
- discovery_feed_load_and_render：端 → 网关 → service → DB 全链路
- like_post_realtime：点赞实时性 + 错误 UI 呈现
- behavior_batch_report：行为批量上报到达验证

**Gate G7**：
- `make gate` 校验 tests/contract.yaml scenarios ⊆ services/content-service/tests/ 中的 Go 测试函数
- 新增场景 → 必须同时写对应 Go 测试函数

## 验收标准

- A1：tests/mock.yaml 场景覆盖 errors.yaml 全量 codes
- A2：tests/mock.yaml 场景覆盖 behaviors.yaml 全量 behavior_events
- A3：tests/contract.yaml 覆盖 service.yaml 全部 api_routes（每路由 ≥1 场景）
- A4：service.yaml contract_test 块已删除（场景迁出完成）
- A5：make gate G7（场景覆盖校验）通过
- A6：新增 Go 测试函数覆盖 tests/contract.yaml 所有场景（flutter test + go test 全绿）
