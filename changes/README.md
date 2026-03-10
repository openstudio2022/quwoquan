# changes/（全栈特性粒度交付）

本目录是**端云一体化**的“单一特性载体”：Ask/Plan 阶段的输出必须落盘在这里，后续实现与测试必须以这里的验收标准为准。

全量特性台账：
- `changes/feature_catalog.yaml`
- `changes/feature_tree.yaml` 已退役，不再作为特性树结构来源
- 每条特性必须补充：`opsx_change_id`、`opsx_specs`、`delivery_profile`

创建新特性目录：

```bash
bash scripts/new_feature_fullstack.sh "<slug>"
```

生成后目录结构（示例）：

```text
changes/2026-02-21-discovery-feed-v1/
├── README.md             # 目标/范围/非目标/风险/里程碑（Ask 输出）
├── contracts_delta.md    # contracts-first：OpenAPI/约束变更清单（Plan 输出）
├── acceptance.yaml       # 机器可读验收标准（A1~A8）+ 自动化测试映射
├── tasks.md              # 端侧 + 云侧任务拆解（落到可执行项）
└── traceability.yaml     # 特性映射（服务/对象/API/横切能力/测试）
```

`traceability.yaml` 需包含：
- `opsx`（`change_id` + `specs`）
- `test_automation`（mock / contract / integration / uat 的端云自动化映射）

`acceptance.yaml` 必须采用统一模板（A1~A8）：
- `global_acceptance.A1_functional`
- `global_acceptance.A2_experience`
- `global_acceptance.A3_service_governance`
- `global_acceptance.A4_observability`
- `global_acceptance.A5_product_ops`
- `global_acceptance.A6_security_privacy`
- `global_acceptance.A7_contract_metadata_consistency`
- `global_acceptance.A8_test_automation`

相关规范：
- `quwoquan_service/contracts/feature_delivery_workflow.md`
- `quwoquan_service/contracts/acceptance_criteria.md`
- `quwoquan_service/contracts/ddd_fullstack_guidelines.md`

