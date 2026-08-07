# L3 Story：目标特性上下文发现 (`feature-context-discovery`)

> 所属能力：[Agent 上下文工具](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为编程与审核提供最小完整上下文
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为 Cursor/Codex Agent，我希望输入一个 spec 或代码路径就能定位唯一领域 owner、规格父链与验收证据，从而在不扫描全仓的情况下做出一致决定。

## 2. 范围与非目标

### In Scope

- 从 spec 路径直接定位节点；从代码路径按 L1 工程归属定位唯一 owner。
- 输出父链、Journey、REQ/验收/DEC/OPEN、metadata、`spec_ref`、Git 增量和依赖节点。

### Out of Scope

- 把派生上下文提交进仓库，或在多个 owner 冲突时自动猜选。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 唯一 owner 与最小父链

- 同优先级多个 L1 认领路径时必须阻断；成功输出不得依赖 tracked index、registry 或状态文件。
- canonical App 对象测试 `test/<layer>/service/<service>/<context>/<object>/...` 必须投影到同 service 的 production engineering root 决定 owner；`quwoquan_app` 项目级构建归属不得吞并业务对象测试，legacy/未知 service 必须 `GATE_BLOCK`。

## 4. 契约引用

- context tool：`quwoquan_ops/cli/feature_tree.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 从代码定位规格上下文

- GIVEN 一个存在且被某 L1 工程根唯一认领的代码路径。
- WHEN Agent 生成 feature context。
- THEN 输出唯一 L1 与目标父链、相关验收和当前 OPEN；若存在同优先级重复 owner 则返回 GATE_BLOCK。
- AND canonical App 对象测试与同 domain production source 得到相同 L1 owner，项目级 App fallback 不得改变该结果。

## 6. 依赖

- 前置要求：各 L1 工程归属真实存在且无未裁决重叠。
- 上游事实：目录、Markdown、Git diff 与测试引用。
- 下游结果：`.qwq_output` 中的只读上下文报告。
- 父级设计：`DEC-001`
