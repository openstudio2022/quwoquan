---
name: /continue-dev
id: continue-dev
category: Workflow
description: 规划就绪后进入开发验证，或开发完成后复盘遗留风险、生成下一轮规划并继续开发
---

# /continue-dev

目标：把「规划就绪 → 开发 → 验证」与「开发完成 → 复盘 → 盘点遗留/风险 → 新一轮规划 → 再开发」收敛为一个持续开发闭环。执行时按最资深软件工程师标准裁决方案，零技术债，严格测试收口。

真相源：`specs/00_MASTER_DEVELOPMENT_FLOW.md`、特性树 `spec.md/design.md/acceptance.yaml`、`contracts/metadata/**`、`docs/outstanding_risks_backlog.md`、`.cursor/rules/**`。

## 两个使用场景

**场景 A：规划就绪后进入开发**

- 准入：已明确一棵树归属，且 `spec.md` / `design.md` / `acceptance.yaml` / 任务清单稳定。
- 动作：复核历史对话与当前规划，对齐目标、范围、Out of Scope 和任务清单；按 `/dev` + `/verify` 执行。

**场景 B：开发完成后复盘并继续开发**

- 准入：一轮 `/dev` / `/deliver` 完成，或一个里程碑收口。
- 动作：复盘当前实现，盘点遗留任务与剩余风险，必要时更新 `docs/outstanding_risks_backlog.md`；按 `/plan-next` 生成下一轮规划，收敛后回到场景 A。

## 硬约束

- **裁决最优方案**：争议由 Agent 主动裁决；以 DDD 领域模型、契约正确性、可扩展性、可维护性为准，不以工作量大小为准。
- **metadata-first**：字段、错误码、path、surface、operation、route、decoder context 以 `contracts/metadata/**` 为唯一真相源，先 verify/codegen，再写业务逻辑。
- **克制不过度设计**：不为单场景硬编码，也不为假想场景新增旁路分支、第二真相源或无必要抽象。
- **零技术债**：强相关技术债当轮清理；不保留 v1/v2 并存、shim、fallback、allowlist 扩张、死代码、弱类型穿透、空 catch、手改 codegen 或 UI 直连 Mock。
- **诚实完成**：未达成就标记 `GATE_BLOCK`，不得用新规划掩盖旧缺口，不得以「后续补」「临时兼容」「先绕过 gate」作为完成定义。
- **严格测试**：验收意图对齐 `UAT / SIT / GWT / contract`；测试证据覆盖 `local_contract / api_integration / user_acceptance`。`api_integration` Remote/API 断言必须能在 `local_contract` Mock/Provider/Widget 中找到对应覆盖。

## 执行

1. 读取 `docs/agent_context_contract.md`，完成 `Spec Entry` 与 `Pre-work Reflection`；对照 `docs/agent_command_simulation_matrix.md` 确认阶段、禁止事项与出口证据。
2. 审视 `docs/outstanding_risks_backlog.md`、相关 `spec/design/acceptance`、registry、CR 和历史对话，形成当前 todo。
3. 按 metadata/codegen、seed、mock、权限、生命周期、观测、灰度、回滚自检后执行 Red → Green → Refactor。
4. 回填测试证据，运行触发范围门禁；场景 B 额外输出复盘、遗留/风险台账与下一轮规划。

## 出口

- 输出 `Exit Review`：规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁、剩余风险。
- 场景 A：实现闭环且分层测试与触发范围门禁绿。
- 场景 B：复盘结论、遗留/风险台账与下一轮规划（目标/规格/任务清单/验收标准）齐备，且不掩盖本轮未完成项。
- 明确未跑验证的原因；若发现规格/验收缺口，停止并退回 `/prd`、`/design` 或 `/plan-review`。

## 阻断（返回 `GATE_BLOCK`）

- 一棵树归属、规格、验收或三层测试证据矩阵不清。
- 出现 metadata 真相源漂移、v1/v2 并存、shim、fallback、allowlist 掩盖问题。
- 强相关技术债未清理，或只完成局部端、部分测试、无证据状态。
- 场景 B 存在未达成且无证据项，却试图直接进入下一轮规划。

自然语言等价触发：用户说「规划好了开始开发」「按规划进入实施」「这一轮做完了，复盘一下再继续开发」「盘点遗留和风险后开下一轮」「接着往下开发」时，也按 `/continue-dev` 语义执行；若规格或验收不清，先退回 `/explore`、`/prd` 或 `/plan-review`。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
