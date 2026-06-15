# L3 特性：multi-environment-wave-deployment

## 功能说明

四类逻辑环境（alpha、beta、gamma、prod）与**代码一套、配置分环境**，以及 `alpha-local -> beta-local -> prod-hosted` 的固定自动推进主链（gamma 仅本地 mirror，不在远端推进链上；远端/hosted 目标只有 prod-hosted）。`prod` 内部仍允许灰度/放量 wave（`gray-initial -> carry-on -> full`），但这些 wave 只属于 `prod`，不是额外环境。

## 范围

- 环境矩阵、Secrets、`Makefile` L3 环境变量
- 与 `gray_rollout_stages`、`deploy_prod_design`、`pre-release` 一致
- `main` 自动 promotion 所需的环境波次顺序、阶段证据与 900 秒预算约束

## 验收标准概要

- A1：存在可检索的 [environment_matrix.md](../../../../../deploy/shared/environment_matrix.md)
- A2：CI `l3-api-contract` 与 `make test-api-contract` 同时提供双 HTTP 基址
- A3：灰度 D/E 与 `prod` 映射在文档与 `gray_rollout_stages` 可核对
- A4：文档与 workflow 都明确保持 `alpha-local / beta-local / prod-hosted`（gamma 仅本地），不引入 `beta-hosted`、`prod-gray` 或远端 `gamma-hosted`
- A5：`main` 自动 promotion 的阶段顺序、阻断链与 900 秒预算在文档与执行链中一致
