---
name: /deliver
id: deliver
category: Workflow
description: 增强交付入口（/dev 自主闭环后直接 /commit，面向 L3_scenario）
---

> SDD 主流程：design → **deliver** → deploy

`/deliver` = 增强 `/dev` + `/commit`

其中增强 `/dev` 已包含：

- 任务级 plan mode 审视
- 前后端与 metadata/codegen 的完整实施
- `T1~T4` 与商用条件闭环
- verify 等价检查
- archive 等价回写

目标：

- 完成 `L3_scenario`
- 完成目标 slices
- 通过门禁
- 完成自动归档
- 完成 CR 修订
- 完成提交

测试口径只使用：

- `T1`
- `T2`
- `T3`
- `T4`
