# /prd

目标：冻结规格与验收，不做实现。

准入：`/explore` 已明确一棵树归属，目标用户、范围、Out of Scope、风险清晰。

产出：
- 对应层级 `spec.md`。
- 对应 `acceptance.yaml`，包含 UAT/SIT/GWT/contract 与 T1~T4。
- 如影响跨领域体验，更新 `journey_scenario_registry.yaml`。
- 关联或新建 `specs/changelog/CR-*.yaml`。

阻断：缺权限、生命周期、SLO/KPI、灰度回滚、metadata 真相源时返回 `GATE_BLOCK`。
