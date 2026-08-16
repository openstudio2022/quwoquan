# L2 Business Capability：系统架构与工程规范 (`system-architecture-and-engineering-guide`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理。

## 2. 范围与非目标

### In Scope

- service-local contracts 与 context/object/layer 物理路径唯一反向映射
- 从服务本地契约扫描发现全部 context、独立对象根、聚合成员及六类 object kind，不维护冻结数量清单
- 服务与 App 源码、metadata 和三层测试按同一 service/context/object 身份反向映射；L1 domain 只由 service `domain.yaml` 与特性树工程 owner 派生，不进入第二份路径 registry
- App 业务纵切、页面 source owner/participants、层间依赖和唯一 composition root
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
- [`absent-empty-failure-nullability`](./absent-empty-failure-nullability/spec.md)：缺席、空值与失败在端云保持三种不可互换的结果状态。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 metadata 对象单轨与反向映射

- context、独立对象根和 aggregate member 数量全部由服务本地契约扫描派生，不在规格、门禁或注册表重复登记
- 每个独立对象的 kind 必须取自 [AppRoot REQ-010](../../spec.md#req-010) 声明的六类闭集，六类均已入仓且各自有真实对象；实际分布由门禁报告计算，规格不登记快照数量
- `process_manager` 的写入口是专用 `process_facade`，`identity.version_source` 恒为 `checkpoint`，并必须声明状态机的 `state_field` 与 `states`；它的云侧必需层是 domain、application 与 infrastructure 三层，缺任一层即阻断
- 任意 object root 只有一个 object.yaml.kind，domain/context/object 不在文件中重复声明
- owned_entity/value_object 只作为 aggregate_root 的聚合成员，不存在独立对象根；owned_entity 必须声明聚合内 identity、有界 cardinality 且只能经 aggregate facade 写入，不得拥有独立 Facade/Store/operation
- value_object 无独立 identity 与写入口，保持不可变和结构相等；聚合可保留有界 append-only revision 值序列，但不得把该序列提升为第二对象根或独立存储 owner
- business_object_map、对象 readiness、aggregate/entity/service 文件及全局对象 catalog 数量为零
- ContractGraph、OpenAPI 和派生对象索引可由受版本控制的 metadata 重建
- stateful object 的 `lifecycle.state_field` 必须引用同对象 enum field 且 states 与 enum wire value 精确一致；append_only_fact 必须声明 immutable，其他 kind 禁止借用 immutable 逃逸生命周期校验
- append_only_fact 的每个公开 command 必须由对象自己的 `lifecycle.append_command_admission` 正向声明后才准入，声明必须逐条列出 command 并给出评估理由，且要求 `instance_invariant: none`
- 该判据只接受对象契约内的正向声明，不接受集中 allowlist；对象非不可变、存在实例级可变不变式或 command 未登记时一律阻断，该 command 属于聚合根写入口，应改挂对应 aggregate_root
- enum 仅允许 global/service/object 三级最近 owner 解析，同名 shadow、同 owner 重复、跨对象私有重复、悬空引用和 dead definition 均 fail-closed
- fields 中所有 type/semantic_type 必须能解析且语义兼容；projection 必须显式声明 `read_model` 与非空字段 shape，客户端 `dart_class + output_path` 成对且全图唯一

<a id="req-002"></a>
### REQ-002 服务目录、DDD 依赖与 CQRS 规则

- 任意服务文件符合 services/<service>/internal/<context>/<object>/<layer>/file，domain 唯一来自服务 contracts/domain.yaml
- 任意 App 业务文件符合 `quwoquan_app/lib/service/<service>/<context>/<object>/<layer>/file`，其中 layer 只允许 domain、application、adapters、presentation；`<service>` 是拥有该 context 的云侧服务名的 snake_case 形式，context/object 必须来自 canonical ContractGraph 与所属 L1 工程归属，禁止由文件名启发式、人工 registry 或旧目录别名决定 owner。
- App 的 `runtime`、`design_system` 与 `l10n` 是唯一横切根；业务对象不得落入旧 `ui/cloud/core/app/application/infrastructure` 大桶，横切根也不得成为无 owner 业务文件的 fallback。
- App 层义务按 canonical 端侧能力事实派生：App-exposed operation 要求 application/adapters，页面认领要求 application/presentation，端侧不变式或状态机才要求 domain；未被 App 消费的纯云对象不要求 App 空目录或占位实现。
- App 必需层由端侧能力事实决定，端侧禁止层与写面形态则由云侧 kind 唯一决定，两者是互补的两组义务，不得互相顶替。
- 由 kind 派生的端侧禁止层是：`append_only_fact` 与 `runtime_session` 不得拥有 presentation，`external_reference` 不得拥有 domain 与 presentation。`projection` 与 `process_manager` 不进禁止层表，二者合法拥有页面，是否 PageOwned 只由页面对象契约的 source owner 决定。
- 由 kind 派生的端侧写面形态是：`projection` 与 `external_reference` 端侧没有写面也不得有本地可变 patch 路径，`external_reference` 不得绑定本地权威持久化；`append_only_fact` 与 `process_manager` 的端侧写面必须与聚合写面在类型上可区分，不得共用聚合的 command writer 命名族。
- 每个页面必须声明唯一 source owner，并保留全部 participant object；页面物理文件位于 source owner 的 presentation，其他 participant 只经公开 application port/facade 参与，移动文件不得删除语义参与关系。
- 任意声明 api_routes 的对象必须有同 context/object 源码 owner，禁止将实现集中到同服务“主对象”目录或用空占位冒充实现
- 每个源码对象有唯一 service owner，不存在跨服务 internal import
- domain 对 HTTP、数据库、MQ、配置框架和 generated transport DTO 的依赖数量为零
- infrastructure 不被 domain/application/adapters 反向依赖
- 对象 adapters/infrastructure 不被兄弟对象导入；跨对象仅经 domain/application port 或事件协作，adapter 组合只发生在 cmd
- App 依赖方向只允许 presentation 使用 application/domain、application 使用自身 domain、adapters 实现 application port 并使用 domain；具体 adapter 只在 `runtime/di` 组合，presentation 不得导入具体 adapter，domain 不得依赖 Flutter、IO、generated transport 或其他层。
- App 跨对象协作只经显式公开 port/facade/event；兄弟对象私有层、barrel re-export、旧路径 shim、双轨 import 和兼容 fallback 数量均为零。
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
- 公共资源、Data release 与 artifact 引用职责分离。同源表示相同 canonical publish、immutable release、importer、公开契约和 readback，不表示复制 Prod 数据库。Creator 是 release 内容身份而非登录 Actor。Alpha/Beta/Gamma 的 Actor 与候选绑定交易数据只经真实非生产主体和领域公开 command/event 创建，Prod 只接受真实用户或正式运营行为且不含 fixture、测试 seed 或非生产 runner
- 第一方服务部署归服务 deploy/base 与 environments/<env>/deploy；Ops 环境目录只做可执行装配，不维护第一方 workload/topology 注册表
- 14×4 个服务环境入口和4个 Ops 环境装配均可独立构建
- 删除 .qwq_output 后仍可从版本控制真相源重建配置、资源与部署包；`.qwq_output` 只保存可再生运行证据、过程记录和缓存，渲染配置、临时 `.env`、TLS 与 secret 仅能位于受控仓外 `QWQ_DEPLOY_WORK_ROOT`
- `QWQ_DEPLOY_WORK_ROOT` 解析后必须是仓库和 `QWQ_OUTPUT_ROOT` 之外的绝对 target-scoped 目录，符号链接逃逸和对根目录的 destructive cleanup 均 fail-closed

<a id="req-004"></a>
### REQ-004 外部 capability 与特殊资产归位

- 每个真实外部调用形成 operations capability 到环境 Binding、adapter/workload 和 conformance evidence 的闭环；共享 capability 由唯一 owner 的 `externalDependencies` 与 consumer object 的显式 capability-use 派生，禁止外置 consumer/root 清单
- 不存在外部服务总注册表、provider assertion 清单或 registered_only 运行项
- alpha/beta/gamma required 验收只选择受管非生产租户的非内存 Provider 且不使用 UI Mock/Provider override；prod 不选择 mock、fixture、本地替身、明文 secret 或无 conformance adapter
- Provider request、attempt、result 与 dead-letter 账本只由 `integration.ExternalInteraction` 及其事实对象维护；消费方只保存 `externalInteractionId` 与幂等 inbox receipt，禁止复制 provider 状态账本
- 声明 identity、事件 payload 或 projection 的 `external_reference` 必须拥有字段契约并使用 typed payload，禁止以未声明字段或原始 `object` 形成第二真相源
- coturn 和 livekit 位于 Ops external workload；seed-box 和领域业务 seed job 数量均为零，非生产验收写入只由 `stackctl verify` 编排领域公开 command/event
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
- App 三层测试与生产对象同构为 `test/<layer>/service/<service>/<context>/<object>`；服务 local_contract/api_integration 与生产对象同构为 `tests/<layer>/<context>/<object>`，`support` 只承载 harness、fixture factory 和 typed double 定义，不承载测试用例或生产成功事实。
- runner 可由 `spec_ref` 定位实际测试、结果、环境和 commit/config/image 摘要；测试入口的路径与摘要属于结构证据，实际 CaseResult、环境和用户验收回执属于结果证据，两类必须分字段且不得互相替代。
- local_contract 覆盖对象规则、kind、mapper/provider/widget 本地行为
- api_integration 覆盖真实 HTTP/WS、字段、错误、鉴权、存储与 adapter 边界
- user_acceptance 覆盖 Journey/Scenario、环境行为和用户可见恢复动作
- readiness 由静态结构证据与 runner 结果证据分阶段计算，metadata source 不手写 implemented/commercial-ready；文件存在最多证明结构入口，不产生通过结果
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
- THEN 每个独立对象的 kind 均属于六类合法治理语义，实际分布由门禁报告计算
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
- THEN 任意 App 业务文件都能按 service/context/object/layer 精确反向定位到 canonical 对象和唯一 L1 owner，旧业务大桶、人工 owner registry、无 owner 文件与占位层均不存在
- THEN App 必需层由 operation、页面认领与端侧不变式等 canonical 能力事实派生，纯云对象不会为目录完整性生成空 App 实现，append-only fact 不直接拥有 presentation
- THEN 每个页面有唯一 source owner 且保留全部 participant object，多对象页面只经 participant 的公开 application 边界组合
- THEN 任意声明 api_routes 的对象均有同 context/object 源码 owner，且不存在借住主对象目录或空占位的实现
- THEN 每个源码对象有唯一 service owner，不存在跨服务 internal import
- THEN domain 对 HTTP、数据库、MQ、配置框架和 generated transport DTO 的依赖数量为零
- THEN infrastructure 不被 domain/application/adapters 反向依赖
- THEN 对象 adapters/infrastructure 不被兄弟对象导入；跨对象仅经 domain/application port 或事件协作，adapter 组合只发生在 cmd
- THEN App 的 domain/application/adapters/presentation 依赖方向、跨对象公开边界和唯一 `runtime/di` composition root 均成立，旧路径 shim、barrel re-export 与双轨 import 均不存在
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
- THEN 公共资源、Data release 与 artifact 引用职责分离。同源不复制 Prod 数据库，Creator 不充当登录 Actor。Alpha/Beta/Gamma 验收 Actor 与交易数据只经真实非生产主体和领域公开 command/event 创建，Prod 不含 fixture、测试 seed 或非生产 runner
- THEN 14×4 个服务环境入口和4个 Ops 环境装配均可独立构建
- THEN 删除 .qwq_output 后仍可从版本控制真相源重建配置、资源与部署包，`.qwq_output` 只保存可再生运行证据、过程记录和缓存，渲染配置、临时 `.env`、TLS 与 secret 位于受控仓外 `QWQ_DEPLOY_WORK_ROOT`
- THEN `QWQ_DEPLOY_WORK_ROOT` 解析后为仓库和 `QWQ_OUTPUT_ROOT` 外的绝对 target-scoped 目录，符号链接逃逸和对根目录的 destructive cleanup 均 fail-closed

<a id="sit-004"></a>
### SIT-004 外部 capability 与特殊资产归位

- GIVEN 执行“外部 capability 与特殊资产归位”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“外部 capability 与特殊资产归位”对应动作。
- THEN 每个真实外部调用形成 operations capability 到环境 Binding、adapter/workload 和 conformance evidence 的闭环，且共享 capability 仅由唯一 owner 的 `externalDependencies` 与 consumer object 的显式 capability-use 派生
- THEN 不存在外部服务总注册表、provider assertion 清单或 registered_only 运行项
- THEN alpha/beta/gamma required 验收只选择受管非生产租户的非内存 Provider 且不使用 UI Mock/Provider override；prod 不选择 mock、fixture、本地替身、明文 secret 或无 conformance adapter
- THEN Provider request、attempt、result 与 dead-letter 账本只存在于 `integration.ExternalInteraction` 及其事实对象，消费方只保存 `externalInteractionId` 与幂等 inbox receipt
- THEN 每个声明 identity、事件 payload 或 projection 的 `external_reference` 都有对应字段契约并使用 typed payload，不存在未声明字段或原始 `object`
- THEN coturn 和 livekit 位于 Ops external workload，seed-box 与领域业务 seed job 均不存在，非生产验收写入由 `stackctl verify` 单轨编排
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
- THEN App 与服务测试均按生产对象身份同构落位，support 只提供共享 harness 或 typed double 且不承载测试用例
- THEN runner 可由 `spec_ref` 定位实际测试、结果、环境和 commit/config/image 摘要，结构证据与执行结果使用不同字段且文件存在不会被解释为通过
- THEN local_contract 覆盖对象规则、kind、mapper/provider/widget 本地行为
- THEN api_integration 覆盖真实 HTTP/WS、字段、错误、鉴权、存储与 adapter 边界
- THEN user_acceptance 覆盖 Journey/Scenario、环境行为和用户可见恢复动作
- THEN readiness 由静态结构证据与 runner 结果证据分阶段计算，metadata source 不手写 implemented/commercial-ready，且文件存在不会产生通过结果
- THEN gamma/prod 当前证据缺失时结论保持 structure-governance-complete 或更低

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 metadata 对象单轨与反向映射

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前证据只覆盖 `SIT-001` 7 条结果子句中的一部分。现有证据为 Ops 服务架构治理测试、metadata lifecycle owner 契约测试与 search 事件源绑定契约测试，集中在对象根扫描派生、kind 合法性与 lifecycle/enum owner 漂移硬失败；`business_object_map` 与全局对象 catalog 清零、`owned_entity`/`value_object` 不独立成根、ContractGraph 与 OpenAPI 可从受版本控制 metadata 重建，以及 field type/semantic_type 与 projection shape 的跨文档漂移无 warn-only 逃逸，均无独立断言证据。
- 完成判定：`SIT-001` 的 7 条 THEN 组全部具备子句级 `spec_ref`（`sit-001.t1..t7`）绑定的真实测试或可执行门证据。

<a id="open-002"></a>
### OPEN-002 服务目录、DDD 依赖与 CQRS 规则

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前服务对象目录已形成稳定基线，但 App 仍处于旧业务大桶与对象纵切并存状态，尚不能证明全部业务文件精确归属、能力驱动层义务、页面 source owner/participants、依赖 DAG 与零 shim 同时成立。
- 完成判定：`SIT-002` 的 21 条 THEN 组全部具备子句级 `spec_ref`（`sit-002.t1..t21`）绑定的真实测试或可执行门证据。

<a id="open-003"></a>
### OPEN-003 配置、四环境与唯一运行拓扑

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前证据只覆盖 `SIT-003` 8 条结果子句中的一部分。现有证据为 Ops 服务架构治理测试、非生产业务数据供给门与环境 fixture 切除测试，集中在环境集合与非生产数据来源；配置键单一定义、14×4 服务环境入口与 4 个 Ops 装配可独立构建、删除 `.qwq_output` 后可从版本控制真相源完整重建，以及 `QWQ_DEPLOY_WORK_ROOT` 的符号链接逃逸与 destructive cleanup fail-closed，均无独立断言证据。已实测到反例：推荐服务 local_contract 测试会在服务根写出 `.qwq_output`，说明运行输出收口尚未真正成立。
- 完成判定：`SIT-003` 的 8 条 THEN 组全部具备子句级 `spec_ref`（`sit-003.t1..t8`）绑定的真实测试或可执行门证据。

<a id="open-004"></a>
### OPEN-004 外部 capability 与特殊资产归位

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前证据只覆盖 `SIT-004` 8 条结果子句中的一部分。现有证据为 Ops 服务架构治理测试与 integration-service 的事件源绑定、事件归属契约测试，集中在 `ExternalInteraction` 账本归属；capability 到环境 Binding 与 conformance evidence 的闭环、alpha/beta/gamma 只选受管非生产租户 Provider、prod 不含 mock 与明文 secret、`external_reference` 全部 typed payload，以及 coturn/livekit/legal/rec-model 等特殊资产不被扫描为业务对象 owner，均无独立断言证据。
- 完成判定：`SIT-004` 的 8 条 THEN 组全部具备子句级 `spec_ref`（`sit-004.t1..t8`）绑定的真实测试或可执行门证据。

<a id="open-005"></a>
### OPEN-005 唯一脚手架与治理门面

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前证据只覆盖 `SIT-005` 6 条结果子句中的一条。唯一证据是 Ops 服务架构治理测试，只覆盖 `make verify-service-architecture` 作为唯一人工入口；new-service 只接受无 source owner 的既有 metadata object、脚手架生成物的正向与负向清单、旧验证入口不再被 Make/stackctl/CI 调用，以及源码树缓存与手工生成物清零，均无独立断言证据。
- 完成判定：`SIT-005` 的 6 条 THEN 组全部具备子句级 `spec_ref`（`sit-005.t1..t6`）绑定的真实测试或可执行门证据。

<a id="open-006"></a>
### OPEN-006 三层证据与 readiness 计算

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前三层入口和静态 evidence 尚不能分别证明 App 与服务的对象级测试完整性，也没有把结构入口与 runner CaseResult、四环境和用户验收回执完整分字段承载；缺结果证据时不得把对象升为 commercial-ready。
- 完成判定：`SIT-006` 的 9 条 THEN 组全部具备子句级 `spec_ref`（`sit-006.t1..t9`）绑定的真实测试或可执行门证据，且结构入口与 runner CaseResult、四环境和用户验收回执分字段承载，缺结果证据的对象不得升为 commercial-ready。

