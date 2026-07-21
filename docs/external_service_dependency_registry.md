# 外部能力依赖治理说明

## 目的与归属

本说明定义第三方 SaaS、公开数据源、自托管基础设施和客户端原生能力的统一治理方式。
唯一条目真相源是 `docs/external_service_registry.yaml`；本文件不复制供应商清单、端点、
凭据或环境矩阵，以避免出现第二套登记表。

- L1：`runtime`
- L2：`runtime-external-integration`
- L3：`provider-adapter-conformance-suite`、
  `capability-provider-commercial-readiness-gate`

## 单轨模型

```text
业务调用方
  -> Capability（稳定 ID + typed Port + owner）
  -> Provider Adapter（稳定 ID + vendor 实现边界）
  -> Environment Binding（选中 Adapter + endpoint/Secret 引用）
  -> Conformance evidence（Alpha/Beta/Gamma × 三层测试）
  -> adapter_ready / capability_ready
```

| 输入 | 唯一职责 | 禁止内容 |
|---|---|---|
| `docs/external_service_registry.yaml` | Capability、Adapter、SDK、实现状态、治理引用 | 端点实际值、Secret 实际值、运行时状态 |
| `quwoquan_ops/environments/external_provider_bindings.yaml` | 环境选择、状态、端点引用、Secret 键引用 | 端点实际值、Secret 实际值、动态 fallback |
| `quwoquan_ops/environments/provider_conformance_manifest.yaml` | profile 到三层原生 harness 的映射；未注册真实 Remote journey 时声明受控 fail-closed prerequisite | 以空实现、memory/fixture 或 UI mock 代替 UAT |
| `provider_conformance_evidence.schema.json` | 证据结构与 artifact 位置 | 配置、凭据、TLS/PII |

BindingCompiler 位于
`quwoquan_ops/cli/lib/external_provider_governance.py`，通过
`python3 quwoquan_ops/gate/verify_external_provider_governance.py` 在构建和门禁阶段执行。
release-required Capability 必须在 registry 的 `binding_scope + binding_roots` 中声明全部
实际组合根、descriptor 输出路径、entrypoint 与 resolver symbol；编译器按 descriptor
owner 投影同一 Binding，并为每个 root 生成 checked-in receipt。门禁同时校验 descriptor
没有漂移、Adapter consumer 集合与 root 集合一致且静态 preflight 消费存在。
`runtime.message.transport` 是 Redis Streams/PubSub 的共享多消费者能力：Pub/Sub 仅用于
瞬时提示，跨服务事实必须使用 Stream、ACK、reclaim 和 DLQ。NATS 与 DNS 明确为
`production_consumption: none`，不产生 required Binding 或 readiness。
服务运行时不得扫描 registry、反射实例化 Adapter 或按字符串动态选厂。

## 访问策略

每个 Capability 和其 Adapter 必须有且只有一种策略：

| 策略 | 使用场景 | 边界 |
|---|---|---|
| `central_integration` | 跨域短信、推送、位置、回调 | 调用方只经 integration-service 的 typed 契约 |
| `domain_owned_adapter` | 领域专属模型、媒体、RTC、存储、观测 | Adapter 只在该领域 composition root 装配 |
| `runtime_shared_adapter` | Redis 等多个服务共同消费的基础设施能力 | 每个 binding root 使用同一环境 Binding 并在启动 preflight，禁止 root 自选 Adapter |
| `client_platform_adapter` | 定位、来电、原生登录、RTC 客户端 | App 业务只读取 `PlatformCapabilities` / NativeBridge |
| `data_pipeline_adapter` | 公开源、素材源、Agent SDK | 只由 `qwq-data` CLI-first pipeline 使用 |

自托管不构成豁免。它仍需声明 Capability、Port、Adapter、环境 Binding、可观测和
Conformance，只是不必通过 `integration-service`。

## 必填合同

### Capability

每项能力必须定义：

