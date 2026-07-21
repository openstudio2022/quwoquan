# L3 Story：capability-provider-commercial-readiness-gate

## 用户价值

只有真实可用、可观测、可降级、可切换和可回滚的外部能力才能进入生产。某个替代实现
可用，不代表目标厂商 Adapter 已完成；测试文件存在，也不代表能力已商用。

## 双层准出

- `adapter_ready`：指定 Adapter 完成真实鉴权、调用/回调、错误映射、脱敏、指标告警、
  Beta/Gamma Conformance 与巡检。
- `capability_ready`：至少一个 production-grade Adapter ready，且 Capability 的九格、
  用户 Journey、切换、降级与回滚全部通过。

两个状态均由同一 commit、image、config、ContractGraph、Adapter digest 的证据计算，
禁止人工翻牌或跨 Adapter 借用证据。

## 启动与运行门

- Gamma/Prod 的 required Provider 缺 Binding、Secret、初始化或健康探针时启动失败。
- optional Provider 不可用时只允许结构化关闭并提供用户指引。
- readiness 不泄露 endpoint/Secret；只输出 ID、状态、版本、digest 和 evidence URI。
- Provider 失败不得返回 fixture、空集合、固定成功或自动切 Mock。

## 切换与回滚

- 仅允许在两个 `adapter_ready=true` 的 production-grade Adapter 之间切换。
- 切换前验证合同、数据驻留、幂等、callback、成本、SLO 与用户 Journey 兼容。
- 切换后收口旧请求/callback/队列，按 release/adapter 维度观察。
- config+image 成对灰度和回滚；回滚后验证健康、数据结果、观测和用户连续性。

## 完成条件

- 机读 gate 能区分 configured/ready/degraded/unavailable 与 adapter/capability 两级状态。
- Gamma 九格 PASS 是 Prod deploy 前置。
- `prod-hosted gray_initial` 只做真实租户低风险 smoke、SLO/告警和回滚演练，不替代 Gamma。
- 缺真实凭据、设备或远端租户时诚实保持 blocked，不生成伪证据。
