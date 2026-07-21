# L2 特性：runtime-external-integration

## 0. Spec Entry

- **AppRoot Journey / Scenario**：所有依赖外部 Provider 的可发布 Journey；首个显式回链为
  `message-social-connection / message-call-and-offline-delivery`。
- **L1_domain_service**：`runtime`。`integration-service` 是由 runtime 治理的独立部署进程，
  不是新的 L1 领域服务。
- **L2_business_capability**：`runtime-external-integration`。
- **L3_story**：`integration-service-foundation`、
  `integration-service-foundation--location-nearby-search-gateway`、
  `provider-adapter-conformance-suite`、
  `capability-provider-commercial-readiness-gate`。
- **验收意图**：L2 使用 SIT；L3 使用 GWT / contract；用户可感知的 Provider 故障、
  降级与恢复回链 AppRoot UAT。
- **测试证据**：`local_contract`、`api_integration`、`user_acceptance`。Alpha、Beta、
  Gamma 是执行环境维度，不是第四测试层。

## 1. 目标与用户价值

外部 SDK、endpoint、鉴权、错误码、回调 DTO、重试与限流差异不得穿透业务代码。每项
外部能力采用唯一链路：

```text
业务/领域能力 -> 能力专属 typed Port -> Provider Adapter -> 外部服务
```

业务只消费稳定请求/响应、`RuntimeFailure + RuntimeRecoveryPolicy`、deadline/cancel、
幂等键、观测上下文与隐私分类。Provider 不可用时必须产生真实失败、明确降级或阻断发布，
不得返回 fixture、空集合、固定成功或自动切换 Mock。

## 2. 范围

### 2.1 In Scope

- 已存在或产品已声明 required 的外部能力：日志/SLS、对象存储/CDN、RTC、模型/Embedding、
  Push/SMS、OAuth/一键登录、Realtime、搜索、内容安全与 Redis 共享消息传输。共享消息能力
  必须通过 provider-neutral boundary、全部实际组合根的启动预检和真实 consumer 证据后才可
  标为 release-required；NATS 与 DNS 仍仅保持资产登记。
- 能力合同、Adapter 库存、环境 Binding、binding root、readiness、供应链、观测、成本、
  降级、切换、回滚与商用证据。
- Alpha/Beta/Gamma × `local_contract/api_integration/user_acceptance` 九格证据。
- Capability 与具体 Vendor Adapter 两级独立准出。

### 2.2 Out of Scope

- 为尚无产品需求的邮件、支付等能力预造 Port。
- 把所有 Provider 强制代理到 `integration-service`。
- 在运行时扫描 metadata、动态注册对象或按字符串反射选厂。
- 用 Prod smoke 替代 Gamma 证据，或用替代 Provider 的通过状态提升目标厂商 Adapter。

## 3. 访问策略

每个 Adapter 必须登记且恰属一种策略：

- `central_integration`：跨业务域复用、需要服务端鉴权/审计的 SaaS，经
  `integration-service` 对象 Facade 暴露。
- `domain_owned_adapter`：只服务一个业务对象的外部实现，位于该服务
  `internal/infrastructure/<context>/<object>/**`。
- `client_platform_adapter`：设备 SDK/原生能力，经 `quwoquan_app/lib/core/platform/**`
  防腐接口和 capability profile 装配。
- `data_pipeline_adapter`：离线公开源或数据加工 Provider，经 `qwq-data` CLI-first
  工作流接入。
- `runtime_shared_adapter`：由多个静态组合根共同消费的基础设施能力。每个 root 必须在
  编译期 receipt 中显式登记，并在启动时对同一环境 Binding 执行 fail-closed preflight；
  不允许任一 root 自行选择 Adapter。

豁免仅表示不经过 `integration-service`；不豁免 typed Port、注册表、错误合同、隐私、
Conformance Suite、环境 Binding 与商用门禁。

## 4. 真相源

- 请求/响应、operation、错误、隐私与对象边界：
  `quwoquan_service/contracts/metadata/**`。
- Provider/SDK/Adapter 库存及 `capability_id -> adapter_id`：
  `docs/external_service_registry.yaml`。