- `capability_id`、owner、唯一 `canonical_port` 与 access policy；
- required 环境；
- SLO、隐私、成本、降级、回滚文档引用；
- 验收引用。

### Adapter

每个 Adapter 必须定义：

- `adapter_id`、所属 Capability、vendor、实现路径、SDK 依赖；
- `implementation_status`、允许环境、`production_grade`；
- profile、合规状态、已知缺口与治理引用；
- 仅以 `environment_binding:*`、`platform_default` 或 `not_configured` 表达端点；
- 仅以 `runtime_secret:NAME` 表达凭据。

`mock` 与 `test_fixture_only` 只能用于 alpha/local 的隔离契约；Beta、Gamma、Prod 的
`enabled` Binding 只允许真实的 fail-closed Adapter，Prod 还要求
`production_grade: true`。

## 准出和阻断

结构合法不等于商用 ready。编译器分别输出：

- `adapter_ready`：当前环境选中的具体 Adapter 已具备真实实现和必要级别；
- `capability_ready`：该能力的必需 Binding 及其 Adapter 均 ready。

`blocked` 是诚实的不可用状态：未注入受控凭据、未完成真实连接或未取得设备/运营证据时，
它必须阻止 required Capability 的环境准出。禁止用其他 Adapter 的报告、Mock、历史
artifact、空集合或固定成功提升状态。

当前 registry 的 required Binding 均保留为 `blocked`，直至实际密钥、远端租户、设备或
观测证据完成；Evidence readiness 命令会对此 fail-closed：

```bash
python3 quwoquan_ops/cli/lib/provider_conformance.py --require-ready gamma
```

此命令用于环境/发布准出，不放入仓库静态 `make gate`，避免把“未获得外部凭据”伪装成
代码结构错误；发布前必须在对应环境显式执行。

## 测试与证据

公共 Conformance 至少覆盖 success、validation、authentication、DNS/network、timeout、
throttle、retry、idempotency、callback ordering、redaction 和 observability；能力 profile
补充消息、推送、模型、RTC、对象存储、日志或公开源协议语义。

- `local_contract`：真实 Adapter 类的离线协议/故障 harness，永不访问外网；
- `api_integration`：真实 TLS、鉴权、远端读写、回调或 readback；
- `user_acceptance`：真实页面、设备或运营流程。

每份 evidence 都必须声明 Adapter/Capability、环境、测试层、执行 profile、当前时间和
`.qwq_output/env/<env>/runs/**` 的可删除 artifact 引用。`NOT_RUN`、required skip、
零断言、dry-run、旧 digest、跨环境复用或缺清理/观测引用一律不得提升 readiness。

## 输出与凭据边界

`.qwq_output` 只允许可删除的运行记录、发布产物、观测证据和缓存。以下内容不得进入：

- 环境 Binding、schema、policy、prompt、template、可复用配置；
- `.env`、Caddyfile、Caddy data/config、TLS、证书、私钥、凭据或未脱敏 token；
- 运行期渲染部署文件。

渲染部署配置、TLS 和临时部署卷只能写入仓外 `QWQ_DEPLOY_WORK_ROOT`；可版本控制的配置
真相源保留在 `quwoquan_ops/environments/**` 或领域 `deploy/**`。门禁：

```bash
python3 quwoquan_ops/gate/verify_output_layout.py
python3 quwoquan_ops/gate/verify_output_path_source_contract.py
```

## 新增或迁移流程

1. 先确认业务对象、typed Port 和 access policy；必要字段、错误码和操作先进入 metadata。
2. 在 registry 新增 Capability/Adapter，并声明未实现状态，不得以虚构 ready 占位。
3. 新增 Binding 的引用，不写入 endpoint/Secret 实际值。
4. 实现 Adapter、fail-closed composition、结构化错误、指标和回滚。
5. 完成三层 Conformance 和环境 evidence，最后才提升 release readiness。
