# 应用根设计

## 设计目标

应用根设计定义全 App 的长期架构和治理约束，确保产品规格、领域服务、业务能力、Story、代码工程和测试工程使用同一套概念。

## 全局分层

```text
产品与验收层
  AppRoot Journey / Scenario / UAT

领域服务层
  L1_domain_service

业务能力层
  L2_business_capability

最小价值层
  L3_story / GWT / contract

工程实现层
  quwoquan_app / quwoquan_service / quwoquan_data / agent_ops

契约与测试层
  contracts/metadata / local_contract / api_integration / user_acceptance
```

## 全局职责边界

- 应用根负责跨领域编排、UAT、全局架构、技术约束、观测、灰度和回滚。
- 领域服务负责 bounded context、产品领域边界、上下游依赖、服务治理和运行约束。
- 业务能力负责领域内状态、策略、数据流、端云协同和 SIT。
- Story 负责最小价值点、GWT、接口契约和最小测试证据。

## 工程映射

领域服务必须映射到以下工程资产：

- App UI：`quwoquan_app/lib/ui/{domain}`。
- App cloud：`quwoquan_app/lib/cloud/services/{domain}` 与 generated runtime。
- Metadata：`quwoquan_service/contracts/metadata/{domain}`。
- Service：`quwoquan_service/services/*-service`。
- Deploy：`deploy/shared/process_domain_mapping.yaml` 等部署映射。
- Test：`quwoquan_app/test/**`、`quwoquan_service/services/*/tests`、metadata tests。

## 技术约束

- metadata 是字段、错误码、路径、operation、surface、route 的唯一真相源。
- App UI 不直接依赖 mock 数据，必须通过 Provider / Repository。
- Go 服务遵循 DDD 分层：`domain <- application <- adapters <- infrastructure`。
- 测试工程层只使用 `local_contract`、`api_integration`、`user_acceptance`。
- `树内计划文档`、`树内任务文档`、Story 设计文档 不再是正式治理文档。

## 观测与发布治理

应用根设计要求所有可发布能力具备：

- SLO/KPI。
- 行为埋点和归因链。
- 弱网、性能、容量边界。
- 灰度策略和回滚条件。
- `api_integration/user_acceptance` 发布前证据。
