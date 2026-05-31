# /baseline

目标：在需求稳定且方案收敛时，一次冻结 spec、acceptance、必要 design 与 CR。

准入：
- 一棵树归属已明确。
- UAT/SIT/GWT/contract 可测。
- T1~T4 证据矩阵可形成。
- 无重大架构分叉。

产出：`spec.md`、`acceptance.yaml`、必要层级 `design.md`、registry 更新、CR。

阻断：发现方案未收敛时，退回 `/prd` + `/design`。
