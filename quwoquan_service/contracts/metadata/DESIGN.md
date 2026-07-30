# 领域元数据与 ContractGraph 设计

## 1. 设计边界

元数据描述业务语义，不承担资产登记。物理路径是对象身份来源；compiler 扫描目录构建 ContractGraph，生成 transport、DTO、错误码、投影类型和覆盖报告。

```text
metadata YAML ──strict load──> typed AST ──validate──> ContractGraph
                                                       ├── OpenAPI
                                                       ├── Go/Dart/Python contracts
                                                       ├── operation/reader/slice descriptors
                                                       └── coverage/readiness evidence
```

任何 generator 都不得重新解释原始 YAML，也不得从旧 OpenAPI 反向恢复语义。

## 2. 对象身份

对象根路径固定为所属服务内：

```text
services/<service>/contracts/<bounded-context>/<business-object>/
```

由此得到：

```text
metadata_domain = services/<service>/contracts/domain.yaml
bounded_context = <domain>.<bounded-context>
business_object = <domain>.<business-object>
object_kind = object.yaml.kind
```

同一 `<domain>.<business-object>` 不得位于多个 context。需要消歧时重命名业务对象，不增加 alias、重复 ID 或注册表。

源码采用相同组织轴：

```text
services/<service>/internal/<context>/<object>/<layer>/...
```

service 只表达源码和部署所有权，不进入对象业务标识。

## 3. 对象类型

独立对象只允许五种 kind：

| kind | compiler 必须验证的语义 |
|---|---|
| `aggregate_root` | command owner、事务边界、并发策略、必要 outbox |
| `append_only_fact` | append sink、幂等/去重、禁止 update/delete |
| `projection` | named Reader/Slice、禁止业务 command |
| `external_reference` | 本地非权威、禁止本地生命周期写入 |
| `runtime_session` | session owner、租约/fencing/TTL/终止语义 |

`owned_entity`、`value_object` 是聚合成员语义，只能写在聚合根 `object.yaml.members`。它们不拥有独立目录、Store、Repository 或公开 Facade。

## 4. 文件分工

`context.yaml` 只描述 bounded context；`object.yaml` 只描述对象种类、生命周期、规则和关系；`fields.yaml` 只描述字段；`operations.yaml` 只描述用例、transport 与端口；`storage.yaml`、`events.yaml`、`errors.yaml` 分别描述存储、事件和错误语义。

文件内不得重复路径身份、service、源码/测试路径、DDD layer 或 readiness。可从目录、入口、Kustomize 或测试运行推导的事实不进入 metadata。

## 5. DDD 与 CQRS

依赖方向固定：

```text
adapters/inbound -> application -> domain
infrastructure --implements--> application/domain ports
generated --------------------> contract types only
```

- domain 不依赖 HTTP、数据库、消息中间件、配置框架或 transport DTO。
- application 组织用例与事务边界，核心业务规则留在 domain。
- command 只能修改 `aggregate_root` 或 `runtime_session`；事实对象只允许 append。
- query 从 projection/read model 读取，不通过聚合仓储拼装复杂列表。
- infrastructure 只实现端口，不向 domain 暴露 SDK 类型。
- 禁止跨服务导入对方 `internal/**`。

## 6. Operation 编译

`operations.yaml` 中每个 operation 必须绑定：

- 稳定 operation ID 与 public/internal transport（如存在）；
- `application.kind`；
- command 的 `aggregate_owner`、`session_owner` 或 `append_sink`；
- query 的 named `reader` 与 typed `slice`；
- actor/auth、错误、可靠性及可观测策略；
- 实际需要的外部 capability/port（如存在）。

compiler 先解析所有对象，再解析关系和 operation；未解析引用、跨对象写 owner、projection command、事实 update/delete 或 owned child 直达均失败。

## 7. OpenAPI 与语言产物

域级 `openapi.yaml` 是生成快照，`operations.yaml api_routes` 是 transport 真相。生成器原子重建全部快照；missing、stale、orphan 任一状态都由门禁阻断。

OpenAPI、Go、Dart 和 Python 消费同一个 Graph hash。生成文件必须标记 `DO NOT EDIT`；手写代码只依赖生成契约，不复制 route、错误码、字段或枚举。

## 8. 配置与外部能力

- 每个服务的 `config/schema.yaml` 唯一定义配置键、默认值、约束、敏感性和 rollout 语义。
- `services/<service>/environments/{alpha,beta,gamma,prod}/config.yaml` 只保存 override、secret reference 和 external binding；环境之间禁止继承。
- package 阶段将 schema 默认值与单一环境差异渲染为 `<QWQ_DEPLOY_WORK_ROOT>/<env>/packages/services/<service>/config/config.yaml`，`CONFIG_VERSION` 由内容摘要派生。
- 公共资源和部署基线分别位于服务 `resources/`、`deploy/base/`；环境资源引用和部署差异位于同一 `environments/<env>` 入口。
- 对象声明外部 capability/port，服务环境入口选择真实 binding，Ops 只装配 external workload。conformance 结果按 evidence schema 保存，不维护 provider 或 assertion 注册表。

## 9. 测试与 readiness

测试物理路径与对象路径同构：

```text
services/<service>/tests/local_contract/<context>/<object>/...
services/<service>/tests/api_integration/<context>/<object>/...
tests/user_acceptance/<journey-or-story>/...
```

UAT/DOM/SIT/GWT 只在所属 feature-tree 节点定义。真实测试以 `spec_ref` 直接绑定验收锚点；runner 将锚点、实际测试、环境、制品摘要和结果关联。测试数、通过率和 readiness 全部由证据计算，禁止 tracked coverage map、手写状态或 exact-path 清单。

`qwq-contract coverage` 的结构阶段与累计 readiness 是两种不同口径：阶段分布互斥，`modeled`、`contractReady`、`implemented`、`commercialReady` 则按前置关系累计。静态 compiler 不得把源码或测试文件“存在”解释成测试通过；runner 尚未附加对象级结果证据时，`readinessEvidencePackets=0`，`implemented/commercialReady=0` 只表示运行证据未接入，不表示仓库中没有实现。runner 证据必须绑定当前对象、完整 operation ID 集与内容摘要；任何 operation 仍为 `commercial.status: blocked` 时，四环境或 UAT 证据不得把对象提升为 commercial-ready。

## 10. 治理门面

`make verify-service-architecture` 是统一门面，内部组合 metadata、路径反向映射、DDD/CQRS、配置四环境、拓扑、外部能力和测试目录门禁。专项脚本是门面的内部实现，不形成第二套人工流程。

任何报告中的对象数量、kind 分布、operation 数量和 readiness 都必须由当前 Graph 或 runner 生成，不在文档手工维护。