- 每环境主备、endpoint/secret 引用与启动策略：
  `quwoquan_ops/environments/external_provider_bindings.yaml`。
- Conformance 执行映射：
  `quwoquan_ops/environments/provider_conformance_manifest.yaml`。
- 场景语义与完成条件：本能力及 L3 的 `acceptance.yaml`。
- 可删除运行事实：`.qwq_output` 规范化 evidence；它永远不是配置或环境真相源。

## 5. 环境与测试合同

- **Alpha**：本地、内存、可控模拟或轻量参考实现；必须执行真实合同、状态机、异常注入与
  完整旅程，禁止固定成功。
- **Beta**：远端沙箱、轻量真实服务、自建兼容服务或厂商测试环境；验证 TLS、鉴权、
  callback、retry、timeout、throttle 与真实协议，禁止纯内存替代远端。
- **Gamma**：生产级 Adapter 连接隔离 Gamma/沙箱租户；验证真实凭据、真实调用、观测、
  切换与回滚，禁止 Mock/Fake/InMemory/Noop/fixed-test/deterministic。
- **Prod**：只有 `prod-hosted`；低风险真实租户验证发生在 `gray_initial`，不得反写成
  Gamma 或目标 Adapter 的历史证据。

Beta/Gamma 的 `local_contract` 对真实 Adapter 类运行同一场景的本地协议/故障 harness，
永不访问外网；真实远端调用只属于 `api_integration`。九格每格必须记录场景、文件、命令、
Adapter/config/ContractGraph digest、网络边界、数据 digest、断言/skip、观测引用与
acceptance refs。

## 6. 错误、隐私与可观测

- 第三方原始错误只在 Adapter 内转换为 metadata 生成的稳定错误和
  `RuntimeRecoveryPolicy`；context 仅使用 string-only attributes。
- deadline、cancel、幂等、retry/throttle 必须由能力合同约束，调用方不得猜测 Vendor 行为。
- credential、token、原始 endpoint、PII/SECRET 不得进入日志、trace、metric label、
  readiness 或 evidence；只允许引用 ID、digest 与脱敏状态。
- 每项 required 能力必须有可查询的成功率、错误率、P95/P99、throttle、retry、
  dependency health、成本/配额与切换标识；告警和回滚使用同一 `capability_id/adapter_id`。
- `runtime.message.transport` 额外以 `binding_root + adapter_id + operation` 维度记录
  ephemeral publish、durable append/consume/ACK/reclaim、pending lag、DLQ 与 preflight；
  5 分钟窗口内 durable append/consume P95 不得高于 250ms、成功率不得低于 99.9%，
  任一 consumer group pending 超过 1,000 或出现非零 DLQ 增量必须停止 rollout 并进入
  受控恢复。阈值、告警与 last-good rollback receipt 必须由同一 release evidence 引用。

## 7. Readiness、降级与回滚

- `adapter_ready=true`：该 Adapter 的公共/专项 Conformance、Beta/Gamma 真实证据、鉴权、
  读写/回调、错误映射、脱敏、指标告警和巡检全部通过。
- `capability_ready=true`：至少一个 production-grade Adapter ready，且 Capability 九格、
  用户旅程、切换与回滚全部通过。
- Gamma/Prod 缺 required Provider、凭据、初始化或健康探针时启动失败。
- optional 能力只能以结构化 unavailable/degraded 关闭并提供用户指引；禁止假成功或
  自动切 Mock。
- 切换只允许在两个 ready Adapter 之间进行；必须验证数据/合同兼容、用户旅程连续、
  指标口径一致、旧 callback 收口和 config+image 成对回滚。

## 8. 商用阻断

任一条件成立即 `GATE_BLOCK`：

- 无能力专属 Port，或业务代码直接依赖 Vendor SDK/type/endpoint/error/DTO。
- required 能力无 Beta 真实远端或 Gamma production-grade Adapter。
- Conformance Suite 未执行、九格有空白/NOT_RUN/required skip/零断言/旧 digest。
- 启动缺配置仍报 ready，外部失败返回 fixture/空集合/固定成功，或日志/evidence 泄密。
- `.qwq_output` 被用作配置、环境 Binding、schema、policy、Secret 或 TLS 真相源。
