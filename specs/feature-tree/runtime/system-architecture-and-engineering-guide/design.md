# L2 Design：系统架构与工程规范 (`system-architecture-and-engineering-guide`)

> 对应规格：[L2 spec](./spec.md)
>
> 设计触发原因：“领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理”需要 `app-cloud-business-object-commercial-closure`、`domain-service-directory-ownership`、`repository-layout-hygiene-and-retirement` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md)：ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- [`domain-service-directory-ownership`](./domain-service-directory-ownership/spec.md)：服务根和共享 metadata 的 L1 owner 均由当前目录与 spec 直接反推。
- [`repository-layout-hygiene-and-retirement`](./repository-layout-hygiene-and-retirement/spec.md)：报告包含固定九类分类、WIP 清单、候选引用证据和最小验证命令。

## 3. 端云与数据流

- 对象契约位于 `services/<service>/contracts/<context>/<object>`；服务唯一 domain 位于 `contracts/domain.yaml`。
- 人工实现位于 `internal/<context>/<object>/<layer>`；生成代码位于 `generated/<context>/<object>`，禁止生成物藏在 `internal`。
- 配置有效值由 `config/schema.yaml` 默认值与 `environments/<env>/config.yaml` 差异合成。
- 公共 migration/template/policy/skill/static/model 位于 `resources/`；环境只选择 seed、Data release 和 artifact digest。
- 部署有效清单由 `deploy/base` 与 `environments/<env>/deploy` 合成；镜像 digest、配置摘要和资源摘要在 package 阶段注入。
- Ops 四环境目录只引用各服务同名环境入口以及 external/platform workload，是可执行装配而非注册表。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 服务自治与路径反向映射

