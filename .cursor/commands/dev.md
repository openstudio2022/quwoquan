---
name: /dev
id: dev
category: Workflow
description: 实施特性（以 L3_scenario 为单位，按 plan slice 推进）
---

> SDD 主流程：explore → prd → design → **dev** → commit → deploy

## Dev Gate

进入 `/dev` 前必须确认：

- `design.md` 已冻结
- codegen 已通过
- `plan.yaml` 已就绪
- `acceptance.yaml` 可测量并映射 `T1~T4`
- 目标 CR 已存在且已列出受影响节点
- 若涉及助手链路：已阅读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` 第 2~6 节，并确认优先改 asset / metadata / config，而非 runtime 硬编码

## 实施对象

- 实施单位：`L3_scenario`
- 正式执行清单：`plan.yaml` 中的 slice
- 会话执行清单：从 `plan.yaml` 派生的临时 todo

禁止：

- 再使用“L4 Story”作为实施单位
- 把会话 todo 当成真相源

## TDD 循环

每个会话 todo 按以下顺序执行：

```text
1. 读取 `plan.yaml` 与对应 CR
2. 选择本次要完成的 slice
3. 派生会话 todo（必须引用 `acceptance_refs`）
4. 先写失败测试（Red）
5. 写最小实现（Green）
6. 重构（Refactor）
7. 回填 `acceptance.yaml` 与 CR 的 tests/evidence
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

## 收口

目标 slice 完成后：

```bash
make gate-full
```

若涉及助手，还必须额外确认：

- 未新增 runtime 垂类特判
- 未新增字符串驱动的语义分类或行为分支
- 工具文案、提示词正文、检索策略均已回到真相源

## 结束输出

```text
实施完成：<feature-path>
L3_scenario: <scenario>
slice 完成：<N>/<N>
CR: <change-request>
下一步：/commit
```
