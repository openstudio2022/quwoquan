# L2 Business Capability：系统架构与工程规范 (`system-architecture-and-engineering-guide`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理。

## 2. 范围与非目标

### In Scope

- service-local contracts 与 context/object/layer 物理路径唯一反向映射
- 从服务本地契约扫描发现全部 context、独立对象根、聚合成员及五类 object kind，不维护冻结数量清单
- 服务源码、metadata 和服务测试目录统一
- 服务自治 config/resources/deploy、四环境差异、secret reference 与 release package 边界
- 服务四环境 Kustomize 入口与 Ops 可执行装配闭环
- 外部 capability、environment binding、adapter/workload 与 conformance evidence 闭环
- coturn、LiveKit、seed-box、legal、platform-ops、rec-model 归位
- 唯一 new-service 脚手架和 verify-service-architecture 门面

### Out of Scope

- 改变公开 wire 字段、HTTP/WS route 或稳定错误码语义
- 兼容旧 path/schema/registry
- 第五环境、prod-gray 环境或第二治理平台
- 以静态门禁代替 gamma/prod 当前证据

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-004 / SCN-002`](../../spec.md#scn-002)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-006 / SCN-006`](../../spec.md#scn-006)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-007 / SCN-012`](../../spec.md#scn-012)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-010 / SCN-023`](../../spec.md#scn-023)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md)：ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- [`domain-service-directory-ownership`](./domain-service-directory-ownership/spec.md)：从每个服务的 `contracts/domain.yaml` 和 L1 工程归属直接定位唯一责任领域。
- [`repository-layout-hygiene-and-retirement`](./repository-layout-hygiene-and-retirement/spec.md)：报告包含固定九类分类、WIP 清单、候选引用证据和最小验证命令。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 metadata 对象单轨与反向映射

- context、独立对象根和 aggregate member 数量全部由服务本地契约扫描派生，不在规格、门禁或注册表重复登记
- 每个独立对象的 kind 必须是 aggregate_root、append_only_fact、projection、external_reference、runtime_session 之一，实际分布由门禁报告计算
- 任意 object root 只有一个 object.yaml.kind，domain/context/object 不在文件中重复声明
- owned_entity/value_object 只作为聚合成员，不存在独立对象根
- business_object_map、对象 readiness、aggregate/entity/service 文件及全局对象 catalog 数量为零
- ContractGraph、OpenAPI 和派生对象索引可由受版本控制的 metadata 重建
- stateful object 的 `lifecycle.state_field` 必须引用同对象 enum field 且 states 与 enum wire value 精确一致；append_only_fact 必须声明 immutable，其他 kind 禁止借用 immutable 逃逸生命周期校验
- enum 仅允许 global/service/object 三级最近 owner 解析，同名 shadow、同 owner 重复、跨对象私有重复、悬空引用和 dead definition 均 fail-closed
- fields 中所有 type/semantic_type 必须能解析且语义兼容；projection 必须显式声明 `read_model` 与非空字段 shape，客户端 `dart_class + output_path` 成对且全图唯一

<a id="req-002"></a>
### REQ-002 服务目录、DDD 依赖与 CQRS 规则

- 任意服务文件符合 services/<service>/internal/<context>/<object>/<layer>/file，domain 唯一来自服务 contracts/domain.yaml
- 任意声明 api_routes 的对象必须有同 context/object 源码 owner，禁止将实现集中到同服务“主对象”目录或用空占位冒充实现
- 每个源码对象有唯一 service owner，不存在跨服务 internal import
- domain 对 HTTP、数据库、MQ、配置框架和 generated transport DTO 的依赖数量为零
- infrastructure 不被 domain/application/adapters 反向依赖
- 对象 adapters/infrastructure 不被兄弟对象导入；跨对象仅经 domain/application port 或事件协作，adapter 组合只发生在 cmd
- command 写 projection/external_reference/append_only_fact update-delete 的违规数量为零
- query 使用 named reader/slice，runtime session 绑定同 packet session owner
- generated 只存在于服务根 generated/<context>/<object>，internal 下生成产物数量为零
- 启用 errors codegen 的服务逐对象一一生成，禁止 domain wildcard 或多对象错误聚合到主对象包
- local_contract/api_integration 文件均位于自身 context/object 测试路径，共享启动支持仅位于 tests/support；`internal/**`、`cmd/**` 和 production package 不得含业务测试文件
- 服务目录下旧 configs、deploy/overlays 和 release snapshot 数量为零
- Go 服务共享唯一 `quwoquan_service/go.mod` 且无嵌套 module/go.work；Python 服务在自身目录拥有 `pyproject.toml`

<a id="req-003"></a>
### REQ-003 配置、四环境与唯一运行拓扑

- 每个服务配置键只在本服务 config/schema.yaml 定义，四环境 config.yaml 只保存 override、secret reference 与 external binding
- 环境集合精确等于 alpha/beta/gamma/prod，不存在 dev 或 prod-gray
- prod gray 仅是 rollout stage
- 每个服务以 environments/<env> 作为该环境唯一入口，四环境只依赖公共 config/resources/deploy 基线，环境之间不继承
- 公共资源与环境 seed/release/artifact 引用职责分离；gamma 只消费环境自治的不可变测试 seed 且不注入 App Mock，prod 不含 fixture 或测试 seed
- 第一方服务部署归服务 deploy/base 与 environments/<env>/deploy；Ops 环境目录只做可执行装配，不维护第一方 workload/topology 注册表
- 14×4 个服务环境入口和4个 Ops 环境装配均可独立构建
- 删除 .qwq_output 后仍可从版本控制真相源重建配置、资源与部署包；`.qwq_output` 只保存可再生运行证据、过程记录和缓存，渲染配置、临时 `.env`、TLS 与 secret 仅能位于受控仓外 `QWQ_DEPLOY_WORK_ROOT`
- `QWQ_DEPLOY_WORK_ROOT` 解析后必须是仓库和 `QWQ_OUTPUT_ROOT` 之外的绝对 target-scoped 目录，符号链接逃逸和对根目录的 destructive cleanup 均 fail-closed

<a id="req-004"></a>
### REQ-004 外部 capability 与特殊资产归位

- 每个真实外部调用形成 operations capability 到环境 Binding、adapter/workload 和 conformance evidence 的闭环；共享 capability 由唯一 owner 的 `externalDependencies` 与 consumer object 的显式 capability-use 派生，禁止外置 consumer/root 清单
- 不存在外部服务总注册表、provider assertion 清单或 registered_only 运行项
- gamma 外部 Provider 只选择 typed Port 对等本地替身且不使用 UI Mock/Provider override；prod 不选择 mock、fixture、本地替身、明文 secret 或无 conformance adapter
- Provider request、attempt、result 与 dead-letter 账本只由 `integration.ExternalInteraction` 及其事实对象维护；消费方只保存 `externalInteractionId` 与幂等 inbox receipt，禁止复制 provider 状态账本
- 声明 identity、事件 payload 或 projection 的 `external_reference` 必须拥有字段契约并使用 typed payload，禁止以未声明字段或原始 `object` 形成第二真相源
- coturn 和 livekit 位于 Ops external workload；seed-box 数量为零，seed 由各领域服务 job 自治执行
- legal 位于 static/legal，platform-ops 位于 control-plane，rec-model 归 recommendation-service
- 上述特殊资产均不被扫描为领域服务或业务对象 owner

<a id="req-005"></a>
### REQ-005 唯一脚手架与治理门面

- new-service 只接受已存在且无 source owner 的 metadata object
- 脚手架生成首个对象纵切、api entry、build Dockerfile、服务配置定义、公共部署基线、四环境入口与对象路径测试
- 脚手架不生成 registry、release snapshot、README、无能力空目录或重复环境默认值
- make verify-service-architecture 是唯一人工服务架构治理入口
- 旧 module/process/workload/onboarding/asset profile 验证入口不再被 Make、stackctl 或 CI 调用
- 源码树 __pycache__、pyc、pyo、pytest cache 与手工生成物数量为零

<a id="req-006"></a>
### REQ-006 三层证据与 readiness 计算

- UAT/DOM/SIT/GWT 仅在所属节点定义，真实测试直接写稳定 `spec_ref`，不登记测试文件路径清单
- runner 可由 `spec_ref` 定位实际测试、结果、环境和 commit/config/image 摘要
- local_contract 覆盖对象规则、kind、mapper/provider/widget 本地行为
- api_integration 覆盖真实 HTTP/WS、字段、错误、鉴权、存储与 adapter 边界
- user_acceptance 覆盖 Journey/Scenario、环境行为和用户可见恢复动作
- readiness 由 runner 结果计算，metadata 不声明 implemented/commercial-ready
- gamma/prod 当前证据缺失时结论保持 structure-governance-complete 或更低

<a id="req-007"></a>
### REQ-007 脚手架、三层测试目录、case ID 和统一架构门禁

- 脚手架、三层测试目录、case ID 和统一架构门禁。
- 缺 gamma/prod 当前证据时，禁止声明商业就绪。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/contracts/metadata/_schemas`、`quwoquan_service/services/*/contracts`、`quwoquan_service/services/*/config/schema.yaml`、`quwoquan_service/services/*/resources`、`quwoquan_service/services/*/deploy/base`、`quwoquan_service/services/*/environments`、`quwoquan_ops/environments/{alpha,beta,gamma,prod}`、`quwoquan_ops/external`、`quwoquan_ops/environments/local_env_port_manifest.yaml`、`quwoquan_ops/environments/prod/access-isolation.yaml`、`quwoquan_service/static/legal`、`quwoquan_service/control-plane/platform-ops`、`quwoquan_ops/gate/verify_service_architecture.py`、`quwoquan_ops/gate/scaffold/new_service.py`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 metadata 对象单轨与反向映射

- GIVEN 执行“metadata 对象单轨与反向映射”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“metadata 对象单轨与反向映射”对应动作。
- THEN context、独立对象根和 aggregate member 数量全部由服务本地契约扫描派生，不存在冻结数量注册
- THEN 每个独立对象的 kind 均属于五类合法治理语义，实际分布由门禁报告计算
- THEN 任意 object root 只有一个 object.yaml.kind，domain/context/object 不在文件中重复声明
- THEN owned_entity/value_object 只作为聚合成员，不存在独立对象根
- THEN business_object_map、对象 readiness、aggregate/entity/service 文件及全局对象 catalog 数量为零
- THEN ContractGraph、OpenAPI 和派生对象索引可由受版本控制的 metadata 重建
- THEN lifecycle、enum owner、field type/semantic_type 与 projection shape/output 的跨文档漂移由 compiler 硬失败，且不存在 warn-only 或按服务豁免

<a id="sit-002"></a>
### SIT-002 服务目录、DDD 依赖与 CQRS 规则

- GIVEN 执行“服务目录、DDD 依赖与 CQRS 规则”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“服务目录、DDD 依赖与 CQRS 规则”对应动作。
- THEN 任意服务文件符合 services/<service>/internal/<context>/<object>/<layer>/file，domain 唯一来自服务 contracts/domain.yaml
- THEN 任意声明 api_routes 的对象均有同 context/object 源码 owner，且不存在借住主对象目录或空占位的实现
- THEN 每个源码对象有唯一 service owner，不存在跨服务 internal import
- THEN domain 对 HTTP、数据库、MQ、配置框架和 generated transport DTO 的依赖数量为零
- THEN infrastructure 不被 domain/application/adapters 反向依赖
- THEN 对象 adapters/infrastructure 不被兄弟对象导入；跨对象仅经 domain/application port 或事件协作，adapter 组合只发生在 cmd
- THEN command 写 projection/external_reference/append_only_fact update-delete 的违规数量为零
- THEN query 使用 named reader/slice，runtime session 绑定同 packet session owner
- THEN generated 只存在于服务根 generated/<context>/<object>，internal 下生成产物数量为零
- THEN 启用 errors codegen 的服务逐对象一一生成，禁止 domain wildcard 或多对象错误聚合到主对象包
- THEN local_contract/api_integration 文件均位于自身 context/object 测试路径，共享启动支持仅位于 tests/support，且 `internal/**`、`cmd/**` 和 production package 不含业务测试文件
- THEN 服务目录下旧 configs、deploy/overlays 和 release snapshot 数量为零
- THEN Go 服务共享唯一 `quwoquan_service/go.mod` 且无嵌套 module/go.work；Python 服务在自身目录拥有 `pyproject.toml`

<a id="sit-003"></a>
### SIT-003 配置、四环境与唯一运行拓扑

- GIVEN 执行“配置、四环境与唯一运行拓扑”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“配置、四环境与唯一运行拓扑”对应动作。
- THEN 每个服务配置键只在本服务 config/schema.yaml 定义，四环境 config.yaml 只保存 override、secret reference 与 external binding
- THEN 环境集合精确等于 alpha/beta/gamma/prod，不存在 dev 或 prod-gray
- THEN prod gray 仅是 rollout stage
- THEN 每个服务以 environments/<env> 作为该环境唯一入口，环境之间不存在引用或继承
- THEN 公共资源与环境 seed/release/artifact 引用职责分离；gamma 只消费环境自治的不可变测试 seed 且不注入 App Mock，prod 不含 fixture 或测试 seed
- THEN 14×4 个服务环境入口和4个 Ops 环境装配均可独立构建
- THEN 删除 .qwq_output 后仍可从版本控制真相源重建配置、资源与部署包，`.qwq_output` 只保存可再生运行证据、过程记录和缓存，渲染配置、临时 `.env`、TLS 与 secret 位于受控仓外 `QWQ_DEPLOY_WORK_ROOT`
- THEN `QWQ_DEPLOY_WORK_ROOT` 解析后为仓库和 `QWQ_OUTPUT_ROOT` 外的绝对 target-scoped 目录，符号链接逃逸和对根目录的 destructive cleanup 均 fail-closed

<a id="sit-004"></a>
### SIT-004 外部 capability 与特殊资产归位

- GIVEN 执行“外部 capability 与特殊资产归位”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“外部 capability 与特殊资产归位”对应动作。
- THEN 每个真实外部调用形成 operations capability 到环境 Binding、adapter/workload 和 conformance evidence 的闭环，且共享 capability 仅由唯一 owner 的 `externalDependencies` 与 consumer object 的显式 capability-use 派生
- THEN 不存在外部服务总注册表、provider assertion 清单或 registered_only 运行项
- THEN gamma 外部 Provider 只选择 typed Port 对等本地替身且不使用 UI Mock/Provider override；prod 不选择 mock、fixture、本地替身、明文 secret 或无 conformance adapter
- THEN Provider request、attempt、result 与 dead-letter 账本只存在于 `integration.ExternalInteraction` 及其事实对象，消费方只保存 `externalInteractionId` 与幂等 inbox receipt
- THEN 每个声明 identity、事件 payload 或 projection 的 `external_reference` 都有对应字段契约并使用 typed payload，不存在未声明字段或原始 `object`
- THEN coturn 和 livekit 位于 Ops external workload，seed-box 不存在且 seed 由服务 job 自治执行
- THEN legal 位于 static/legal，platform-ops 位于 control-plane，rec-model 归 recommendation-service
- THEN 上述特殊资产均不被扫描为领域服务或业务对象 owner

<a id="sit-005"></a>
### SIT-005 唯一脚手架与治理门面

- GIVEN 执行“唯一脚手架与治理门面”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“唯一脚手架与治理门面”对应动作。
- THEN new-service 只接受已存在且无 source owner 的 metadata object
- THEN 脚手架生成首个对象纵切、api entry、build Dockerfile、配置定义、部署基线、四环境入口与对象路径测试
- THEN 脚手架不生成 registry、release snapshot、README、无能力空目录或重复环境默认值
- THEN make verify-service-architecture 是唯一人工服务架构治理入口
- THEN 旧 module/process/workload/onboarding/asset profile 验证入口不再被 Make、stackctl 或 CI 调用
- THEN 源码树 __pycache__、pyc、pyo、pytest cache 与手工生成物数量为零

<a id="sit-006"></a>
### SIT-006 三层证据与 readiness 计算

- GIVEN 执行“三层证据与 readiness 计算”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“三层证据与 readiness 计算”对应动作。
- THEN UAT/DOM/SIT/GWT 仅在所属节点定义，真实测试直接写稳定 `spec_ref`，不登记测试文件路径清单
- THEN runner 可由 `spec_ref` 定位实际测试、结果、环境和 commit/config/image 摘要
- THEN local_contract 覆盖对象规则、kind、mapper/provider/widget 本地行为
- THEN api_integration 覆盖真实 HTTP/WS、字段、错误、鉴权、存储与 adapter 边界
- THEN user_acceptance 覆盖 Journey/Scenario、环境行为和用户可见恢复动作
- THEN readiness 由 runner 结果计算，metadata 不声明 implemented/commercial-ready
- THEN gamma/prod 当前证据缺失时结论保持 structure-governance-complete 或更低

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 metadata 对象单轨与反向映射

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：对象身份、kind 与聚合成员从服务本地契约唯一发现且可反向映射
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 服务目录、DDD 依赖与 CQRS 规则

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：任意服务文件符合 services/<service>/internal/<context>/<object>/<layer>/file，domain 唯一来自服务 contracts/domain.yaml
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 配置、四环境与唯一运行拓扑

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：每个服务的配置键只在本服务 config/schema.yaml 定义，四环境文件只保存 override、secret reference 与 external binding
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 外部 capability 与特殊资产归位

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：每个真实外部调用形成 operations capability 到 environment binding、adapter/workload 和 conformance evidence 的闭环
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 唯一脚手架与治理门面

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：new-service 只接受已存在且无 source owner 的 metadata object
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 三层证据与 readiness 计算

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：acceptance 仅登记稳定 case ID，不登记测试文件路径
- 完成判定：`SIT-006` 对应行为满足且真实测试 `spec_ref` 有效
