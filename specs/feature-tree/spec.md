# 应用根规格

## 定位

趣我圈是一套端云一体的社交、内容、关系、会话、搜索、助手和运营平台。特性树应用根是全 App 产品规格、知识、设计和测试底座，负责统一用户旅程、跨领域场景、全局术语、边界和 UAT。

## 范围

应用根覆盖：

- 全 App 的核心用户 Journey 与跨领域 Scenario。
- 产品领域服务的边界与协作关系。
- 用户需求到领域服务、业务能力、Story 的分解规则。
- UAT、SLO/KPI、灰度、回滚、观测和发布治理。
- 与代码工程、metadata、测试工程、部署工程的追踪关系。

## Out of Scope

应用根不承载：

- 单个 Story 的实现细节。
- 单个接口字段、错误码、路径和 DTO 设计；这些以 `quwoquan_service/contracts/metadata/**` 为真相源。
- 临时开发计划、会话 todo、PR checklist。
- 领域内部状态机和策略细节；这些归属对应业务能力。

## 分解规则

用户需求先映射到应用根 Journey / Scenario，再落到领域服务、业务能力和 Story：

```text
用户需求
  -> Journey / Scenario
  -> L1_domain_service
  -> L2_business_capability
  -> L3_story
```

判断原则：

- 跨多个领域服务的用户路径写入应用根 registry。
- 稳定产品领域写入 `L1_domain_service`。
- 一组可被 SIT 验证的能力写入 `L2_business_capability`。
- 最小可闭环价值点写入 `L3_story`。

## 全局验收关注点

- 用户旅程是否能以 UAT 证明价值闭环。
- 领域边界是否清晰，是否避免跨域职责漂移。
- 业务能力是否能以 SIT 验证组合行为。
- Story 是否有 GWT、接口契约和三层测试证据。
- 代码工程、测试工程、metadata、部署映射是否与特性树一致。
