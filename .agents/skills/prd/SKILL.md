---
name: prd
description: Update the currently-valid spec.md and testable acceptance anchors for a change, without implementing anything. Every acceptance must be bindable by a real test. Use when the user says 写 PRD, 冻结需求, 明确规格, 明确范围, 明确验收, or when a change needs its spec updated before code.
metadata:
  kind: workflow
  command: /prd
---

# prd

## 触发与输入

用于新增或修改当前有效 Feature spec、冻结范围与可测验收，不实现代码。输入是用户价值、已知路径、当前 plan/diff、OPEN 与验收意图；调用前不要求 owner manifest。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.prd`，可见输出由 canonical projector 生成。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定 exact target；读取最近子树 `AGENTS.md`，运行默认 compact `make feature-context TARGET=<exact-path>`，保存 stdout 的 immutable exact ref 后再加载 owner 与 canonical contexts。
2. 在最低可关闭节点更新 AppRoot Journey/UAT、L1 DOM、L2 SIT 或 L3 REQ/GWT，不跨层复制事实。
3. 每条验收写成可观察结果并可由真实 `local_contract/api_integration/user_acceptance` 测试绑定；字段、枚举、operation 与错误码只引用 canonical contracts，未实现事实进入 `OPEN-###`。
4. 运行 `make verify-feature-tree`；POST 复用 PRE 的同一 exact ref，报告命名 evidence 结果；默认零 Reviewer，只在用户显式 `/review` 或进入 lane→`dev1.0` PR / handoff 准出时按 review Skill 有界评审。

## 完成证据

当前 spec、范围、REQ/验收锚点、证据层、OPEN 去向、immutable ref 与验证命令均绑定当前工作树；未评审时如实标注。

## 失败与停止

用户价值、范围、target、owner、可测结果或 contract owner 不唯一时 `GATE_BLOCK` 并回 explore；门禁失败时不进 design/dev。

## 条件性交接

规格冻结后按设计门槛交 design，否则交 dev；传递 exact target、immutable ref 与验收锚点。仅在 canonical 六类 handoff 触发成立时持久交接。
