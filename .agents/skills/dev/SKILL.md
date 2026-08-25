---
name: dev
description: Implement a frozen Story, capability, or object-level extension and close the loop with real tests - metadata-first, then verify/codegen, then Red/Green/Refactor. Use when the user says 实现, 修复, 开始写代码, 加字段, 加接口, 加事件, 加查询, 加对象, 加存储 adapter, 新建服务, or asks for a code change whose spec and design are already settled.
metadata:
  kind: workflow
  command: /dev
---

# dev

实现已冻结的 Story、能力或对象级扩展并闭环验证。五段执行契约见根 `AGENTS.md`。

## 触发

- 显式命令 `/dev`。
- 自然语言：实现、修复、开始写代码；以及对象级扩展请求——加字段 / 加接口 / 加事件 /
  加查询 / 加对象 / 加存储 adapter / 新建服务 / 补测试证据（走本工作流的对象扩展子流程）。

## 输入

- `prd` 或 `design` 的 HANDOFF：唯一父链、验收锚点；涉及对象边界时附
  `owned_entity` vs `separate_aggregate` 裁决与 command/query 分流结论。断链即 `GATE_BLOCK`。
- [MUST] `make feature-context TARGET=<target>` 得到**唯一**父链。
- [MUST] L3 REQ/GWT 与设计归属稳定；父 L2 SIT、L1 DOM 与受影响 AppRoot UAT 可追踪。
- [MUST] 相关 `OPEN block` 已明确处置。

## 角色

主会话扮演 **implementer**：DURING 以 checklist copy-in 方式持续消费 PRE 评审选出的
checklist 约束（复制进回复并逐项勾选）；对象扩展分流由本工作流内部判定。

## 执行

自由度：低（固定序列，失败即停）。

1. 读父链、相关 DEC、metadata 与对应测试。**不扫描整棵树。**
2. 从 REQ/GWT/SIT/UAT 与当前会话计划派生 todo；不创建 tracked task 或 plan。
3. 按改动类型分流：
   - **对象级扩展**（加字段/对象/接口/查询/事件/adapter/new-service 等）：
     按 [references/object-extension.md](references/object-extension.md) 的场景裁决与
     固定顺序执行 metadata → validate → codegen → Facade/Ports → composition root → 三层测试。
   - **普通 Story**：**metadata-first → verify/codegen → Red → Green → Refactor**。
4. 每个有 validator 的步骤按「跑验证 → 修复 → 重跑」闭环，验证不过不得进下一步。
5. Remote/API 断言必须在 local_contract 的 Provider/Widget/领域规则中有对应覆盖；
   用户旅程变化补 user_acceptance。

落位前逐项自检：

- **可测试性** — 新逻辑可从 canonical 测试树观察（导出 API 或对象级 typed port）。
  [MUST NOT] 为可测性发明 test-only 后门。横切区（`runtime/internal/tools/cmd`）
  旁路同包测试必须以 `__local_contract_test` 层后缀命名；api_integration 禁止旁路同包。
- **读写分离** — 新增消费入口只依赖对象级 `*CommandWriter/*Query` typed port。
  [MUST NOT] 聚合 Repository、动态 Filter/Map，或为展示路径加载 aggregate。
- **领域与服务规范** — 服务侧遵循 DDD 依赖方向与对象边界，跨对象只依赖 port 或事件。
  边界冲突回 `design`，**不在实现里就地发明**。
- **前端规范** — 触及 `quwoquan_app/lib` 时按 `quwoquan_app/AGENTS.md` 与 PRE 评审装配的
  developer / ux / architect checklist 自检。Provider/Widget 测试以
  `sealedCloudBoundaryOverrides()` 开头；[MUST NOT] 新增聚合 Mock 替身（棘轮只减不增）。
- **失败处理** — 测试红先归因四选一：
  `本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky`。
  并行中间态**不修不掩盖**，如实交接。

交互协议（[interaction-protocols](../review/references/interaction-protocols.md)）：
每完成一个子任务、每次意外失败、每次准备扩大改动面，按协议 4 对照反串讲承诺做
三级裁决；跨界判定用 `git status` 并行交集自查，禁止顺手扩围修复。

## 交付件

**实现增量**：代码 / metadata / 测试 diff、受影响 metadata 路径与目标测试结果。

送审前自检：

- 影响面测试与 `make verify-feature-tree`、`make feature-tree-change-report` 已跑；
- 未运行的验证已说明原因，**失败未包装为通过**；
- 无未归属业务变更。

## 内置评审

- PRE：调 `review`（workflow=`dev`，segment=PRE）装配 role/profile bundle 并判准入。
- POST：调 `review`（workflow=`dev`，segment=POST，deliverable=`implementation`），
  角色与 gate 由 profile 决定（见 review registry）；评审通过后才形成可供
  `plan-next` / `commit` 消费的 HANDOFF。

## 失败与停止

- 不得发明规格或架构；目标父链、对象边界或验收不稳定时退回 `prd` / `design`。
- [MUST NOT] 让代码反向定义规格。
- 对象扩展固定顺序中任何一步失败**立即停止**；
  [MUST NOT] alias、fallback、双读、双写、动态 skip、allowlist 或放宽测试阈值。

## HANDOFF

- **完成判据**：见 [completion-criteria](../review/references/completion-criteria.md) 本工作流段；证据链条目带命令+退出码+时间戳+SHA，下游过期即复跑。
- **产出物**：实现增量 + POST 评审结论。
- **未决项去向**：残量转最低 owner 节点 `OPEN-###`，或判 Out of Scope；
  并行会话交接项双向列出。
- **唯一合法下游**：`plan-next`；用户明确要求提交时 `commit`。
- **证据链**：三层测试结果、门禁输出、失败项及其归因、POST 评审报告。
- **交接单**：轮次结束落 `.qwq_output/env/repo/runs/handoff/<轮次>/manifest.md`，过 `make verify-handoff-manifest` 后交接。
