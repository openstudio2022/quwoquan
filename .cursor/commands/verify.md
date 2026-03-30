---
name: /verify
id: verify
category: Quality
description: 验证 Scenario / Journey 完成度、plan 覆盖率与 CR 证据
---

> SDD 主流程：... → dev → **verify** / commit → deploy
> AI Agent 在执行 `/dev` 时必须完成 verify 等价检查；`/verify` 用于独立复核、返工后重跑或人工显式发起质量审查。

`/verify` 只验证：

- `L3_scenario` 是否完成
- `L2_journey` 是否因本次增量受到影响
- `plan.yaml` 是否覆盖实施范围
- `acceptance.yaml` 是否闭环
- `CR` 是否记录了本次 delta 与影响
- `T1~T4` 证据是否存在

它不负责继续拆分需求或补做功能；若发现 BLOCKING，必须回到 `/dev` 的自主闭环继续修复，直到再次通过验证。

## 核查项

- 四件套是否齐全
- `plan.yaml` 的目标 slice 是否已完成
- `acceptance.yaml` 是否无 `pending`
- `implemented` 项是否有 `tests`
- `CR` 的 `affected_nodes`、`changed_documents`、`impact` 是否更新
- 是否仍残留旧层级

## 端侧 Mock / Remote 与发布态（Flutter）

若本次变更涉及 `quwoquan_app/lib/` 数据源、Repository、`appDataSourceModeProvider`、或 `main_prod`/构建脚本，还须对照 [`specs/gates/mock_data_cloud_integration_policy.md`](../../specs/gates/mock_data_cloud_integration_policy.md) **§5.1**：

- **发布态（R1–R6）**：Release 默认 Remote、无「切 Mock」用户入口、`Remote*` 不整表委托 `Mock*`、正式构建显式 `APP_DATA_SOURCE=remote`。
- **开发测试态（D1–D4）**：单一 Provider 一键切换；切换 UI 仅非 Release；Mock 数据仅在 `Mock*Repository` / `cloud/services/*/mock/` / `test/**`。
- **自动化**：`make verify-app-mock-isolation` 或 `python3 scripts/verify_ui_mock_isolation.py` 无 BLOCKING。

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
L3_scenario: <scenario>
L2_journey: <journey>
CR: <change-request>
BLOCKING: <N>
WARNING: <N>
```
