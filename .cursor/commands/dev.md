---
name: /dev
id: dev
category: Workflow
description: 实施特性（以 L3_story 为单位，逐项完成 Task）
---

> SDD 主流程：explore → prd → design → **dev** → commit → deploy

## Dev Gate

进入 `/dev` 前必须确认：

- `design.md` 已冻结
- codegen 已通过
- `tasks.md` 已就绪
- `acceptance.yaml` 可测量并映射 `T1~T4`
- 若涉及助手链路：已阅读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` 第 2~6 节，并确认优先改 asset / metadata / config，而非 runtime 硬编码

## 实施对象

- 实施单位：`L3_story`
- 执行清单：`Task`

禁止：

- 再使用“L4 Story”作为实施单位
- 把任务项当成树层级

## TDD 循环

每个 `Task` 按以下顺序执行：

```text
1. 对应验收项与测试层
2. 先写失败测试（Red）
3. 写最小实现（Green）
4. 重构（Refactor）
5. 回填 tests 证据
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

全部 `Task` 完成后：

```bash
make gate-full
```

并回写：

- `acceptance.yaml.archived=true`
- `tree_index.yaml` 对应 `L3_story.status=completed`

若涉及助手，还必须额外确认：

- 未新增 runtime 垂类特判
- 未新增字符串驱动的语义分类或行为分支
- 工具文案、提示词正文、检索策略均已回到真相源

## 结束输出

```text
实施完成：<feature-path>
L3_story: <story>
Task 完成：<N>/<N>
下一步：/commit
```
