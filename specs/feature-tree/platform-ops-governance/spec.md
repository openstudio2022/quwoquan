# L1 Domain Service：platform-ops-governance（运维横切） (`platform-ops-governance`)

> 一句话定位：建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。

## 1. 目标与用户价值

建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。

## 2. 领域边界

### 本领域拥有

- 拥有平台配置发布、可靠性策略、观测告警、运维审计与生产准出证据的生命周期和治理决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- 当前 AppRoot Scenario 不直接经过本领域；本领域只提供被业务领域调用的横切能力。

## 4. 业务能力

- [`commercial-readiness-risk-closure`](./commercial-readiness-risk-closure/spec.md)：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- [`config-and-reliability-governance`](./config-and-reliability-governance/spec.md)：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- [`observability-and-alerting`](./observability-and-alerting/spec.md)：建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。
- [`security-privacy-audit`](./security-privacy-audit/spec.md)：统一发布前与运营期的权限、隐私、审计和供应链检查

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 platform ops governance 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力

- 建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。
- 作为统一 Web 门户 `ops-portal` 中 `Platform Ops` 工作域的特性树承载层。
- 所有服务必须接入统一治理策略，不允许按服务自定义核心口径。
- 语义 token、错误码、追踪头、治理参数必须标准化。
- 运维高风险变更必须具备灰度与回滚。
- 面向 `platform-ops` 的管理接口必须从统一控制面元数据生成，禁止手写临时 admin API。
- 三类面必须保持契约与部署拓扑解耦；第一方服务拥有独立 workload 定义，跨服务装配不得引入组合业务 `seed-box`。
- 契约设计不得依赖当前部署拓扑，避免后续拆 Pod 返工。
- 可观测统一且可检索

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 platform ops governance 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_ops`
- Contracts：`quwoquan_service/control-plane/platform-ops/contracts`
- Service：`quwoquan_service/control-plane/platform-ops`
- 测试：
  - `local_contract`：`quwoquan_ops/tests`
  - `api_integration`：`quwoquan_service/control-plane/platform-ops`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 platform ops governance 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效
