---
name: /dev
id: dev
category: Workflow
description: 实施特性（以 L3_scenario 为单位，按 plan slice 推进）
---

> SDD 主流程：explore → prd → design → **dev** → commit → deploy
> 快捷链路：explore → baseline → **dev** → commit → deploy

## Dev Gate

进入 `/dev` 前必须确认：

- `design.md` 已冻结
- codegen 已通过
- `plan.yaml` 已就绪
- `acceptance.yaml` 可测量并映射 `T1~T4`
- 目标 CR 已存在且已列出受影响节点
- 若涉及助手链路：已阅读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` 第 2~6 节，并确认优先改 asset / metadata / config，而非 runtime 硬编码

## 执行姿态

AI Agent 执行 `/dev` 时，必须先进入**任务级 plan mode**，全面审视：

- `spec.md`
- `design.md`
- `plan.yaml`
- `acceptance.yaml`
- 对应 `CR`
- 前后端影响面、metadata/codegen、权限边界、数据生命周期、灰度/回滚、观测与商用条件

若审视后发现以下问题，**不得停下等待新指令**，而是先自动修复再继续实施：

- 需求、设计、切片或验收标准不完整
- 前后端任务拆分不足，无法支撑端到端交付
- `T1~T4` 证据矩阵缺口
- 商用条件缺口：权限、生命周期、SLO/KPI、弱网、并发、灰度、回滚、观测
- metadata / codegen / CR / acceptance 回写缺口

## 实施对象

- 实施单位：`L3_scenario`
- 正式执行清单：`plan.yaml` 中的 slice
- 会话执行清单：从 `plan.yaml` 派生的临时 todo
- 默认交付目标：一次完成目标 scenario 所需的前端、后端、metadata/codegen、配置、文档与测试闭环，达到可商用状态

禁止：

- 再使用“L4 Story”作为实施单位
- 把会话 todo 当成真相源
- 仅完成部分 slice、部分端、部分测试后就停下等待下一条指令
- 明知验收、设计或商用条件未闭环，仍宣布 `/dev` 完成
- 把缺失的前后端工作、测试工作或文档回写留到 `/commit` 前再补

## 执行闭环

每次 `/dev` 会话按以下顺序执行，直到目标 scenario 达到端到端可商用交付：

```text
1. 进入任务级 plan mode，通读 spec/design/plan/acceptance/CR
2. 审视前后端、metadata/codegen、商用条件与 `T1~T4` 缺口
3. 若基线或切片不完整，先自动补齐相关文档与验收/计划
4. 派生覆盖全部未完成 slices 的会话 todo（必须引用 `acceptance_refs`）
5. 对每个 todo 执行 Red → Green → Refactor
6. 完成前后端功能、契约、配置、观测、权限、灰度/回滚等所有缺口
7. 回填 `acceptance.yaml`、`plan.yaml`、CR 的 tests/evidence/status
8. 执行 verify 等价检查并修复所有阻塞项
9. 验证通过后自动执行 archive 等价回写
10. 输出完成报告并等待 `/commit`
```

## G2

每完成一组任务后执行：

```bash
make build
make test-contract
```

若涉及 Flutter 变更，追加：

```bash
flutter test test/cloud/ test/components/ test/ui/
```

若目标 scenario 涉及真实端云联动、发布 guardrail 或用户可见关键路径，必须继续补齐所需的 `T3` / `T4` 证据，而不是只停在 `T1` / `T2`。

## 收口

目标 scenario 的前后端功能、验收与商用条件完成后，必须继续执行：

```bash
make gate-full
```

`make gate-full`、`acceptance.yaml`、`CR`、四层测试证据或非功能条件存在问题时，AI Agent 必须继续修复并重跑，直到：

- 无 BLOCKING 漂移
- `T1~T4` 证据满足目标场景要求
- 验收无 `pending`
- 商用条件闭环
- 可执行 archive 回写

验证通过后，AI Agent 必须自动完成 `/archive` 等价动作：

- 回写 `acceptance.yaml.archived`
- 回写 `tree_index.status`
- 生成归档报告

若涉及助手，还必须额外确认：

- 未新增 runtime 垂类特判
- 未新增字符串驱动的语义分类或行为分支
- 工具文案、提示词正文、检索策略均已回到真相源

## 结束输出

```text
实施、验证与归档完成：<feature-path>
L3_scenario: <scenario>
slice 完成：<N>/<N>
CR: <change-request>
verify: PASS
archive: DONE
下一步：/commit
```
