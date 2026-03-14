---
name: /verify
id: verify
category: Quality
description: 验证 L3_story 完成度、测试证据与门禁状态
---

> SDD 主流程：... → dev → **verify** / commit → deploy

`/verify` 只验证：

- `L3_story` 是否完成
- `Task` 是否收口
- `acceptance.yaml` 是否闭环
- `T1~T4` 证据是否存在

## 核查项

- 四件套是否齐全
- 当前交付任务是否都已完成
- `acceptance.yaml` 是否无 `pending`
- `implemented` 项是否有 `tests`
- 是否仍残留旧层级

## 助手专项核查

若本次交付涉及助手链路，还必须核查：

- 是否已引用 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
- 是否新增 runtime 垂类特判
- 是否新增字符串驱动的语义路由、阶段判断或工具策略
- 是否引入第二真相源（tool 文案、skill 策略、prompt 模板、权限矩阵）
- 回归测试是否以合同和结构为主，而不是以垂类样例文案为主

## G3

```bash
make gate-full
```

## 输出

```text
验证报告：<feature-path>
L3_story: <story>
BLOCKING: <N>
WARNING: <N>
```
