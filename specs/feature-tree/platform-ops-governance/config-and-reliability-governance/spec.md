# L2 特性：config-and-reliability-governance

## 功能说明
- 承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- 作为 `Platform Ops` 一级菜单中“配置中心 / 治理策略 / 发布灰度 / 环境与依赖”的特性树承载层。
- 为各领域的 `platform-control-plane` 提供统一接入模型，要求通过 `control_plane.yaml` 与 `config_schema.yaml` 等元数据声明，并由 codegen 生成契约。

## 约束
- 仅管理 `sys.*` 系统配置、治理策略、配置包、发布回滚、环境差异与依赖差异。
- 不承载审核、实验、人群灰度、推荐运营等 `ops.*` 业务策略。
- 控制面契约必须独立于用户面 API，不得依赖当前同 Pod 部署。
- 高风险配置必须具备灰度、回滚、审计与危险动作确认能力。
- 各领域接入时必须声明最低 `platform-control-plane` 对象集合。

## 验收标准
- A1：配置中心、治理策略、发布灰度、环境与依赖四类平台能力边界明确。
- A3：高风险配置、治理策略和发布回滚支持灰度与回滚。
- A4：配置与治理变更可审计、可检索、可告警。
- A7：`control_plane.yaml`、`config_schema.yaml` 与 codegen 契约一致。
- A8：可无歧义进入 `/design` 细化门户模型、对象模型、部署模型与 codegen 方案。
