# Design: runtime-external-integration

## 1. 设计目标

本能力把第三方依赖治理为编译期可验证、启动时 fail-closed、运行时可观测、发布时可回滚的
typed Adapter 系统。`integration-service` 是其中一种部署形态，不是所有外部依赖的万能
代理，也不是新的 L1 领域服务。

## 2. 总体架构

```text
metadata capability contract ─┐
provider registry ────────────┼─> build-time BindingCompiler
environment bindings ─────────┘        │
                                       v
业务对象 -> typed Port -> explicit CompositionRoot -> Provider Adapter -> Provider
                                       │                     │
                                       v                     v
                                  capability readiness   conformance evidence
```

一项能力只能有一个 canonical Port 和一套业务请求/响应/错误语义。不同 Adapter 可以使用
不同 SDK/协议，但 Vendor 类型、endpoint、鉴权、callback DTO、重试与限流差异不能越过
Adapter 边界。

## 3. 分层与部署边界

### 3.1 central_integration

`integration-service` 按 metadata 业务对象提供 command/query Facade。对象拥有自己的
domain/application/infrastructure 边界；禁止恢复跨对象通用 CRUD 或万能 Provider 接口。
SMS、Push、位置等跨域能力可采用该策略。

### 3.2 domain_owned_adapter

只服务单一对象的外部实现放在对象所属服务
`internal/infrastructure/<bounded-context>/<object>/**`，application 只依赖对象专属 Port。
对象存储、搜索、LLM 等是否采用该策略由 registry 显式声明。

### 3.3 client_platform_adapter

设备 SDK 经 `quwoquan_app/lib/core/platform/**` 的 platform-neutral Port 装配。业务/UI
只读取 capability 并使用统一 DTO/RuntimeFailure；LiveKit、CallKit、PushKit、FCM/APNs
原生类型不得进入 UI、Provider state 或 cloud contract。

### 3.4 data_pipeline_adapter

数据公开源和模型/素材 Provider 经 `qwq-data` CLI-first pipeline 接入。schema、prompt、
template、policy 与 reference 留在 `quwoquan_data/**`，执行产物才进入 `.qwq_output/data`。

## 4. 单轨注册与编译

### 4.1 输入

- `quwoquan_service/contracts/metadata/**`：能力与对象合同。
- `docs/external_service_registry.yaml`：Capability、Adapter、SDK/SBOM 与治理属性。
- `quwoquan_ops/environments/external_provider_bindings.yaml`：环境选择、主备和 SecretRef。
- `quwoquan_ops/environments/provider_conformance_manifest.yaml`：验收场景到执行入口映射。

### 4.2 BindingCompiler

compiler 在构建/门禁阶段加载上述输入，校验：

- capability、canonical Port、binding scope/root 与 Adapter 实现路径存在且唯一；
- Adapter 的 access policy、allowed env、production-grade、conformance profile 完整；
- 环境 Binding 只引用已登记 ID，required 能力恰有一个 primary；
- Gamma/Prod 不引用 Mock/Fake/InMemory/Noop/fixed-test/deterministic；
- 每项 release-required Capability 的 `binding_scope + binding_roots`、checked-in Go
  descriptor、entrypoint 与 resolver symbol 完整且双向一致；descriptor drift、任一
  root 未消费或 root 自选 Adapter 即阻断。
- composition root、依赖/SBOM、acceptance 与注册表双向一致。

输出是按 binding root 投影的 typed descriptor/codegen 或构建期 receipt；同一 Capability
在每个 root 只投影同一环境选择，禁止 root 自行选择具体类型。单 root 能力使用
`root_composed`，共享基础设施使用 `shared_multi_consumer`；两者都使用同一
`binding_roots` schema。未实现 provider-neutral infrastructure boundary 的登记能力
（当前 NATS、DNS）不产生 release descriptor、不参与 release readiness。
服务启动不得扫描 metadata/registry、动态注册对象或按字符串反射选厂。

## 5. 运行时模型

每项 binding root 接收的绑定形成：

