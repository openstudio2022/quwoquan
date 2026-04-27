# L3 特性：multi-environment-wave-deployment

## 功能说明

五类逻辑环境（本地、CI、integration、生产灰度、生产全量）与**代码一套、配置分环境**、`STAGING_*` 与 integration 的对应，以及 B→C→(D→E) 大波段 + prod 内小 wave 的落档与门禁对齐。

## 范围

- 环境矩阵、Secrets、`Makefile` L3 变量别名
- 与 `gray_rollout_stages`、`deploy_prod_design`、`pre-release` 一致

## 验收标准概要

- A1：存在可检索的 [environment_matrix.md](../../../../../deploy/shared/environment_matrix.md)
- A2：CI `l3-api-contract` 与 `make test-api-contract` 同时提供双 HTTP 基址
- A3：灰度 D/E 与 `prod` 映射在文档与 `gray_rollout_stages` 可核对
