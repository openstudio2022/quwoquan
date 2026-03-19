---
name: /explore
id: explore
category: Workflow
description: 探索模式（定位 L1/L2/L3，识别 Journey/Scenario/CR，不写实现代码）
---

> SDD 主流程：**explore** → prd → design → dev → commit → deploy

探索模式只做思考、分析、澄清和定位，不写实现代码。

## G0 必做项

探索开始前必须自动完成：

1. 查 `specs/feature-tree/tree_index.yaml`，确认需求归属的 `L1_capability`
2. 判断是否需要创建或更新某个 `L2_journey`
3. 判断目标 `L3_scenario`
4. 查 `contracts/metadata/`，确认涉及哪些业务对象
5. 识别是否涉及扩展场景
6. 识别对标输入、NFR、测试责任、发布风险
7. 识别权限边界、数据生命周期、迁移灰度与回滚风险
8. 若涉及 `path / operation / surface / route / decoder context`，明确 metadata 真相源边界
9. 判断本次增量是否需要新建或续写 `specs/changelog/CR-*.yaml`

缺少对标输入、真实网络条件、容量假设、权限边界、生命周期合同或回滚条件时，直接输出 `GATE_BLOCK`。

## 助手相关需求必读

若需求涉及 `quwoquan_app/lib/personal_assistant/`、`quwoquan_app/assets/personal_assistant/`、`quwoquan_app/test/personal_assistant/` 或与助理链路直接耦合的 `ui/chat`：

1. 先读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
2. 再读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
3. 若涉及新增 Skill / Tool / Phase / 垂类专项，再读对应 `quwoquan_app/personal_assistant/docs/scenarios/*.md`

探索阶段必须先判断本次需求应落在 runtime、skill、tool、prompt、UI 哪一层，并明确哪些逻辑不得通过 runtime 硬编码实现。

## 三层定位原则

- `L1_capability`：能力边界
- `L2_journey`：端到端旅程与组合验收容器
- `L3_scenario`：单环节场景与最小实施单元
- `plan slice`：稳定实施切片，后续落入 `plan.yaml`

禁止：

- 在 explore 阶段讨论 `L4/L5`
- 把任务项或会话 todo 当成树节点

## 探索重点

- 目标用户是谁
- 核心问题是什么
- 成功标准是什么
- 不做什么
- 是否有对标产品、原型、截图、视频、公开代码或公开文档
- 该需求应挂到哪个 `L1_capability`
- 应形成哪个 `L2_journey`
- 目标 `L3_scenario` 是什么
- 是否涉及权限、分享、小趣消费、删除撤销、升级迁移
- 初步 plan slice 是否满足 `metadata -> codegen -> 业务逻辑 -> 测试`
- 这次增量是否应进入已有 CR，还是新建 CR

## 输出建议

```text
已澄清：
- ...

仍待澄清：
- ...

建议归属：
- L1: ...
- L2: ...
- L3: ...

初步计划：
- plan slice: ...

增量变更：
- CR: ...

商用风险：
- Benchmark:
- SLO/KPI:
- 权限/生命周期:
- 灰度/回滚:

测试责任：
- T1: ...
- T2: ...
- T3: ...
- T4: ...

结论：
- EXPLORE_READY
# 或
- GATE_BLOCK
```

## Guardrails

- 不实现代码
- 不创建第四层或第五层树节点
- 不把测试层写成 `L3/L4`
