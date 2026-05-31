# 模板领域服务设计

## 设计目标

模板目录以 authoring asset 的形式存在，目标是让所有新增特性树节点使用同一套文档结构、验收语言和测试证据口径。

## 设计决策

### D1：模板按层级拆分

应用根、领域服务、业务能力和 Story 的文档职责不同，因此模板按层级拆分，而不是复用一份通用模板。

### D2：Story 不设设计模板

Story 是最小可闭环价值点，设计决策必须上收到业务能力层。Story 只保留 `spec.md` 与 `acceptance.yaml`。

### D3：计划不进入特性树

`树内计划文档` 和 `树内任务文档` 不再作为正式治理文档。执行计划保留在会话、PR 或外部台账中。

## 模板资产

- `app_root_spec.md`
- `app_root_design.md`
- `app_root_acceptance.yaml`
- `domain_service_spec.md`
- `domain_service_design.md`
- `domain_service_acceptance.yaml`
- `business_capability_spec.md`
- `business_capability_design.md`
- `business_capability_acceptance.yaml`
- `story_spec.md`
- `story_acceptance.yaml`

## 演进策略

- 新增模板必须先更新本设计。
- gate 规则变化必须先反映到模板。
- 旧 Journey / Scenario 模板不得作为新增节点入口继续使用。
