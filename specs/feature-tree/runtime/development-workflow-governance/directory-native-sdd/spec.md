# L3 Story：目录原生 SDD (`directory-native-sdd`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；支撑全部 Scenario 的一致规格与验收
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为编程 Agent 或审核者，我希望从目录和节点文档直接获得当前规格、设计归属、验收与 OPEN，从而不依赖人工索引、历史任务台账或会话记忆做决定。

## 2. 范围与非目标

### In Scope

- 目录表达 AppRoot/L1/L2/L3，节点 Markdown 自解释，动态报告写入 `.qwq_output`。
- 章节、链接、验收、OPEN、owner 和禁止历史文件由 gate 检查。

### Out of Scope

- tracked tree index、Journey registry、acceptance YAML、changelog 或 backlog。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 无注册表上下文

- 工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。

## 4. 契约引用

- scanner：`quwoquan_ops/cli/feature_tree.py`
- content gate：`quwoquan_ops/cli/feature_tree_content_review.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 目录直接表达树与验收

- GIVEN 仓库只保留节点 spec/design、metadata、代码与测试。
- WHEN gate 扫描层级、父子链接、验收锚点和 `spec_ref`。
- THEN 它无需任何 tracked index/registry 即生成完整树；缺链接、占位内容或无 owner 变更被阻断。

## 6. 依赖

- 前置要求：根 `AGENTS.md` 与 feature-tree README 的单一规则。
- 上游事实：目录、Markdown、Git diff 与测试 `spec_ref`。
- 下游结果：上下文、总览、变更报告或 GATE_BLOCK。
- 父级设计：`DEC-001`