```text
CapabilityBinding {
  capabilityId
  adapterId
  required
  productionGrade
  endpointRef
  secretRefs
  timeoutPolicyRef
  retryPolicyRef
  evidenceProfile
}
```

`endpointRef/secretRefs` 是外部配置系统的引用，不是实际值。启动 preflight 解析有效配置、
初始化 Adapter、执行轻量健康探针并生成脱敏 readiness；required 任一步失败即进程
fail-closed。optional 失败仅产生结构化 unavailable，不得本地合成成功。

## 6. 错误与恢复

- Adapter 将 Vendor 错误映射到 metadata 生成的 `RuntimeFailure`。
- 恢复行为只来自 `RuntimeRecoveryPolicy`，不作为错误事实硬编码在业务/UI。
- timeout、cancel、retry、throttle、idempotency 属于能力合同；Adapter 可以实现 Vendor
  差异，但不得改变调用方可观察语义。
- HTTP 边界使用 `runtime/errors` 的 `RuntimeErrorResponse` 并保留 request/trace id；
  App 端由 runtime mapper 生成 `CloudException.runtimeFailure`。

## 7. Conformance 与 3×3 证据

公共 suite 至少覆盖 success、validation、auth failure、DNS/network、timeout、throttle、
retry、idempotency、callback/duplicate/out-of-order、redaction 与 observability。能力专项
profile 补充 SLS readback、MQ ack/ordering/DLQ、DNS TTL/NXDOMAIN/TLS、RTC 媒体/离线来电、
LLM stream/tool/usage 等场景。

同一 scenario ID 可由 Go/Dart/Python 原生 harness 实现；共享的是场景语义、fault model 和
evidence schema，不强制共享测试代码。环境维度与三层测试正交：

- `local_contract`：不出网的合同/故障 harness；
- `api_integration`：真实协议、TLS、鉴权、远端读写/回调；
- `user_acceptance`：真实页面、设备或运营旅程及恢复结果。

聚合器只接受当前 commit、image、config、ContractGraph 和 Adapter digest 一致的报告。
NOT_RUN、required skip、零断言、dry-run、缺观测或旧 digest 都阻断。

## 8. Readiness 状态机

```text
unconfigured -> configured -> initialized -> healthy -> adapter_ready
                                            \-> degraded/unavailable

adapter_ready + capability 3×3 + switch/rollback -> capability_ready
```

替代 Provider 的通过状态不能提升另一个 Adapter。readiness 只输出 ID、版本、digest、
状态、失败分类与 evidence URI，不输出 endpoint/credential。

## 9. 切换、降级与回滚

- primary/secondary 都必须先达到 `adapter_ready`。
- 切换以 config+image 对为原子发布单位，指标按 release/adapter 隔离。
- 切换前验证请求/响应、幂等键、callback、数据驻留、成本和 SLO 兼容。
- 切换后收口旧请求、队列与 callback；失败回滚 last-good config+image，并验证用户 Journey
  连续和指标口径未漂移。
- 无 ready 替代时只能关闭 optional 能力、向用户解释或阻断 rollout，不能切 Mock。

## 10. 输出与 Secret 边界

- 配置、binding、schema、policy、构建规则在受版本控制目录。
- 本地渲染配置、临时 `.env`、Secret 与证书位于仓外
  `QWQ_DEPLOY_WORK_ROOT/<target>/{rendered,secrets,certificates}`。
- `.qwq_output/env/<env>/runs` 只放报告/回执，`observability` 放 logs/traces/metrics，
  `local/<target>/process` 只放 PID/状态，`release` 只放可重建派生包。
- evidence 只记录 ref/digest；删除 `.qwq_output` 后必须能从源码与显式外部依赖重建。

## 11. 供应链与发布

App/Service/Data/Ops 的 SDK、镜像和二进制必须反查 registry，记录 version、digest、
license、CVE、签名与支持平台。Gamma 九格和能力 readiness 是 Prod deploy 前置；
`prod-hosted gray_initial` 只做受控真实租户 smoke、SLO/告警和回滚演练。
