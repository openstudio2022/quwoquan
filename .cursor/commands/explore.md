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
10. 若涉及端侧 **Mock/Remote、数据源切换、正式包构建**：对照 [`specs/gates/mock_data_cloud_integration_policy.md`](../../specs/gates/mock_data_cloud_integration_policy.md) **§5.1**（发布态 R1–R6、开发测试态 D1–D4、测试代码用语边界）；可续写 **CR-20260329-007** 或单列 CR 登记策略 delta

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
- 是否影响 **发布态无测试入口 / 开发态一键切云**：与 §5.1、规则 `08-mock-data-isolation.mdc`、CI `APP_DATA_SOURCE` 是否一致

## 工程合规预判（代码评审专家视角）

探索阶段必须对以下工程约束做初步预判，以便后续 `/prd` / `/design` 正确冻结：

| 约束 | 预判问题 |
|------|---------|
| DDD 分层 | 需求涉及哪些领域层？是否需要新建 domain / application / infrastructure？ |
| 强类型 | 是否涉及新的数据结构？端侧 DTO 和云侧 struct 如何对齐？ |
| 存储无关 | 需要什么存储引擎？是否通过 interface 抽象？是否涉及存储迁移？ |
| 端云一致 | 是否新增 API / 字段 / 枚举 / 错误码？端云 schema 如何同步？ |
| 元数据驱动 | 需要改哪些 metadata YAML？路径/操作/surface/错误码是否走 codegen？ |
| 四层测试 | 初步 T1~T4 证据矩阵如何分布？是否涉及端云联调（T3）或真机旅程（T4）？ |

## 可观测与推荐影响预判

| 维度 | 预判问题 |
|------|---------|
| 埋点 | 需求涉及的页面是否已有行为埋点？是否需要新增事件类型或字段？ |
| 指标 | 是否需要新增运营指标或切分维度？现有指标是否足以度量成功？ |
| 推荐 | 是否产生新的用户行为信号？是否需要回流到推荐特征？ |
| 性能 | 是否涉及列表/媒体/网络密集场景？是否需要性能基线？ |
| 存储生命周期 | 新增数据的 TTL / 归档 / 清理策略如何？ |

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