- 决策：服务内路径固定为 `internal/<context>/<object>/<layer>`，domain 从 `contracts/domain.yaml` 取得。每个发现的服务根由一个 L1 的直接 `Service` 根拥有，`contracts/metadata/_shared` 由 runtime 拥有；同一对象的 contracts、generated 和 tests 使用相同 context/object 路径。
- 理由：路径必须能够从服务、context 与 object 唯一反向定位 owner，避免对象目录、宽泛 fallback 和人工 catalog 同时成为真相源。
- 被否决方案：在文件中重复 domain/context/object、使用 alias 消歧、保留全局对象注册表、按 DDD layer 建服务级大桶。
- 约束：同一 domain/object 不得跨 context 重名，声明 API route 的对象必须拥有同路径真实源码，禁止把实现集中到“主对象”目录；对象 adapters/infrastructure 不得被兄弟对象直接导入，多对象 adapter 仅在 cmd 组合。
- 影响：跨对象协作经 typed port/event，跨服务禁止导入 `internal` 或 `generated`。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md)、[`domain-service-directory-ownership`](./domain-service-directory-ownership/spec.md)、[`repository-layout-hygiene-and-retirement`](./repository-layout-hygiene-and-retirement/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 四环境星型继承

- 决策：每个服务的 `environments/alpha|beta|gamma|prod` 是环境唯一入口；四环境只共同依赖服务公共 `config/schema.yaml`、`resources/` 和 `deploy/base`，彼此不得继承。
- 理由：环境间继承会隐藏实际生效值并形成第五种组合状态，星型继承使差异和准出边界可审计。
- 被否决方案：将环境差异散落到 `config/environments`、`resources/seeds/<env>`、`deploy/overlays`，引入 `environments/common` 伪环境，或让 beta/gamma/prod 逐级继承。
- 约束与影响：`APP_ENV` 由路径推导，config/image/resource version 由摘要推导；环境文件只保存差异、secret reference、external binding 和资源引用。
- 关联要求：`REQ-003`

<a id="dec-003"></a>
### DEC-003 第一方部署归服务、全局只装配

- 决策：第一方 workload 基线和四环境入口归领域服务；Ops 只保留四环境聚合、跨服务平台策略和 coturn/livekit 等 external workload。
- 理由：workload 与服务代码必须由同一 owner 演进，Ops 只负责跨服务装配才能避免部署清单漂移。
- 被否决方案：Ops 复制所有第一方 workload、保留 environment topology 人工注册表、使用 seed-box 组合业务服务。
- 约束：seed 由各服务 job 执行，Data 大制品只通过 `releaseRef + digest` 绑定。
- 影响：prod 包禁止 fixture、mock、测试 seed 和明文 secret。
- 关联要求：`REQ-003`、`REQ-004`

<a id="dec-004"></a>
### DEC-004 生成产物独立边界

- 决策：所有 codegen 输出必须位于服务根 `generated` 或 App/Portal 各自既有 generated 根；`internal` 只保存人工维护实现。
- 理由：生成代码与手写领域实现分离后，codegen 才能幂等重建且不会覆盖业务逻辑。
- 被否决方案：在对象 `internal` 下设置 generated、把生成 `.g.go` 与手写 domain model 混放、提交无 marker 产物。
- 约束与影响：生成 package 必须是独立可导入包，人工代码显式依赖生成 contract type；codegen/check 必须幂等。
- 需求追踪：`REQ-002`、`REQ-005`

<a id="dec-005"></a>
### DEC-005 Go 单模块是技术构建边界，不是服务所有权边界

- 决策：Go 服务共享 `quwoquan_service/go.mod`，禁止服务内嵌套 `go.mod` 或 `go.work`；Python recommendation-service 独立使用本服务 `pyproject.toml`。
- 理由：当前 Go runtime、codegen 和跨服务技术协议处于同一模块；强行拆成循环依赖的嵌套 module 只会增加发布与依赖治理复杂度，不增强领域自治。
- 约束与影响：服务自治由独立 contracts、对象源码、配置、资源、部署、环境入口、Dockerfile 和 Makefile 保证；跨服务 `internal/generated` import 仍为零，构建产物按服务独立生成。
- 被否决方案：为目录外观给 13 个 Go 服务复制 `go.mod`，或引入 `go.work` 和根模块/服务模块循环 replace。
- 关联要求：`REQ-002`、`REQ-005`

<a id="dec-006"></a>
### DEC-006 外部交互事实账本由 Integration 唯一拥有

- 决策：Provider request、attempt、result 与 dead-letter 事实只由 `integration.ExternalInteraction` 及其事实对象维护；Notification 等消费方只保存 `externalInteractionId`、业务状态与幂等 inbox receipt。
- 理由：同一次 Provider 调用若在消费方和 Integration 各维护一套状态账本，异步回执窗口必然产生矛盾事实，恢复与审计也无法确定唯一依据。
- 被否决方案：在消费方聚合冗余 provider 请求摘要、结果和取消结果，或在 `external_interaction` 内联 attempt/dead-letter 的同时再保留独立事实对象。
- 约束与影响：跨对象组合读通过引用与 projection 完成；`external_reference` 的 identity、事件 payload 与 projection 字段必须有 typed contract，禁止原始 `object` 和未声明 payload。
- 关联要求：`REQ-004`
- 关联验收：`SIT-004`

## 5. 失败与恢复

- 目录或契约移动用 Git diff 与内容摘要证明一一映射；文件无唯一 owner 时阻断变更。
- 单个服务完成 contracts/source/generated/config/resources/deploy/tests 闭环后才切换其构建入口。
- 环境渲染、Kustomize 或测试失败时保留该服务为 `GATE_BLOCK`，禁止回退旧路径双读或恢复注册表。
- prod rollout 只在同一 image/config/resource digest 的实时 SLO 达标后推进，失败按服务 package 回滚。

## 6. 质量与观测

- `make verify-service-architecture` 是人工治理门面，运行时扫描当前对象、聚合成员、服务和四环境入口，不在文档冻结数量。
- 门禁检查 DDD/CQRS 依赖、生成物边界、配置键唯一性、环境无继承、资源纯度、Kustomize 构建、external binding、migration 顺序、三层 case result 和源码缓存。
- package 输出写入仓外 `QWQ_DEPLOY_WORK_ROOT`；`.qwq_output` 只保存可删除报告与证据，均不得成为下一次构建唯一输入。

## 7. 迁移与回滚

- 迁移顺序固定为：规格与规则 → contracts/ContractGraph → source/generated → config/resources/deploy/environments → Ops/external → stackctl/gate → 三层验证。
- 不保留旧 path/schema/registry alias、fallback 或兼容读取；回滚以完整 Git 变更和发布 package 为单位，不在运行时双轨。
