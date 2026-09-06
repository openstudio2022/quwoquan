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
- [`incremental-code-health-governance`](./incremental-code-health-governance/spec.md)：candidate delta 阻断新债，全仓历史只输出热点观测。

## 3. 端云与数据流

- 对象契约位于 `services/<service>/contracts/<context>/<object>`；服务唯一 domain 位于 `contracts/domain.yaml`。
- 人工实现位于 `internal/<context>/<object>/<layer>`；生成代码位于 `generated/<context>/<object>`，禁止生成物藏在 `internal`。
- 配置有效值由 `config/schema.yaml` 默认值与 `environments/<env>/config.yaml` 差异合成。
- 公共 migration/template/policy/static/model 位于 `resources/`。Skill package 的受控发布源码固定为 `resources/skill_packages/official`，已构建且供运行时按 active release digest 读取的 immutable asset 固定为 `resources/skills/packages/official`。两者必须是互不链接的物理根，禁止运行时扫描源码或保留 fallback。环境只选择 Data release、artifact digest 与 Provider binding。“同源”只表示相同 publish/release/importer/contract/readback，绝不复制 Prod 数据库。Creator 属于 release 内容身份而不是登录 Actor，非生产 Actor 与交易数据由所属领域公开 command/event 在候选验证期产生。
- 部署有效清单由 `deploy/base` 与 `environments/<env>/deploy` 合成，镜像 digest、配置摘要和资源摘要在 package 阶段注入。组合部署时，服务可额外公开只组合自身 wiring 的薄 bootstrap，顶层 host 只消费这些 bootstrap，不能导入任何服务的 `internal` 或 `generated`。
- Ops 四环境目录只引用各服务同名环境入口以及 external/platform workload，是可执行装配而非注册表。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 服务自治与路径反向映射

- 决策：服务内路径固定为 `internal/<context>/<object>/<layer>`，domain 从 `contracts/domain.yaml` 取得。每个发现的服务根由一个 L1 的直接 `Service` 根拥有，`contracts/metadata/_shared` 由 runtime 拥有；同一对象的 contracts、generated 和 tests 使用相同 context/object 路径。
- 理由：路径必须能够从服务、context 与 object 唯一反向定位 owner，避免对象目录、宽泛 fallback 和人工 catalog 同时成为真相源。
- 被否决方案：在文件中重复 domain/context/object、使用 alias 消歧、保留全局对象注册表、按 DDD layer 建服务级大桶。
- 约束：同一 domain/object 不得跨 context 重名，声明 API route 的对象必须拥有同路径真实源码，禁止把实现集中到“主对象”目录；对象 adapters/infrastructure 不得被兄弟对象直接导入，多对象 adapter 仅在 cmd 组合。
- 影响：跨对象协作经 typed port/event，跨服务禁止导入 `internal` 或 `generated`。
- 关联要求：服务自治与目录反向映射对应 `REQ-001`、`REQ-002`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md)、[`domain-service-directory-ownership`](./domain-service-directory-ownership/spec.md)、[`repository-layout-hygiene-and-retirement`](./repository-layout-hygiene-and-retirement/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 四环境星型 authoring 与信任域构建分离

- 决策：每个服务的 `environments/alpha|beta|gamma|prod` 是环境唯一 authoring 入口。四环境只共同依赖服务公共 `config/schema.yaml`、`resources/` 和 `deploy/base`，彼此不得继承。package 从当前环境入口与只读 capsule 生成环境专属 config、SecretRef、endpoint、resource、topology 与 activation closure，可执行镜像按 `nonprod/prod` 信任域从同一 capsule 构建并由环境 composition 引用。
- 理由：环境间继承会隐藏实际生效值，按环境重复编译则把配置差异错误地升级成字节差异。星型 authoring 保证四环境差异可审计，信任域构建保证未变组件可按 digest 复用并维持 Prod 与非生产供应链隔离。
- 被否决方案：将环境差异散落到 `config/environments`、`resources/seeds/<env>` 或 `deploy/overlays`，引入 `environments/common` 伪环境，让 beta/gamma/prod 逐级继承，按四环境生成最终镜像，或让 `APP_ENV` 在进程启动后选择 Adapter、数据源或策略。
- 约束与影响：config/resource/authority version 从当前环境 capsule 的精确字节派生。image 与编译期 Provider binding 按信任域派生，Alpha、Beta、Gamma 的 external binding 必须先收敛为同一 nonprod 视图。环境文件只保存差异、secret reference、external binding 和资源引用。`APP_ENV` 只校验部署面挂载配置，缺失或错配即失败，不得反向选择制品。
- 关联要求：`REQ-003`

<a id="dec-003"></a>
### DEC-003 第一方部署归服务、全局只装配

- 决策：第一方 workload 基线和四环境入口归领域服务；Ops 只保留四环境聚合、跨服务平台策略和 coturn/livekit 等 external workload。
- 决策：当服务自治部署输入选择组合单元时，组合单元只投影进程、镜像与部署边界；每项 service 的 contracts、配置、资源、迁移、数据源与公开 endpoint 仍由原 service owner 持有。
- 理由：workload 与服务代码必须由同一 owner 演进，Ops 只负责跨服务装配才能避免部署清单漂移。
- 被否决方案：Ops 复制所有第一方 workload、保留 environment topology 人工注册表、使用 seed-box 组合业务服务。
- 约束：领域业务 seed job 数量为零；Data 大制品只通过 `releaseRef + digest` 绑定，Alpha/Beta/Gamma 验收数据只由 `stackctl verify` 经公开 command/event 创建。组合 host 只能依赖每个服务公开的 bootstrap，不得新增跨服务私有 import、共享业务 store 或进程内业务调用。
- 影响：测试数据 Provider 按选中 capability 的领域依赖闭包发现和加载；兄弟领域实现不得成为编译、打包或 import 前置。Prod 包禁止 fixture、mock、测试 seed、非生产数据控制面、租约、回执和明文 secret。
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

<a id="dec-007"></a>
### DEC-007 删除与 tombstone 三层语义各有唯一 owner

- 决策：作者软删只由 `content.Post` 聚合的 `PostStatus.deleted` 与 `deletedAt` 表达，owner 是 Post 自身。
- 决策：宿主 Post 删除后的评论级联终态只由 `content.Comment` 聚合的 `tombstoned` 状态表达，owner 是 Comment 自身。
- 决策：不可变删除事实由独立对象 `quwoquan_service/services/content-service/contracts/content/deleted_post_tombstone` 以 append-only 方式记录，owner 是该对象本身。
- 理由：三层分别回答作者是否撤回、宿主消失后子内容如何收敛、删除事件是否可审计重放，合并任意两层都会让恢复与审计失去唯一依据。
- 被否决方案：在 Post 上再增加一个 tombstone 状态位、让 Comment 反查删除事实推断自身状态、或新增第四条删除表达路径。
- 约束：HTTP 410 语义唯一绑定 `quwoquan_service/services/content-service/contracts/content/post/errors.yaml` 的 `CONTENT.USER.content_deleted`，其唯一 producer 是 `GetPost`。
- 影响：其他读 operation 遇到已删内容按自身可见性语义返回，不得复用同一 410 错误码。
- 关联要求：`REQ-001`
- 关联验收：`SIT-001`

<a id="dec-008"></a>
### DEC-008 跨上下文主体命名以 context-local 词汇为准

- 决策：user 上下文的社交主体统一命名为 `personaId`，content 与 tag 上下文使用 `actorId` 搭配 `quwoquan_service/services/content-service/contracts/_shared/enums.yaml` 的 `ContentActorDimension`。
- 理由：content 行为事实必须同时表达 persona 与 device 两个维度，压回单一 `personaId` 会丢失 device 维度，而把 user 上下文改成 `actorId` 又会让关系与身份语义失去主体约束。
- 被否决方案：在 user 上下文引入 `actorId`、在 content 上下文把 `actorId` 改名为 `personaId`、或两侧同时保留两个同义字段。
- 约束：跨上下文引用必须经显式映射完成，禁止在 wire、投影或存储层隐式等价这两个词汇。
- 影响：ContractGraph 与生成客户端按各自上下文词汇保持单轨，不生成跨上下文别名字段。
- 关联要求：`REQ-002`

<a id="dec-009"></a>
### DEC-009 contentType 只表示内容载体类型

- 决策：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml` 的 `contentType` 只表示内容载体类型，值域由 `ContentType` 决定。
- 决策：媒体二进制类型只由 `mediaType` 与 `mimeType` 表达，媒体对象不得新增 `contentType` 字段。
- 理由：载体类型决定编辑器、发布校验与阅读形态，二进制类型决定转码与派生策略，同名字段跨对象承担两种语义会让端侧无法判断按哪一层分流。
- 被否决方案：让媒体对象复用 `contentType`、把 `mediaType` 并入 `ContentType`、或在媒体侧新增第二个载体类型字段。
- 约束：新增内容或媒体字段前必须先确认所属命名族，跨族复用同名字段一律阻断生成。
- 关联要求：`REQ-001`

<a id="dec-010"></a>
### DEC-010 Notification 只镜像引用外部交互 Provider 枚举

- 决策：`ExternalInteractionProvider` 与 `ExternalInteractionAttemptStatus` 的值域 owner 是 `quwoquan_service/contracts/metadata/_shared/types.yaml`，语义 owner 是 DEC-006 声明的 `integration.ExternalInteraction`。
- 决策：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification_delivery_job/fields.yaml` 只能以 `enum_ref` 镜像这两个枚举，禁止在 Notification 侧重新声明其 values。
- 理由：Provider 上线、替换或下线只应在一处改动，消费方一旦复制 values，异步回执窗口内就会出现两套互相矛盾的合法值。
- 被否决方案：在 Notification 复制枚举 values、把这两个字段降级为裸 string、或在 Notification 侧新增 provider 别名值。
- 约束：镜像引用必须解析到 canonical enum owner，解析失败或值域漂移一律阻断生成。
- 影响：Notification 只保存 `externalInteractionId` 与幂等 inbox receipt，不因枚举镜像获得 Provider 账本所有权。
- 关联要求：`REQ-004`
- 关联验收：`SIT-004`

<a id="dec-011"></a>
### DEC-011 对象入口单轨，投影运行时事实归 object.yaml.lifecycle

- 决策：一个对象要么声明 HTTP `api_routes`，要么声明 `runtime_entrypoints`，两者不得在同一对象并存。
- 决策：投影与追加型运行时事实的唯一归属地是 `object.yaml` 的 `lifecycle`，`source_events`、`checkpoint`、`rebuild`、`tombstone` 与 `idempotency` 在有 HTTP 轨与无 HTTP 轨的对象上填写口径完全相同。
- 决策：对外可读投影的正确形态是 query 型 `api_routes` 搭配 `object.yaml.lifecycle`，projector 源码放在该对象自己的 application 与 adapters 层，不再额外声明 projector 入口。
- 理由：入口决定对象的对外契约面，运行时事实决定重放与收敛语义；两轨并存时读端口 owner 与 projector owner 同时两义，重建与 tombstone 也失去唯一依据。
- 被否决方案：为可读投影同时保留读路由与 projector 入口、把 lifecycle 字段搬到 `operations.yaml` 或第二处声明、按对象有无 HTTP 轨区分两套 lifecycle 口径。
- 约束：单轨是 metadata 校验层的结构性约束，不是只在 readiness 派生或准出阶段生效的软约束；校验层曾允许 query 与 projector 共存的历史断言不得作为重新引入双轨的依据。
- 影响：`content.profile_interaction_activity_view`、`search.search_index_view`、`search.search_request_fact`、`tag.tag_node_view` 与 `product_ops.experiment_assignment_fact` 已按该形态落地，新增可读投影照同一形态装配。
- 关联要求：`REQ-001`
- 关联验收：`SIT-001`

<a id="dec-012"></a>
### DEC-012 错误码归属由唯一 owning errors.yaml 决定

- 决策：只被单个对象发射的错误码进该对象自己的 `errors.yaml`，跨对象共享的错误码留在所属聚合的 `errors.yaml`，并由 `emitted_by` 以 `<context>.<object>.<Operation>` 全限定名枚举全部发射方。
- 决策：消费方对象不得为已有 owner 的共享码再声明一份定义。
- 理由：生成的错误码常量必须能反查到唯一 owning `errors.yaml`，消费方一旦重复定义，同一码既得到两处语义 owner，恢复动作与 HTTP 状态也会出现两套合法值。
- 被否决方案：把共享码复制到每个发射方对象、把对象专属码上收到聚合、或用 alias 让同一码同时归两个 owner。
- 约束：跨对象发射必须写全限定名，缺失或指向不存在 operation 一律阻断生成。
- 影响：`quwoquan_service/services/content-service/contracts/content/profile_interaction_activity_view/errors.yaml` 只拥有自身 interaction 类码，401 未授权语义仍由 `quwoquan_service/services/content-service/contracts/content/post/errors.yaml` 的 `CONTENT.USER.unauthorized` 唯一拥有。
- 关联要求：`REQ-003`

<a id="dec-013"></a>
### DEC-013 projections 目录只服务嵌套复合客户端 read model

- 决策：`projections/` 是嵌套或复合客户端 read model 的 codegen 装置，不是 projection kind 对象的必需声明。
- 决策：扁平 `response_entity` 的客户端类由 `fields.yaml` 生成，此时不得再加 `projections/`。
- 理由：同一 read model 同时由 `fields.yaml` 与 `projections/` 描述时，端侧会收到两个语义等价的生成类，装配方必须在两者之间选择，等于把第二真相源前置到客户端。
- 被否决方案：为目录整齐给每个 projection kind 对象补 `projections/`、或把扁平响应也改由 `projections/` 生成。
- 约束：新增 `projections/` 前必须证明该 read model 存在嵌套或复合结构，无法证明时按 `fields.yaml` 单轨生成。
- 关联要求：`REQ-002`

<a id="dec-014"></a>
### DEC-014 读投影值域可以宽于写侧闭集，不得更窄

- 决策：同一概念的写入闭集与读投影并集分别由各自 owner 声明，读投影值域可以宽于写入闭集，任何情况下不得比写入闭集更窄。
- 决策：写入闭集归发起写入的聚合自有枚举，读并集归共享 types 枚举，两者不得合并为同一个枚举。
- 理由：写入闭集决定命令能否被接受，读并集决定端侧必须能解析的全部取值；把两者收敛成一个枚举必然错一边，要么让写侧接受不该接受的取值，要么让端侧收到无法解析的合法投影值。
- 被否决方案：把读并集裁到写入闭集、把写入闭集放宽到读并集、或用同一枚举加运行期分支区分两侧。
- 约束：两侧枚举必须互相说明关系与差集来源，差集缺少 owner 说明时阻断生成。
- 影响：`user.subject_follow` 的写入闭集是对象内枚举 `SubjectFollowTargetKind`，关注频道读并集由 `quwoquan_service/contracts/metadata/_shared/types.yaml` 的 `FollowSubjectKind` 拥有，差集取值由 `PersonaRelationship` 写入。
- 关联要求：`REQ-002`

<a id="dec-015"></a>
### DEC-015 发件箱归属由存储声明与事务写入共同判定

- 决策：一条发件箱归某个对象所有，判据是该对象在自己的 `storage.yaml` 声明了该存储，并且其拥有服务内存在通过事务句柄写入该存储的生产代码。
- 决策：写入方源码所在的对象目录只是实现细节，不参与归属判定。
- 理由：按代码文件路径判归属会把共享实现误判成越界，实际有近半数发件箱声明被兄弟对象业务代码引用，涉及三分之一以上的对象，共享 store 是主流形态而非例外。
- 理由：为通过门禁去拆分共享 store 会破坏真实正确性属性，典型是会话创建在一个事务里写三个聚合状态且每个事务恰好只追加一张发件箱，继续按聚合拆分反而引入下游乱序。
- 被否决方案：按写入代码所在目录判定归属、为每个聚合强制拆出独立发件箱、或把两侧缺失合并成同一条判定。
- 约束与影响：未声明归属与未观测到事务性追加是两个独立缺口维度，关闭方式不同，不得合并为同一条结论。
- 关联要求：`REQ-001`
- 影响 Story：[`domain-service-directory-ownership`](./domain-service-directory-ownership/spec.md)、[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md)
- 关联验收：`SIT-001`

<a id="dec-016"></a>
### DEC-016 撤销对象契约的 `capabilities` 字段

- 决策：删除对象契约中的 `capabilities` 字段，不保留为非权威描述字段。
- 理由：该字段没有受控值域，没有任何校验器或治理规则消费它，真实发件箱拥有者中只有少数声明过它，且已出现单复数拼写漂移。
- 理由：它想表达的事实在 `storage.yaml`、`events.yaml` 与 `operations.yaml` 中都已有权威表达，其中发件箱归属由 `storage.yaml` 的 `publication_role` 按 `DEC-015` 表达，保留它等于保留第二真相源。
- 被否决方案：为该字段补一个受控枚举、把它降级为注释性描述、或只对新对象停用而豁免存量。
- 约束与影响：撤销由契约线执行，规格层不再引用该字段表达任何对象能力事实。
- 关联要求：`REQ-001`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 承接无效 capabilities 声明的退役。
- 关联验收：`SIT-001`

<a id="dec-017"></a>
### DEC-017 `business_rules` 只作非规范性描述，规范性约束另有 owner

- 决策：对象契约的 `business_rules` 显式降为非规范性描述字段，既不承载可机验的规范性约束，也不改造成结构化规则语言。
- 理由：其中语义精确的那部分与 `fields.yaml` 的 `constraints` 高度重叠，把它结构化只会造出第二套约束语言，使同一条约束出现两个可引用的真相源。
- 理由：全仓 693 条中有 689 条是自由散文，占 99.4%，本身不可机验，这是支撑而非决策依据。
- 被否决方案：为该字段设计结构化规则语言、按规则类型拆出子字段、整体删除该字段。
- 约束：数值区间与值域归 `fields.yaml` 的 `constraints`，行为不变量归所属节点的 REQ 与 GWT，`business_rules` 只保留供人阅读的描述。
- 影响：规格与门禁不得把 `business_rules` 当作约束真相源引用，已把它列入 canonical 契约引用的节点必须改引 `constraints` 或本节点验收。
- 关联要求：`REQ-001`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 承接约束归属划分的落地。
- 关联验收：`SIT-001`

<a id="dec-018"></a>
### DEC-018 App 以能力驱动的对象纵切承接端云业务模型

- 决策：App 业务实现的 canonical 位置是 `lib/service/<service>/<context>/<object>/{domain,application,adapters,presentation}`；`<service>` 是拥有该 context 的云侧服务名的 snake_case 形式，context/object 取自 ContractGraph 与 L1 稳定工程归属，`runtime`、`design_system`、`l10n` 只承接横切能力。
- 决策：目录层不是固定四层脚手架。对象存在 App-exposed operation 时要求 application/adapters，被页面对象契约认领时要求 application/presentation，只有 App 自己维护不变式或状态机时要求 domain；纯云对象没有端侧能力时不创建 App 对象目录，append-only fact 不直接拥有 presentation。
- 理由：用云侧 kind 无条件要求全部 App 层会生成空 facade 和占位实现，而继续按 `ui/cloud/core` 技术大桶组织又无法从路径反向定位对象、规格和测试 owner；能力事实驱动的纵切同时避免两种失真。
- 被否决方案：为每个云对象生成四个空 App 层、按页面或网络/缓存技术类型建顶层大桶、以文件名或手工映射表推测 owner、保留旧目录作为长期兼容入口。
- 约束：层义务只能从所属服务 contracts、页面对象契约与所属规格的端侧不变式派生，不另建 App capability registry；缺少归属或能力事实时 fail-closed，不以空文件、re-export 或路径 alias 补齐。
- 影响：旧 `ui/cloud/core/app/application/infrastructure` 大桶已不在 App 生产树内，不得以任何形式重建；业务文件、测试和 readiness 结构证据均由同一对象身份反向定位。
- 关联要求：`REQ-002`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 承接 App 对象纵切与能力层义务。
- 关联验收：`SIT-002`

<a id="dec-019"></a>
### DEC-019 页面由唯一 source owner 组合 participants，App 层依赖保持单向

- 决策：每个页面在页面对象契约中保留唯一 source owner 与全部 participant object；物理页面位于 source owner 的 presentation，participant 只通过各自 `application/public/**` 下的 port/facade/event/read view 参与，文件归档不得改写页面的语义参与集合。
- 决策：App 对象内依赖方向为 presentation 指向自身 application/domain、application 指向自身 domain、adapters 实现自身 application port 并使用自身 domain；具体 adapter 仅由 `runtime/di` 组合，presentation 不导入具体 adapter，domain 不依赖 Flutter、IO、generated transport 或其他层。
- 决策：跨对象 import 的唯一代码入口是目标对象的 `application/public/**`；该公开子边界只暴露纯 port/facade/event/read view，并且自身只能依赖所属对象 domain 与纯 generated value type。对象私有 application、domain、adapters、presentation、barrel re-export、旧路径 shim、双轨 import 与 compatibility fallback 均不构成公开边界。
- 决策：每个 `clientContract` 必须有唯一真实消费身份。页面消费以 `object_ids` 与 `query_slices/command_operations` 绑定，非页面后台/runtime 消费以 `runtime_execution` 绑定 object、operation、production path 与 symbol；仅存在 generated adapter/DI 不算消费，同一 object/operation 不得同时登记页面 participant 与 runtime execution。
- 理由：多对象页面若按单一物理路径覆盖参与关系，会把真实跨对象依赖藏进 UI import；若 presentation 直接拿 concrete adapter，则测试 double 隔离、错误恢复和 Remote composition 都无法在对象边界验证。
- 被否决方案：把多对象页面放回全局 pages 大桶、让 `runtime/shell` 成为业务页面 owner、允许 presentation 直接导入 adapter、以 barrel 或旧路径 export 维持迁移期双轨。
- 约束：`runtime/di` 是唯一业务装配例外，其他 runtime/design_system/l10n 代码不得反向拥有或导入业务对象私有实现。
- 约束：participant 确有独立 Widget 生命周期时由 `runtime/di` 注入 typed `WidgetBuilder`/slot，不能通过 presentation-to-presentation import 复用；迁移按单文件单入口切换，不能保留长期 shim。
- 影响：页面、对象测试、错误恢复和埋点均能回到同一 source owner，同时保留跨对象 Journey 的完整参与关系。
- 关联要求：`REQ-002`、`REQ-006`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 承接页面 source owner、participants 与依赖边界。
- 关联验收：`SIT-002`、`SIT-006`

<a id="dec-020"></a>
### DEC-020 撤销对象契约的 `lifecycle.transitions` 字段

- 决策：删除对象契约 `lifecycle` 下的 `transitions` 字段，不保留为非权威描述字段，`object.schema.json` 以 `not: {required: [transitions]}` 关闭该键的再次声明。
- 理由：该字段在 10 份 `object.yaml` 中长期以两种互不兼容的 shape 并存，一种是 `[from, to, command]` 位置三元组数组，另一种是 `{from, command, to}` 键控映射，还带有 `transition_notes` 自由散文旁注；同一个键的两种 shape 能长期共存本身就自证没有任何解析方消费它。
- 理由：它想表达的状态迁移事实已由四种形态权威承担——合法状态值域归 `object.yaml.lifecycle` 的 `state_field` 与 `states`，驱动迁移的命令归 `operations.yaml`，运行时可达性归领域层状态机守卫（典型是 `quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime/transitions.go`），持久化闭集归 migration 的 `CHECK (status IN (...))` 约束；保留它等于在这四者之上再加一份既无值域又无消费者的第二真相源。
- 被否决方案：在两种 shape 中择一收敛后补 schema、把它降级为注释性描述、或让它成为领域层状态机的生成输入。
- 约束与影响：撤销由契约线执行，状态迁移事实只能引用上述四种 owner，规格层不再引用该字段表达任何迁移可达性。
- 关联要求：`REQ-001`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 承接无效 transitions 声明的退役。
- 关联验收：`SIT-001`

<a id="dec-021"></a>
### DEC-021 consumer 身份由消费对象反向边承担，建机制但不建中央 consumer registry

- 决策：建机制。事件 consumer 的唯一身份真相源是消费对象自己 `object.yaml` 的 `lifecycle.source_events[]`，其值为完整 `event_ref`；`consumer_ref` 恒等于消费对象的 objectId，由 compiler 反向生成 `event_ref -> consumer_ref[]`。
- 决策：撤销 producer 侧 `events.yaml` 的 `consumers` 字段，`_schemas/events.schema.json` 以 `additionalProperties: false` 关闭该键的再次声明。
- 决策：维持契约线 metadata 设计文档对中央 consumer registry 的禁令，同时维持对 name-only 推断与顶层 `consumption/subscriptions` 的禁令。
- 理由：撤销前 `consumers` 是无值域自由字符串，75 个去重名累计 414 次引用，同一值位混装可部署服务、进程内订阅组、stream 名与逻辑投影四种所指；`projection-workers` 被 11 份 `events.yaml` 指名 50 次却在全仓没有任何定义处，因此「某 consumer 是否存在」在该值域上没有可判定谓词，声明既不可验证也不可证伪。
- 理由：反向边把值域从四种所指收敛为一种，`consumer_ref` 只能是已存在的对象，存在性因此退化为对象解析；可判定性来自值域收敛而不是来自登记处，这正是不建中央 registry 也能取得该结果的原因。
- 理由：真相源仍分散在各消费对象手中，与契约单轨一致；中央 registry 会在对象契约之外再立一份需人工同步的名册，其漂移无法自动复核，属于典型第二真相源。
- 被否决方案：维持现状不建机制——可判定性缺口已由反向边消解，继续维持等于为一个已撤销的字段长期留 OPEN。
- 被否决方案：把 `consumers` 按所指拆成 `consuming_services` / `in_process_subscriptions` / `projections`——只是把一个无身份值位拆成三个，producer 侧替消费方声明这一结构错误未变，且与本条撤销该字段的决策直接冲突。
- 被否决方案：撤销中央 registry 禁令改建登记表——禁令理由仍成立，且反向边已提供更强结果，registry 只会成为第二真相源。
- 约束与影响：零反向边的事件必须写 `no_consumer_reason`，有反向边时必须删除它；`transactional_outbox` 至少需要一条反向边，`transactional_event_log` 与具名 consumer 互斥。三条由 `CONTRACT.EVENT.OUTBOX_WITHOUT_CONSUMER`、`CONTRACT.EVENT.EVENT_LOG_WITH_CONSUMER` 与缺 `no_consumer_reason` 的校验强制。
- 约束与影响：撤销执行不得以删声明消红，原 consumer 事实必须落到反向边或写明 `no_consumer_reason`。当前 220 条事件构成全覆盖二分，121 条有反向边、99 条有 `no_consumer_reason`，无一条两者兼有或两者皆无，且无悬空 `source_events`。
- 约束与影响：consumer 身份与投递路径是两件事，后者归 `delivery_semantics` 受控枚举，不得合回一个字段。
- 关联要求：`REQ-001`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 的 `OPEN-010` 据本条改写。存在性与投递路径两项已消解，该 OPEN 仅继续承载可达性：反向边只证明消费对象声明了这条边，不证明运行时 handler 真的收到，`no_consumer_reason` 亦是自由散文而无结构判据。
- 关联验收：`SIT-001`

<a id="dec-022"></a>
### DEC-022 平台级拒绝码归 `runtime_failure_codes.yaml`，并在该文件引入用户面字段集

- 决策：`GATEWAY.USER.route_not_found` / `unauthorized` / `forbidden` / `invalid_argument` 与 `GATEWAY.MIDDLEWARE.unavailable` 的唯一声明位是 `quwoquan_service/contracts/runtime_errors/errors/runtime_failure_codes.yaml`，不归任何单一服务对象。
- 决策：该文件新增一组仅对「会直接返回给用户」的码声明的可选键 `httpStatus` / `userMessage` / `recoveryAction` / `recoveryAfterSeconds` / `disruptionLevel` / `goConst` / `reason`；纯内部诊断码不写这组键。`recoveryAction` 与 `disruptionLevel` 的值域沿用 `runtime_recovery_policy.schema.yaml` 的 `RuntimeRecoveryAction` / `UserDisruptionLevel`，不另立词表。
- 理由：这些码由 `runtime/auth` 的 generated operation guard 与 `runtime/streaming` 在任何 owner handler 之前产出，而 `runtime/auth` 被全部 14 个服务链接，任一服务都可能发射它们。把它们挂到某一个服务对象名下会让声明位与发射面不一致，构成按目录归属的假属主。
- 理由：扩字段而非另立文件，是因为该文件已是平台级码的既有归属地，只缺用户面维度；再建一处会与它构成第二真相源。
- 被否决方案：在 `api-edge` 建 `edge_security/operation_admission_decision` 对象承载——api-edge 只是众多链接方之一，且该对象无自有 HTTP operation，其本地层只能薄包装 `runtime/auth`，属为满足目录门禁而造的属主。
- 被否决方案：维持 `operation_guard.go` 内的文案 map 为事实真相源——运行时镜像不可作为声明位，且端侧无法消费。
- 约束与影响：`runtime/auth` 仍保留本地文案镜像，因为它不得 import 任一服务的 generated 错误包；镜像的非权威性由 `TestOperationGuardUserMessagesMatchContract` 双向断言强制，该测试已验负例（改文案即报漂移）。
- 约束与影响：这五个码经本文件的 Dart codegen 进入 `runtime_failure_codes.g.dart`，端侧由此持有码常量；服务对象 `errors.yaml` 一侧受 `codegen_app_metadata` 域白名单约束，`gateway` 不在其内，故该路径不承载这些码。
- 关联要求：`REQ-001`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 的用户面错误呈现声明位。
- 关联验收：`SIT-001`

<a id="dec-023"></a>
### DEC-023 `process_manager` 以专用写入口与 checkpoint 版本源承载长流程，端侧读写面与聚合物理分离

- 决策：`process_manager` 的 `access.commands` 使用专用 `process_facade`，不得复用 `aggregate_facade`。调用方向长流程投递的是「推进、取消、恢复」这一次编排意图，与向聚合提交一次状态变更不是同一语义。
- 决策：`identity.version_source` 恒为 `checkpoint`，且对象必须声明 `lifecycle.state_field` 与至少两个 `states`。长流程的进度真相是它推进到哪个检查点，不是某个聚合字段的版本号。
- 决策：云侧必需层是 domain、application 与 infrastructure 三层，缺一即阻断。domain 承载状态机与补偿规则，application 承载编排，infrastructure 承载 checkpoint 持久化。
- 决策：`access.queries` 是条件规则而不是硬性 `named_reader`。经公开合同暴露的流程必须给出具名状态读取面，只经事件参与的内部 saga（`cross_context: event_only`）没有外部调用方，允许 `none`。
- 决策：`storage_role` 复用既有的 `authoritative`，不为该 kind 新增枚举值。`storage_role` 描述的是存储 seam 的性质而不是对象 kind，saga 的 checkpoint 存储与聚合存储同为持久、权威、按 CAS 提交，再造一个值只会让同一性质出现两个名字。
- 决策：端侧读写面必须按 `*ProcessQuery` 与 `*ProcessCommandWriter` 两个命名族物理分离，禁止与 aggregate 共用 `*CommandWriter`。长流程命令只表示一次推进意图被受理，真实终态要回读 checkpoint，共用一个 port 会让调用方无法区分「命令已受理」与「流程已完成」。
- 决策：`process_manager` 通常不是 PageOwned，长流程由发起它的页面组合；是否拥有 presentation 仍由页面对象契约的 `source_path` 这一唯一信号决定，因此它不进端侧禁止层表。
- 理由：长流程与聚合的失败语义根本不同。聚合命令要么成功要么失败并留下一致状态，长流程会在中途留下已提交的外部副作用，必须能从 checkpoint 续跑或补偿，这一差别必须在写入口、版本源与端侧 port 三处同时可见，否则调用方会按聚合语义误用。
- 被否决方案：让长流程继续以 `aggregate_root` 建模并靠命名约定区分——kind 是门禁的唯一输入，靠命名区分等于没有判据，必需层、写入口与端侧禁止层都无法按真实语义派生。
- 被否决方案：对全部 `process_manager` 硬性要求 `named_reader`——纯事件驱动的内部 saga 没有外部调用方，强制给读取面会造出无人调用的 operation，属为满足门禁而造的接口。
- 约束与影响：边界候选 `media_upload_session`、`account_session`、`assistant_session` 与 `rtc.call_session` 保持 `aggregate_root`。判据是四条同时成立：状态迁移属该业务事实自身的合法演进、失败即终态、无已提交的外部副作用需要补偿、没有「从 checkpoint 续跑」语义。
- 约束与影响：端侧 port 改名会穿透 `runtime/di` 与 generated client，因此命名族只在架构门禁的层规则中登记并随其输出，实际标识符扫描由端侧 kind 对齐门禁承担，两处不得各自定义命名族。
- 关联要求：对象种类与端侧分层对应 `REQ-001`、`REQ-002`
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 的 `REQ-012` 按本条派生端侧层义务与 port 命名族。
- 关联验收：`SIT-001`

<a id="dec-024"></a>
### DEC-024 对象级隐私、事件线上身份与 storage 实现必须从 canonical authoring 派生并反向对帐

- 决策：对象 `privacy.yaml` 的字段策略是日志字段治理的唯一 authoring source；生成器从当前对象身份派生 `fieldPrivacyPolicies` 到 Go、Dart、Python 与运营端 catalog，运行时按 `operationId -> objectId` 选择策略。App 不保留手写敏感键表或第二套字段策略。
- 决策：`first_party_service_internal` 表达仅第一方服务内部可见的字段。事件载荷字段与消费对象的 lifecycle 反向边必须逐字段通过该可见性约束；`content.post.moderationStatus` 属于该内部类别，不因对 App 不可见而从安全关键事件中删除。
- 决策：`transactional_outbox` 事件的线上身份由 `events.yaml.wire_event_type` 唯一 authoring，并由服务端与 Python 生成器产出常量；production producer/consumer 不得长期持有并行字面量。
- 决策：所有读取 object-local `storage.yaml` 的 Go、App 与 Ops production/governance consumer 必须经 canonical `storagecontract.Decode` 或其 strict JSON view；启动失败、超时、非零退出、空/非 JSON/stderr、键集漂移与 source TOCTOU 均 fail-closed。Python 不得直接 `safe_load` storage authoring、复制键表或保留 fallback。
- 决策：`storage.yaml.indexes` 只有在声明的键集与 production 建立、查询或唯一性守卫语义等价时才成立。门禁按键、顺序、唯一性、partial predicate 与真实 create/use 语义比对，不以索引名字相等作为判据，也不允许声明但无人建立或建立但无人使用的索引通过。
- 理由：字段隐私、事件线上身份与索引都曾出现「声明存在但运行时不消费」或「运行时硬编码但声明不拥有」的第二真相源；从 authoring 单向生成并对 production 使用反向核验，才能同时发现欠覆盖、过覆盖与 stale 声明。
- 约束：source generator、校验器与模板完成只证明 authoring/implementation 机制成立；generated catalog、运行时常量和环境证据必须来自同一稳定 source hash 的唯一 fresh generation，不能由移动中的生成物或手改产物替代。
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 承接 fresh generation、双端运行时消费、Data 冻结项与全链漂移门的剩余准出。
- 关联要求：对象隐私、事件身份与 storage 同源对应 `REQ-001`、`REQ-002`。
- 关联验收：`SIT-001`

<a id="dec-025"></a>
### DEC-025 缺席、空值与失败是三种不可互换的结果状态

- 决策：任何返回值只能表达「在场有值」「在场为空」「缺席」「失败」之一。失败必须经异常、`RuntimeFailure`、`AppError` 或领域 sealed 结果表达，不得降级编码为 `null`/`nil`/空字符串/空集合；缺席不得塌陷为空字符串或零值。
- 决策：生成代码不得自行补入契约未声明的默认值，也不得对未声明可空性的字段自行推定可空。缺席只能由契约显式声明的可空性或默认值决定；解码期补值必须能追溯到契约上的 `default` 声明。
- 决策：Go 的指针面只减不增。`infrastructure` 可用 `*T` 与 `sql.Null*` 承载列可空事实，需要三态的写入面使用专用 change set。`domain`、`application` 与出站 DTO 的可选标量使用值类型，缺席以省略键表达。HTTP wire 边界上的值类型 `bool` 禁止 `omitempty`，与该字段契约声明的可空性无关。`bool` 只有两态，`omitempty` 让在场的 `false` 在 wire 上表现为缺席，而缺席是另一个状态；必填字段上这还会直接打成端侧 fail-closed 解码失败。确需区分「未设置」与「false」时用 `*bool`，指针在这一处恰好把三态表达对了。
- 决策：`catch` 内 `return null` 只有两条合法出路，因为两类代码本质不同而静态分析读不出区别。异常本身即形状判定（「这段输入不是一个 X」）的解析器，以 `try` 前缀命名承诺该语义，对齐 `int.tryParse` 的生态惯例；其余一律要求留下运行期证据。让代码自己声明属于哪一类，两条路就都能自动判定，门禁因此不需要豁免名单。同一条判据覆盖以空集合、`0` 或空字符串代替 `null` 的变体——换个零值不改变「失败被伪装成在场为空」这件事。`return false` 不在其列：`false` 表达的正是「这次没做成」，它的可观测性由异常吞咽预算门禁承担。
- 决策：「出站 wire 边界」按数据流判定，不按目录名。从出站序列化调用点（`writeJSON` / `httpcodec.WriteJSON` / `json.NewEncoder(w).Encode`）的实参出发，回溯变量赋值与函数返回类型定位 struct 定义处，再沿字段类型递归展开嵌套与列表元素。早先的口径是「文件路径含 `adapters/inbound/http`」，`CommentCommandResult.Replayed` 因此带着契约冲突进入现网：DTO 定义在 `application/contracts.go`，handler 只是把它传给 `writeJSON`，按目录名判定时它根本不算 wire。无法静态定位类型的调用点单独报告、不计入违规——门禁只对能证明的部分下断言，剩下的必须可见而不是被默默当成合规。
- 决策：门禁自身必须可证伪。本次改动涉及的门禁脚本必须有被 gate 链执行的行为级 `local_contract`，缺失即 BLOCK。「恰好有同名测试时才检查」是同构的假绿：一个门禁完全没有配套测试时配套集合为空，循环体一次都不执行，门禁反而放行——越是新写的、判据最没被验证过的门禁越容易掉进去。改动面取 `merge-base` 到 `HEAD` 的已提交增量，不含未提交工作树：脏工作树是本仓库常态，把它计入会让门禁长期为并行改动报红，而持续假红最终只会被 `--no-verify` 绕过。
- 决策：棘轮基线的身份粒度到函数与字段，不到文件。配额挂在文件上时，同一文件内删一处、在另一个函数里添一处，总数不变而门禁看不见。相对 `HEAD` 的计数或身份集合增加一律失败，`_governance` 文字完整不能替代单调性检查——留痕字段齐全时就放行，等于把「债只能减」交给作者自觉，而改基线数字恰好是最省事的绕过方式。
- 理由：`null`/`nil` 同时承担「没有」「空的」「没做成」三种含义时，调用方只能靠判空猜测，失败会被当作空数据继续流向下游。把四态在类型与契约上分开，消费方才可能不判空。
- 约束：wire 字段可空性目前存在三套并行 authoring——`fields.yaml` 的 `NOT_NULL`/`NULLABLE`、assistant `schema.yaml` 的 `required`/`default`、rtc `events.yaml` 的 `payload_fields` 与 `client_payload_defaults`。三者都是契约层的取值声明而非生成器缺陷，生成器忠实执行了各自的声明；收敛需要逐字段的 wire 语义裁决，按 Story OPEN 承载，不得由生成器单方面改写。在收敛前，各管线的当前语义由 `local_contract` 分别锁定，防止其中任何一条悄悄漂移。
- 约束：RTC 方向的收敛必须先取证据再动生成物。实测 envelope 显示，契约声明 `NOT_NULL` 的 `status` 与 `eventId` 在全部通话事件上都不出现——`payload_fields` 白名单先做了裁剪，`omitempty` 再省略空值。此时把生成物切成 fail-closed 必填会让来电信令全面解析失败。收敛只能作为「codegen 改读 `CallEventPayload`、服务端去掉不该有的 `omitempty`、端侧移除兜底」的一次性同源变更，分开做任意一步都会打断信令。
- 被否决方案：全局禁用可空类型、把可缺字符串统一塌陷为空串、把 `NULLABLE` 标量统一映射为 Go 指针、引入 `Result`/`Either` 第二套错误模型、在未做字段级裁决前由生成器批量删除契约声明的 `default`、把 `catch` 内 `return null` 一律判死、按目录名近似出站边界，以及对出站列表批量删除 `omitempty`。这些方案分别会扩大 nil 解引用面、误伤合法解析器、漏掉真实 wire 边界，或让 nil 切片序列化成 `null`，都不能保持缺席、空值与失败的单义性。
- 约束与影响：出站列表与布尔字段在 wire 上分别稳定为 `[]` 与显式 `false`，由真实响应体的原文断言证明——断言不能落在解码后的结构体上，`null`、`[]` 与缺键在那里已经被抹平成同一个空切片。领域端口以空返回兼作未命中信号的存量、契约未声明可空性的字段、出站列表的 `omitempty` 三笔以同一份身份指纹棘轮承载，清零后删除基线并转为硬门禁；Dart 侧与 Go wire 边界的 `bool` 实测已清零，不留基线文件。
- 影响 Story：[`absent-empty-failure-nullability`](./absent-empty-failure-nullability/spec.md) 承接四态定义、跨管线单义与三道门禁。
- 关联要求：`REQ-001`、`REQ-002`
- 关联验收：`SIT-001`

<a id="dec-026"></a>
### DEC-026 本地工作副本治理由单一策略驱动三个执行面，判定实时派生且边界诚实

- 决策：worktree 与 clone 的创建授权、滞留提醒与 hooks 自检共用唯一策略文件 `quwoquan_ops/policies/worktree_policy.yaml` 和唯一派生实现；Cursor、Codex 与 git hooks 三个执行面只做协议适配，不各自实现判定规则。三处规则一旦分写，最先漂移的总是最少被触发的那一处。
- 决策：执行面 hook 只注入上下文，不做硬门。创建授权是根 `AGENTS.md` 对执行体的行为要求，hook 在识别面命中且未留痕时把规则、留痕方式与 canonical 形态注入（Cursor `agent_message`/`user_message`，Codex `hookSpecificOutput.additionalContext`），始终 `allow`，判断权留给 Cursor/Codex。曾经的 `ask`/`deny` 形态在实践中把 lane worktree 的创建自锁在 `dev1.0`、让 Codex 每条 Bash 背负秒级策略加载，并诱使执行体绕道整仓 clone；硬门只应在准出（lane→`dev1.0` 合入、交接）由门禁与 CI 承担。未命中创建面的命令必须在加载策略前返回。
- 决策：`post-commit` 退化为 observe-only 的轻量 dirty/due 标记，只原子写可删除 marker，不加载 policy/inventory，也不执行 git 扫描；下一次受支持且到期的 sessionStart 才做完整扫描。Cursor 本地 Agent 使用当前官方 `sessionStart` 并以顶层 `additional_context` 投递，hooks 配置热重载无需 Reload Window；Codex 保持现有 `SessionStart`/`hookSpecificOutput.additionalContext` 命令路径，本决策不推断其真实协议。Cursor 的无 matcher `beforeShellExecution` every-shell fallback 与包装脚本退役。Cloud Agent 不支持 sessionStart，能力矩阵以 `OPS.WORKTREE.CLOUD_SESSION_REMINDER_UNSUPPORTED` 显式诊断，不以高频 fallback 伪装支持，也不新增硬门。完整扫描由 process-group deadline 约束总 wall-clock，超时/异常记录 lastError 与 elapsedMs、保留 marker，并始终 fail-open。
- 决策：工作副本清单只实时派生，不落台账。授权是随命令传递的一次性凭据，不产生「已授权清单」；滞留判定由 `git worktree list`、发现根扫描与 `git rev-list` 现算。任何形式的 registry、allowlist 或滞留基线，在下一次意外发生时正好会是过期的那一份。
- 决策：git hooks 是三个执行面唯一的公共底座，因此 `core.hooksPath` 的安装状态本身是被治理对象。自检不得只挂在 pre-commit——hooks 失效时 pre-commit 恰好不会运行，而那正是最需要发现问题的时刻；判定改由聚合门禁与执行面会话开始交叉承担。
- 理由：`branch_policy.yaml` 只约束分支名，而实际失控的工作副本没有一个违反分支禁令（临时探针为 detached HEAD，独立 clone 均在 `dev1.0`）。真正的失控维度是工作副本的数量以及其中滞留的未合入工作，这个维度没有任何策略覆盖，也没有任何一道门禁会因它变红。
- 约束：本机制只提醒意外，不阻断任何执行。执行体有权自行设置环境变量与改写仓内文件，hook 本就不构成安全边界；实现与回执必须如实声明该边界，不得表述为强制保护。真正的硬门只在准出：branch policy 与 CI Delivery Gate 守住 lane→`dev1.0` 的合入边。
- 被否决方案：为「已授权 worktree」维护受版本控制的 allowlist（与仓库禁止 registry/inventory 冲突，且必然过期）、仅用 git hooks 覆盖全部执行面（git 没有 worktree 创建前置 hook，`post-checkout` 触发时已无法撤销）、仅用执行面 hook 而不修 git hooks（clone 目标不继承 hooks，人工终端完全失管）、引入常驻守护进程做每日提醒（仓外状态，与仓库自治边界冲突）。
- 影响 Story：[`local-worktree-lifecycle-governance`](./local-worktree-lifecycle-governance/spec.md) 承接授权提醒、滞留提醒、hooks 自检与无台账约束。
- 关联要求：`REQ-005`
- 关联验收：`SIT-005`

<a id="dec-027"></a>
### DEC-027 服务模块装配收敛到 servicekit，进程相位、模块装配与领域装配三层单轨

- 决策：Go 服务的启动装配固定为三层，各层唯一职责。`quwoquan_service/runtime/servicehost` 拥有进程相位机（ValidateConfig → PrepareMigration → Bind → Start → Ready → OpenAdmission → Shutdown）、Composition 身份与虚拟路由。`quwoquan_service/runtime/servicekit` 拥有模块装配套件：运行时身份解析、配置快照加载与身份校验、Redis 场景路由、消息传输装配、观测栈、auth 栈、通用 `servicehost.Module` 实现与 Builder、standalone 壳、config sync 接入。各服务 `cmd/api` bootstrap 只保留带 env tag 声明的 config 结构体与领域装配，装配骨架与 env 覆盖引擎按 [DEC-028](#dec-028) 由 servicekit 承载。
- 决策：新服务与迁移到 servicekit 的服务必须消费 servicekit 构件，不得复制身份、配置、Redis、传输、观测、auth 与生命周期样板；迁移即删除旧样板，不留兼容 shim。
- 决策：servicekit 的依赖边界是 `runtime/*` 与 `internal/platform/*`，不得 import 任何服务的 `internal`、`generated` 或顶层共享 `generated/**`。依赖 generated 产物的输入（operation guard、server timeouts、message binding descriptor、stream rootID）由服务 bootstrap 从自己的 generated 包构造后以值对象入参传入。
- 决策：每个 descriptor_owner 服务保留薄 `cmd/api/message_transport.go` 作为 message root，文件含本服务 generated descriptor import 与 `CompiledBindingFor(...)`，正文调 `servicekit.NewMessageTransport`。preflight（`RequireConfiguredRedisMessageTransport`）由 servicekit 内部必然执行并由其同包测试锁定，外部 provider governance gate 的判据同步认可该形态。
- 决策：config sync 接入的合法源码形态有二：函数库装配的服务显式调用 `servicekit.RegisterConfigSync`（单行）；声明式 Bootstrap 装配的服务由 `servicekit.Bootstrap` 契约内置注册（[DEC-028](#dec-028)），源码字面量为 `servicekit.Bootstrap(`。机器 config ACK 治理 gate 的源码字面量判据同时认可两种形态。config sync 收敛率与 staleness 判定的验收锚点归 [commercial-readiness-risk-closure REQ-006](../../platform-ops-governance/commercial-readiness-risk-closure/spec.md#req-006) 与其 SIT-006，指标与告警面归 [observability-and-alerting](../../platform-ops-governance/observability-and-alerting/spec.md)，本 DEC 只承载装配形态裁决。
- 决策：配置分为四层，各有唯一真相源，互不越界。第一层契约/代码预制：服务名与模块闭包、路由/operation/超时、Redis scene 名与 key 前缀、stream 名，变更走 contracts + codegen + candidate 发布。第二层环境装配静态：`config/schema.yaml` 与 `environments/<env>/config.yaml` 渲染到 `CONFIG_ROOT` 快照并由 `CONFIG_VERSION` digest 钉住，物理端点与凭据只以 secretRef 环境变量名引用，按 [deliver-deploy-prod-pipeline DEC-005](../deliver-deploy-prod-pipeline/design.md#dec-005) 永不进镜像字节。第三层 ops 配置中心热调：限流阈值、feature flag、采样率、文案覆盖、运营开关，判据是值变化不改变拓扑与依赖身份且需要分钟级生效与独立回滚。第四层进程注入身份：`SERVICE_NAME`/`APP_ENV`/`CONFIG_VERSION`/`IMAGE_VERSION` 等，绑定 candidate 由部署面注入。
- 决策：组网配置逻辑面契约预制、物理面环境注入，两者都不进配置中心。逻辑组网（服务存在性、名称、依赖、逻辑端口）变化是部署事件，必须携带 Composition/Topology 身份与整体回滚语义（[deliver-deploy-prod-pipeline DEC-003](../deliver-deploy-prod-pipeline/design.md#dec-003)）；物理组网（实际地址、URI、凭据、容量）只由环境装配注入。
- 决策：服务名由 Builder 入参单点声明，与 `composition.yaml`、compose service name、specs 同一字面值；跨服务调用键名由 `Identity.ServiceBaseURL` 统一派生 `<TOKEN>_SERVICE_BASE_URL`，值仍由部署面或宿主注入。
- 决策：代码内 magic 兜底（硬编码监听端口、`mongodb://localhost:27017`、数据库名）随迁移移除，监听地址与数据库名缺失即启动失败；本地便利由 alpha `config.yaml` 默认值承担，默认值归 `config/schema.yaml` 与环境入口，不归代码。
- 决策：`quwoquan_service/runtime/servicekit` 的代码工程归属按 `quwoquan_service/runtime` 前缀归 [gateway-orchestrator-foundation](../../gateway-orchestrator-foundation/spec.md) L1（其工程归属段直接认领该路径），跨横切工程规范的设计裁决归本 DEC。反查路径为「代码路径查 gateway-orchestrator-foundation spec 工程归属、装配规范查本 DEC」，与 [DEC-022](#dec-022) 裁决 `runtime/auth` 的归属分离形态同型。
- 理由：进程级相位机与组合宿主已单轨存在，但 14 个 Go 服务的 bootstrap 各自复制身份解析（8 份）、env 校验（9 份字节级相同）、消息传输模板（13 份）、生命周期实现体（约 200–240 行 × 11 份）与观测/auth 装配（每服务 100+ 行）。样板漂移已经产生三种 config sync 签名与多处 magic 兜底，收敛到装配套件是消除第二真相源，不是新增抽象层。
- 理由：servicekit 不依赖 generated 产物才能保持「顶层 host 只消费薄 bootstrap、横切库不反向穿透服务内部」的既有方向；generated 输入以值对象传入使服务差异（domain 名、binding、rootID）留在唯一知道它们的 bootstrap。
- 被否决方案：继续逐服务复制样板，或把模块装配并入 servicehost——后者混淆进程相位与模块装配两种变更频率。
- 被否决方案：servicekit 直接 import `generated/operationsecurity`——突破依赖边界，形成横切库对 codegen 的反向耦合。
- 被否决方案：函数库装配形态下 `RegisterConfigSync` 由 Builder 隐式默认注册——该形态无统一入口字面量，隐式注册使 config ACK gate 的源码判据落空且副作用不可从 bootstrap 文本审计。声明式 Bootstrap 形态下的内置注册不在否决范围：`servicekit.Bootstrap(` 调用即审计锚点，注册必然性由其同包白盒测试锁定（[DEC-028](#dec-028)）。
- 被否决方案：把服务名单、依赖或物理地址放进配置中心热改（绕过不可变拓扑身份与整体回滚），以及保留代码 magic 兜底作为「本地便利」（隐性 fallback 违反 fail-closed，掩盖装配错误）。
- 约束与影响：`servicehost` 接口、相位语义、`composition.yaml` 模块集合与顺序、`cmd` 目录路径与二进制名、`CompositionDigest` 均不因本决策改变。存量 11 个核心服务 `cmd/api/main.go` 为 `package bootstrap` 且无 `func main()`，迁移时改名 `bootstrap.go`。`cmd/api` 目录语义为「api 模块组合包」，整体更名 `cmd/bootstrap` 待全部服务迁移后一次完成。
- 约束与影响：servicekit 构件的行为由同包 `*__local_contract_test.go` 白盒测试锁定（横切区旁路同包规则）。存储驱动（Mongo/Postgres/ES）不抽为**必选**构件，服务直连 `internal/platform` 始终合法；Mongo 提供可选场景构件供常规服务收敛样板（[DEC-028](#dec-028)）。env 命名历史差异不静默统一。
- 关联要求：`REQ-002`、`REQ-003`、`REQ-005`
- 关联验收：`SIT-002`、`SIT-003`、`SIT-005`

<a id="dec-028"></a>
### DEC-028 服务装配声明化：Bootstrap 骨架、env tag 覆盖引擎与可选场景构件

- 决策：servicekit 提供泛型声明式骨架 `Bootstrap(serviceName, BootstrapSpec[T])`，吸收装配样板全链：身份解析 → 快照加载 → env 覆盖 → 身份校验 → 观测栈 → auth 栈 → 基础设施自动装配 → HTTP 三件套 mux（healthz/metrics/operation guard）→ CORS 与服务级中间件钩子 → config sync 注册 → ConfigDigest 推导 → `ModuleSpec` 构造。服务侧只保留两件事：带声明的 config 结构体与 `Assemble` 领域回调（store/facade/worker 构造、路由注册、领域健康检查）。
- 决策：env 覆盖声明化为 config struct tag——叶子字段 `env:"<SUFFIX>"`、嵌套结构 `envPrefix:"<SEGMENT>"`，与服务前缀按 `<PREFIX>_<SEGMENT>_<SUFFIX>` 拼接为完整键。服务前缀默认从服务名派生：去 `-service` 后缀后 token 化（tag-service → TAG、circle-service → CIRCLE、realtime-gateway → REALTIME_GATEWAY），与部署面既有键名逐一吻合；`BootstrapSpec.EnvPrefix` 仅作为历史键名不合派生规则时的显式覆盖口。支持类型为 string、[]string（逗号分割）、bool（true/1/yes/on）、int，取值先 TrimSpace，空 env 不覆盖，未支持的字段类型 fail-closed 报错。手写 env 覆盖钩子随迁移删除，声明派生的键名必须与被删除钩子的键名逐一相等。
- 决策：`envAbsolute:"<KEY>"` tag 声明不带服务前缀的全局契约键，用于环境装配已把键名固定为无前缀形态的场景（如 `environments/<env>/config.yaml` 的 `secretRefs` 声明的 `MONGO_URI`）；同一字段同时声明 `env` 与 `envAbsolute` 即 fail-closed，一个字段只有一个键。
- 决策：`required:"true"` tag 承载必填校验，校验时机固定在 env 覆盖应用之后统一执行；缺失即启动失败，与 [DEC-027](#dec-027) 的无 magic 兜底裁决同向。
- 决策：入站 HTTP 观测标签（`Origin=service.http`、`Direction=inbound`、`SourceID`/`Src`=服务名）语义对所有服务相同，由 servicekit 观测栈统一填充，各服务不再重复声明；迁移不得让这些标签退化为空。
- 决策：认证能力按声明装配——`SkipDeviceTicketAuth` 声明本服务不提供设备票据认证，骨架不装配 verifier 也不要求其运行时配置在场；中间件对带设备票据的请求仍由 nil verifier fail-closed 拒绝，不是放行。声明了该能力却缺配置仍然启动失败。
- 决策：进程 trace 的 input/output KV 元数据脱敏由 `ObservabilityKVFilter` 声明，nil 表示原样记录；处理凭据、令牌一类敏感载荷的服务必须显式传入 filter（空策略 filter 即完全不记录 KV），迁移不得把已有的脱敏策略静默降级为原样记录。
- 决策：operation guard 的 boundary 策略由服务选择——默认 public boundary（`RequireGeneratedOperationAuthorization`），按 runtime boundary 判定的服务经 `BootstrapSpec.OperationGuard` 传入 `EnforceRuntimeOperationContract` 包装；骨架不替服务改判 boundary，迁移不得静默切换策略。
- 决策：`/healthz` 与 `/readyz` 语义分离且都由骨架统一挂载：`/healthz` 是浅层 liveness，恒 200，不触达任何依赖；`/readyz` 绑定 health checker，回答依赖与 worker 是否就绪。admission 门对两者与 `/metrics` 始终放行。把依赖检查放进 liveness 会让下游抖动升级为本服务重启。
- 决策：三个探针消费面各取所需，不追求同一路径。Kubernetes `readinessProbe` 取 `/readyz`（不就绪只摘流，不重启），`livenessProbe`/`startupProbe` 取 `/healthz`。Docker Compose 的 `healthcheck` 取 `/healthz`：compose 的 healthy 被其它服务 `depends_on: condition: service_healthy` 当作启动顺序门，探深层就绪会在 `start_period` 窗口内把整条启动链级联阻塞。环境编排的「就绪等待」与巡检取 `/readyz`——它要断言的正是依赖已连上，浅层探针会让后续步骤在依赖未就绪时开跑。
- 决策：部署面注入的 env 键必须有声明侧消费者，由 `cmd/service-core` 的对账测试同时校验 compose 与 prod plane 渲染脚本两条注入轨道。合法消费轨道三条：声明式 config 派生的覆盖键、服务 contracts `adapterContracts` 声明的 provider endpoint/secret 键（含尚未选中的备选 adapter）、仓库内 Go 源码字面量引用（如发布工具）。三条都无即判漂移——注入一个无人读的键不会报错，只会让服务带着渲染快照里的旧值起来。
- 决策：服务把某个 env 键声明为退役（注入即 fail-closed）之后，非 prod 的环境启动器——gamma mirror、beta 手工脚本、alpha content release runtime——也不得再注入它，由 `cmd/service-core` 的第三条对账测试静态校验。这三个启动器过去是对账盲区：它们与断言自己的测试互相自洽，键名与服务声明不一致时静态检查全绿，失效要到实跑该档位才显形。该判据只对带服务前缀的退役键成立，无前缀旧键凭键名分不出注入对象，不进入判据。
- 决策：指向具体存储实例的 env 键（Mongo/Postgres/Redis/Elasticsearch）必须带服务前缀，不得跨模块共享无前缀键。service-core 是单进程多模块，同进程模块读同一份 `os.Environ`：共享一个数据面键等于共享一个存储实例，且这种耦合不出现在任何配置文件里，换实例时会静默改变另一个模块。该不变量由 service-core 对账测试锁定。
- 决策：被调服务的出口地址（`<CALLEE>_SERVICE_BASE_URL`）是跨调用方共享的无前缀键——同一个被调服务对所有调用方是同一地址，与数据面键的实例私有语义相反，因此保留无前缀形态并在调用方 config 用 `envAbsolute` 声明。装配代码不得用 `os.Getenv` 裸读出口地址：裸读的键不进 `DeclaredEnvKeys`，注入键对账只能退到源码字面量兜底轨道，键名重命名时声明面无从发现消费者。下游 HTTP 客户端构造器各自 fail-closed 校验空值的义务不因声明而免除。
- 决策：治理 gate 识别装配点按源码内容特征，不按文件名。message transport 治理的装配点判据是「消费 message transport capability 的 generated binding 或声明 transport root」，`message_transport.go` 这个文件名不再是判据：声明化把 preflight 收进服务 `bootstrap.go` 后，按文件名判定会把合规装配误报为缺失，也会漏掉改了文件名的旁路实现。识别锚点限定在该 capability 自身，避免把其它 capability 的 binding 消费点与错误消息里的同名字面量误抓。
- 决策：服务脚手架（`quwoquan_ops/gate/scaffold/new_service.py`）生成的 `cmd/api/bootstrap.go` 直接是声明式形态——内嵌 `BaseConfig` 的 config 结构、`Bootstrap` 调用与 `Assemble` 回调，附 `DeclaredEnvKeys`；生成的 deploy 资产按上述探针分层写好。脚手架若继续产出手工拼装构件的样板，每个新服务都会把已删除的重复重新引入一次。
- 决策：config sync 由 Bootstrap 契约内置注册，其同包白盒测试锁定「调用 Bootstrap 必然注册 config sync worker 与 healthz 检查」；config ACK 治理 gate 的源码判据接受 `servicekit.Bootstrap(` 为合法形态。
- 决策：账号安全 authority 的配置段（`user_account_security_authority` 的 base_url/timeout_ms）是跨服务同构的标准段，归入 `BaseConfig`；服务侧只声明 `AuthorityScopes` 最小授权范围与 generated operation descriptors 两个平铺字段，auth 栈由骨架自动装配。
- 决策：基础设施构件按「声明即装配」自动发现——Bootstrap 反射扫描 config struct，发现 `MongoConfig` 字段（恰一个）即自动连接并暴露 `Assembly.MongoDB`（ping 健康检查与断连清理自动注册，多个声明 fail-closed 要求显式装配）；发现 `RedisSceneConfig` 字段即按其 yaml tag 收集为 scene 装配路由。一份 scene 配置需要装配成多个 codegen scene 名时（如 general/rec/realtime 共用同一物理连接），由 `BootstrapSpec.RedisScenes` 显式覆盖自动发现。服务直连 `internal/platform` 仍合法，未声明构件类型即不装配。
- 决策：Redis scene 的运行模式只由 `mode` 表达，不由地址在场与否推断，骨架对任何「声明与地址不成套」的组合在装配期判否而不是回落进程内存实现。四种判否形态是 `mode` 未声明、`standalone` 缺 `addr`、`cluster` 缺 `addrs`（含「只注入了单点 `addr`」这一部署面现实形态）、`memory` 与地址同时在场。最后一种是两处声明互相矛盾，挑任一处生效都会让另一处静默失效。静默回落的代价是多副本各自持有一份不共享、重启即丢的「Redis」，而幂等键、分布式锁与会话都建立在跨副本可见的前提上，且这类失效在运行期不产生任何信号。相应地，prod plane 的明文单点 Redis 由渲染器的单一写入口成套注入地址、组网与传输安全三项，只注入地址而漏掉组网降档等价于把单点地址当成集群种子。
- 决策：「本环境不接真实 Redis」由 `mode: memory` 表达，即把关停做成 `mode` 的第三个合法取值，而不是新增一个与 `mode` 正交的开关。正交开关会引入「开关关停但 mode 声明 cluster」这类需要额外裁决的组合，而 `mode` 本就是运行模式的唯一真相源；进程内存实现是一种运行模式，不是运行模式之外的旁路。代价是所有既有 scene 必须在四环境都有成套的地址注入或显式关停声明，缺失在装配期直接暴露。
- 被否决方案：保留「`standalone` 缺 `addr` 回落 memory」作为兼容路径——回落会让「漏了地址注入」与「有意不接 Redis」在运行期形状相同，而两者后果相反且前者无任何信号。判否的迁移成本是一次性的，静默回落的成本每次新增 scene 都要重付一遍。
- 决策：地址注入的成套性由 `quwoquan_ops/tests/local_contract/environment/test_redis_scene_address_provenance__local_contract_test.py` 在提交时判定，把装配期判否的暴露点从部署时提前：对每个服务实际装配的 scene 在四环境逐一要求「渲染快照有地址、该环境的注入源有地址、显式 `mode: memory`」三者至少其一。判定取四层取值后的渲染快照而不是服务快照原文，因为 `mode` 可以由跨服务默认层提供而根本不出现在服务文件里。scene 集合以 `RedisScenes` 钩子返回的 map 键为准、无钩子时取 struct 字段，两者都要覆盖：只认一种会让另一半服务以「跳过」的形式假绿，而 struct 里声明却不被钩子返回的 scene（integration 的 `rec`）不会被装配，要求它有地址会把判否指向错误的修复位置。注入源按环境分组，不分组会让某一档的注入替另一档背书。该门禁上线时实测到三处真实阻断：circle-service 四环境（键名改名后旧键无读取点）、content-service 的 prod `realtime`、search-service 的 prod `general`。
- 决策：scene 专属键一律带 scene 段（`CIRCLE_REDIS_GENERAL_ADDR`），不带 scene 段的 `<PREFIX>_REDIS_ADDR` 形状只保留给 rtc-service 的跨 scene 共享地址位。同一形状承载两种语义时读者无法从键名判断它给哪个 scene 供值，因此 circle-service 的旧键随改名进入 `RetiredEnvKeys` 而不是留作别名——留别名会让两种语义永久共存。
- 约束与影响：本 DEC 落地时 `mode` 仍以各服务 `config/schema.yaml` 的 `default: standalone` 兜底，那份默认值随后按 [DEC-029](#dec-029) 删除——schema 默认值同时是「本服务的物理拓扑」与「没想清楚时的占位」，前者本该逐环境声明。`mode` 的兜底声明位改为跨服务默认层（`quwoquan_ops/environments/config-defaults.yaml`），它仍是一处显式声明且对全部服务只写一遍，因此「所有既有 scene 必须在四环境有成套声明」这一代价不再需要 14 个服务逐一重复书写。
- 决策：ConfigDigest 回退链为 `CONFIG_VERSION` → 快照 `config.version` → operation descriptors 携带的 `ContractGraphSHA256`（generated 值经 descriptors 入参已进入 servicekit，不再要求服务单独传 digest 字段）；servicekit 依赖边界维持 [DEC-027](#dec-027) 的 `runtime/*` 与 `internal/platform/*` 不变。
- 决策：CORS 不由骨架默认挂载。`BootstrapSpec.CORS` 为 nil 表示不挂载 CORS 中间件，`OPTIONS` 按普通请求进入路由与 operation guard 由 ContractGraph 裁决；需要跨域面的服务显式声明策略（`servicekit.BrowserCORSFromEnv()` 保留 env 派生语义）。`WrapHandler` 钩子只承载真正特殊的服务级中间件。
- 决策：双形态并存且各自合法——Bootstrap 是常规 HTTP 服务的推荐路径；WebSocket 网关、边缘网关等特殊形态继续使用函数库构件自行装配，不强行套 Bootstrap。`BootstrapSpec` 提供 `WrapHandler` 钩子承载 CORS 之外的服务级中间件差异。
- 决策：进程入口形态按服务归属分两类，均消费同一 Bootstrap。service-core 组合成员的 `cmd/api` 是 `package bootstrap` 只导出 `NewModule`，进程壳在 `cmd/standalone-api`；独立进程服务（cloud artifact binding gate 的 Go 入口清单成员）保留 `cmd/api/main.go` 为 `package main`，`func main()` 只做 artifact 身份校验与 `servicekit.RunStandalone`，装配仍走 `Bootstrap`。两类都不再手写相位机与装配样板。
- 决策：账号安全 authority 允许「声明缺席」而非缺省装配——`SkipAccountSecurityAuthority` 声明本服务入站面不接受终端用户账号 principal（控制面服务只认运营台 OIDC 与机器凭据），骨架不装配 authority 客户端、不把它并入 `/readyz`；中间件对携带账号 principal 的请求由 deny-all gate fail-closed 拒绝，不是绕过账号状态检查放行。该声明与 `AuthorityScopes`、`user_account_security_authority.base_url` 互斥，同时给出即启动失败。缺席不声明仍然 fail-closed：无 base_url 即报错。无条件装配会让控制面为了自己就绪而反向依赖 user-service，并把「本服务无此依赖」持续报成依赖故障。
- 决策：配置中心自身**仍然**是自己的 config sync 客户端，不提供 `SkipConfigSync` 逃逸口。platform-ops 与其它受管服务同轨读取自己的有效配置并 ACK：prod rollout 的 `CONFIG_ACK_REQUIRED_INSTANCES` 把 platform-ops 实例算作收敛成员，关掉它等于让发布门禁永久不收敛。自举不成立——resolve 走进程内 HTTP 面，与外部客户端同一条路径，因此也顺带证明该面可用。
- 决策：实例报告与配置解析 scope 的 cluster 身份来源优先级为「服务显式声明 → 部署面注入的 `CLUSTER_NAME` → 按环境派生的 `<env>-control-a`」。prod rollout 渲染器按 `prod-<instance>-control-<replica>` 逐副本注入 `CLUSTER_NAME`，骨架忽略该注入会让全体副本在实例报告里自称同一 cluster，副本级漂移不可分辨。
- 决策：领域专属就绪子路由与骨架 `/readyz` 并存且语义不同——`/readyz` 回答「本实例依赖是否就绪」，`/readyz/config-convergence` 回答「本次发布的全体受管实例是否都已 ACK 当前配置」，后者是发布编排判据，挂为领域路由，两者不可互相替代。该子路由只返回 ready/not_ready，拓扑与 hash 详情仍需经 operator 授权接口读取。
- 决策：`RequireGeneratedOperationAuthorization` 的 default-deny 只对被 descriptors 表描述的入站面成立；未被该表收录、但有独立且更窄准入判据的路由必须显式挂到 `Assembly.Unguarded()` 并逐条写明判据，不得改回迁移期的「未匹配即透传」。platform-ops 的三条例外是：发布收敛探针（无凭据探测、只暴露 ready/not_ready）、`resolve-for-instance`（机器面 operation，未被运营台门户派生的描述符表收录，准入由 handler 自身的 service principal 与 env/service 绑定承担）、Alertmanager webhook（对侧只能携带静态机器 token，由专用 token 边界 fail-closed）。透传式 guard 会让任何新增未描述路由默认无鉴权。
- 决策：账号安全 authority 的**提供方**用 `SelfHostedAccountSecurityAuthority` 声明，语义与 `SkipAccountSecurityAuthority` 相反：入站面照常接受终端用户账号 principal，但裁决在本进程内完成。骨架不装配 HTTP 客户端也不登记远端就绪检查——指向自己的客户端会同时制造自调用与就绪自依赖。裁决点**不在认证中间件**：认证中间件位于 operation guard 之外，此刻 operation 上下文尚未写入，无法表达「已确认 closed 的账号重放某条 canonical 幂等终态命令仍返回成功」这类 operation 级豁免（`UserAccount.CloseAccount` 的 metadata 契约要求该语义）。因此自托管服务必须由领域装配经 `Assembly.Auth.ProvideInProcessAccountSecurityGate` 交出进程内裁决中间件，**挂载位置由骨架决定**——固定在 operation guard 内侧、领域路由之前。位置交给服务侧手工组装会让「挂错到 guard 外侧」这种错误只表现为某条幂等重放语义悄悄失效。
- 决策：自托管形态下认证中间件的 authority 面是 nil，而 `rtauth.Middleware` 对 nil authority 的行为是**跳过**账号安全检查，因此「声明自托管但未交出领域 gate」必须 fail-closed：否则被封禁与已注销账号将畅通无阻，且这种失效没有任何运行期信号。骨架在领域装配之后核对 gate 在场，缺席即启动失败；gate 只能提供一次，允许覆盖等于给同一裁决留两条轨。该声明与 `SkipAccountSecurityAuthority`、authority base_url、scopes 均互斥。
- 决策：`PreAdmissionPaths` 是 admission 门的唯一合法前置放行口，判据窄化为精确 `/internal/` 路径，不接受前缀式与通配（骨架 fail-closed 校验）。它的唯一正当用途是打破 service-core 单进程内的启动循环：同进程另一模块的就绪检查要调用本模块的内部端点，而本模块此刻尚未 `OpenAdmission`，双方互等即死锁。业务路由进入该清单等于在就绪之前接受真实流量，因此不允许。
- 决策：认证中间件的内外两侧都有声明位且职责不同。`WrapHandler` 在认证**内侧**（principal 已解析）；`WrapOutsideAuth` 在认证**外侧**，承载必须看到原始入站报文的关注点（网关的凭据中继）——认证会把原始凭据头换成已解析的 principal 上下文。外侧不等于绕过认证：认证仍在其内侧执行，它只是先于认证观察请求。
- 决策：`OperationGuard` 回调收进程身份并允许返回错误（`func(identity Identity) (func(http.Handler) http.Handler, error)`）。按环境分档的 boundary（`rtauth.OperationAuthorizationForRuntime`）需要 env 且构造可失败，构造失败或返回 nil middleware 一律阻止启动，不得退化成无 guard。
- 决策：CORS 是入站面策略而非通用启动样板，因此默认不挂载，由需要它的服务在 `BootstrapSpec.CORS` 显式声明。判据是 `rthttp.WithCORS` 对 `OPTIONS` 的短路不看 options：无论策略取什么值都无条件返回 204，且该响应在观测栈、operation guard、共享准入之外写出，默认挂载等于给每个服务凭空加一个未认证、不计量、可探测的请求面。只有承载浏览器直连入站面的服务声明跨域策略（`chat-service` 的媒体面、`product-ops-service` 的运营台、`tag-service`）；其余服务包括全站唯一对外业务入口 `api-edge` 的 `OPTIONS` 语义是由 ContractGraph 裁决为 `route_not_found`。跨域面集合由 `cmd/service-core` 的 local_contract 锁定，新增声明必须同时给出该服务接受浏览器跨域直连的理由。
- 被否决方案：默认挂载 CORS 并提供 `DisableCORS bool` 关闭位——默认值决定了「忘记声明」的后果，而此处忘记声明的后果是多一个对外可探测面，方向应当是默认关闭而非默认开放。
- 决策：`Workers.AddFallible` 承载「启动动作本身可失败」的 worker，在 Start 相位同步执行，失败即让 Start 失败。把这类失败降级成健康检查会让失败时机推迟到 Ready 窗口，也让「拉起失败」与「运行中故障」共用同一个信号。长跑循环体仍用 `Workers.Add`。
- 决策：生效配置快照路径由骨架写入 `BaseConfig.ConfigPath`，与 `BaseConfig.Environment` 同机制。需要按快照来源分档校验的领域钩子读它，而不是各自重算一遍 configrelease 选路——重算会形成第二套选路规则。
- 决策：servicekit 不直接导入存储驱动。`runtime/**` 公共层禁止直连驱动（`verify_service_layering`），但连接句柄必须能穿过公共层交到服务侧，因此驱动包只在 `internal/platform/{mongodb,postgres}` 被导入，句柄以平台层类型别名对外（`rtmongo.Database`、`rtpostgres.Pool`），生命周期以不含驱动类型的接口对外（`rtmongo.Handle`）。平台层同时区分「DSN 非法」与「连接失败」（`rtpostgres.ErrInvalidDSN`）：两者运维处置相反，前者重试无用，后者可能只是依赖尚未就绪，合并成一条错误会丢掉这个判断。
- 理由：完成 [DEC-027](#dec-027) 迁移后的服务 bootstrap 仍余约 130 行跨服务字节级重复（生命周期序言、手写 env 覆盖、Mongo 装配、HTTP 骨架、digest fallback），继续手抄将随服务数线性放大漂移面；声明化把「每服务手抄」变为「一处实现 + 同包白盒锁定」。
- 被否决方案：env 键按 yaml 路径全隐式派生——键名不再显式出现在源码中，无法 grep、来源不可审计，违反配置来源单义。
- 被否决方案：把特殊形态服务强行套 Bootstrap——网关的 handler 组合与常规服务不同构，强套会让骨架长出逃逸参数簇，形成第二套装配语义。
- 被否决方案：为 `ValidateConfig` 增加 `identity` 与 `configPath` 形参——该钩子已有八个使用者，其中绝大多数不需要这两项，改签名的代价全部落在无关服务上；改为由骨架写入 `BaseConfig` 字段，钩子按需读取。
- 被否决方案：让 authority 提供方装配一个指向自身入站面的 HTTP 客户端——它会把「本服务是否就绪」变成「本服务是否已就绪」的自指判断，并在进程内绕一圈网络栈做本可直调的裁决。
- 被否决方案：把自托管服务的进程内裁决面注入认证中间件的 `AccountSecurityAuthority` 字段——该位置在 operation guard 之外，裁决时拿不到 operation 上下文，`CloseAccount` 的幂等重放语义会被 `closed` 判否直接吃掉。
- 被否决方案：改用 `rtauth.MiddlewareConfig.AccountSecurityExemption` 在认证层表达豁免、退役对象级 gate——豁免判据要从 canonical operation 退化为 method+path 字面量，错误面也要从对象 `errors.yaml` 生成的构造器改为 runtime 硬编码构造器，`USER.AUTH.*` 的用户文案由此出现第二个真相源。
- 约束与影响：Bootstrap、env 引擎与 Mongo 构件的行为由 servicekit 同包 `*__local_contract_test.go` 白盒锁定；真实 Mongo 连接路径不进白盒（连接器以同包 typed double 注入且不出测试树），由服务 api_integration 层承载。迁移服务须新增 env 键全集等价断言（声明派生键与被删除的手写键逐一相等）。
- 关联要求：`REQ-002`、`REQ-003`、`REQ-005`
- 关联验收：`SIT-002`、`SIT-003`、`SIT-005`

<a id="dec-029"></a>
### DEC-029 判定语义只来自显式声明，值的在场与形态不构成声明

- 决策：任何决定行为分支的语义只能读显式声明位，不得读「某个值在不在场」或「某个值长什么样」。判据是一句可回答的话：**这个分支读的是「有人写下的取值」，还是「某个值恰好是/不是某种形状」**。后者一律改为前者，改不动就判否退出，不得留在运行期。本决策的效力范围是全仓 Go/Dart/Python 与配置渲染面，不限于服务装配。
- 决策：「不启用」「不接真实依赖」是取值的一个合法枚举值，不是取值的缺席。Redis 的进程内存实现由 `mode: memory` 表达（[DEC-028](#dec-028)），不由「没注入地址」表达；ES 的启用只由 `SEARCH_ES_ENABLED` 表达，不由 `SEARCH_ES_ENDPOINTS` 在场翻转。地址或端点在场只说明有人注入了一个地址，它同时兼容「本环境要接」与「注入错了地方」两种相反事实，而按前者静默处理的失效在运行期不产生任何信号。
- 决策：显式声明的代价由**分层默认**承担，不由放宽判据承担。配置取值优先级固定为「服务 `environments/<env>/config.yaml` override → 环境级跨服务默认 → 全局跨服务默认（`quwoquan_ops/environments/config-defaults.yaml`）→ 服务 `config/schema.yaml` 的 `default`」，四层每一层都是显式声明，任一生效值都能指回一处写下它的文件。分层默认只提供**取值**，不定义键：键的存在性、类型与 `sensitive` 仍只由本服务 schema 声明（[REQ-003](spec.md#req-003)），跨服务默认按键 pattern 匹配，未命中本服务 schema 声明的键时该键不进入快照——pattern 是跨全部服务的宽匹配，「本服务没有这个键」是常态而非缺陷，命中后的取值仍要过本服务 schema 的类型校验。`sensitive` 键不得由跨服务默认提供，它只能走 secretRef——凭据的注入归属必须逐服务逐环境可查，共享一处默认恰好抹掉这个归属。
- 决策：一段配置的复用只允许「整段缺席即复用另一段」这一条规则，禁止字段级回落。判定由 `IsUndeclared()` 承担（该段每个字段都未被声明过），复用后的整段仍要过原有校验。字段级回落会把 `realtime` 的 mode 与 `general` 的地址拼成一份没人声明过的配置，出问题时没有任何一个文件能解释生效值；整段复用的规则写在装配处、只有一条，读者能一眼看出这个段的每个字段都来自哪里。
- 决策：URI scheme 不是「值的形态」而是 URI 契约的一部分，读它是解析声明。OTLP endpoint 的 `http://` / `https://` 决定 trace 是否加密传输，缺 scheme 判否；注入面必须写出 scheme。改之前的判据是 `HasPrefix(endpoint, "https")`，而 `WithEndpoint` 收的是 `host:port`、注入面给的也是 `host:port`，那个前缀永远不成立——明文是唯一可达分支，且没有任何信号说明加密从未生效。同型豁免适用于 `unix://`、`rediss://` 一类由协议契约定义的 scheme。
- 决策：判否必须止于装配，不得降级为 no-op。`otel.MustInit` 对非法 exporter 声明改为 panic：只记一条 error 再返回空 provider 会让服务带着「无 trace」运行，而无 trace 与安静服务在外部看起来完全一样。同理，校验函数的返回值不得被调用方丢弃——吞掉 error 会让装配期判否退化成注释里的承诺。
- 决策：判否文本描述**缺的那处声明或注入键**，不描述症状。触发这类判否的现实场景是「环境装配注入了单点 addr 却没覆盖 cluster 声明」，读者此刻需要知道该改哪个文件、写哪个键，而不是「invalid config」。判否文本同时给出合法出路（含「声明 `mode: memory` 表示本环境不接」这条关停路径）。
- 理由：隐式语义的成本不对称。声明缺失被静默按「默认关停」处理时，多副本各自持有一份不共享、重启即丢的实现，而幂等键、分布式锁与会话都建立在跨副本可见的前提上；反向的判否成本只是一次性的配置补齐。同一份代码同时服务四个环境时，「按值的形态猜环境意图」必然在某个环境上猜错，而猜错的那个环境通常是最少被实跑的 prod。
- 约束：本决策不禁止默认值，只禁止**没有声明位的**默认值。schema `default`、分层默认与代码内的常量上限都是显式声明；被禁止的是「读不到值就自己决定语义」。
- 约束：`try` 前缀解析器返回 `null` 表达形状判定结果的既有豁免不受影响，它由 [DEC-025](#dec-025) 拥有；本决策管「判定语义从哪来」，DEC-025 管「结果状态怎么表达」，两者不重叠也不互相豁免。
- 被否决方案：为每处推断补注释说明其意图。注释不改变运行期行为，下一次注入错误仍然静默。
- 被否决方案：把 `standalone` 缺地址回落 memory 保留为兼容路径，见 [DEC-028](#dec-028) 的同名否决。
- 被否决方案：用一个与 `mode` 正交的 `enabled` 开关表达关停。它会引入「开关关停但 mode 声明 cluster」这类需要额外裁决的组合，而关停本就是运行模式的一个取值。
- 被否决方案：允许字段级 scene 回落以减少配置行数。少写的那几行换来的是生效值不可追溯。
- 被否决方案：给跨服务默认开 `sensitive` 例外以少写几处 secretRef。凭据的注入归属必须逐服务逐环境可查，共享一处默认恰好抹掉这个归属。
- 影响 Story：[`explicit-semantics-no-implicit-inference`](./explicit-semantics-no-implicit-inference/spec.md) 承接唯一判据、分层默认声明位、整段复用规则、scheme 豁免与判否文本要求。
- 关联要求：`REQ-002`、`REQ-003`
- 关联验收：`SIT-002`、`SIT-003`

<a id="dec-030"></a>
### DEC-030 模型属性的取值语义只来自契约声明，闭集在每条消费管线上类型化

- 决策：闭集的类型化必须传播到每一条消费管线，不止于契约与生成物。契约以 `type: enum` 加 `enum_ref` 声明的属性，在服务侧领域模型、跨对象读端口的 slice、投影行与端侧模型上都必须是该闭集的类型；判定与具名常量比较，不与字符串字面量比较，也不以大小写不敏感比较放宽值域。类型只落在契约与生成物、消费点仍是裸字符串时，闭集实际上不存在：`strings.EqualFold(status, "deleted")` 同时接受契约从未声明的 `Deleted` 与 `DELETED`，而它下一行就能接受一个契约里根本没有的取值而不被任何检查拦住。
- 决策：四种输入形态各自独立判定，不得合并成一个「缺席」分支。**闭集零值**不是合法取值——契约声明 `NOT_NULL` 的枚举属性，其语言零值不在闭集内，必须与不合法取值同路判否，不得为零值单开放行分支。**宿主对象缺席**时不产出属性级判定——对象整体不在场时取属性默认值继续判定，等于把「数据还没到」判成一个具体的业务事实。**闭集外入站取值**必须落到显式声明的未知成员，且该成员不得等价于任何放行态。**契约未声明的取值**不得出现在判定分支里，这类分支是死分支，删除而不是保留为兼容。这四种形态的后果互不相同，写成一个词会让「断言的输入根本到不了被测分支」这类问题在规格层就不可见。
- 决策：一个业务语义只有一个可写载体。判定不得把两个载体用逻辑或合并——`!DeletedAt.IsZero() || status == "deleted"` 在任一载体单独失真时都仍然成立，因此两者的不一致永远不可见。已存在伴随载体时派生方向单一：权威载体写入后由同一次事务派生伴随载体，伴随载体不得被独立写入也不得反向决定权威载体。读侧归并展示取值时，归并结果必须是显式声明的展示态成员，且语义相反的两个取值不得归并到同一个成员——把 `rejected` 与 `pending_review` 一起显示成「审核中」不是简化，是告诉用户一件不成立的事。
- 决策：默认值是纯写侧概念，读侧只翻译不发明。默认值的声明位唯一，在写入时一次性物化为显式取值，物化后与任何其他显式取值不可区分；因此读侧不存在「默认态」这个状态。读侧为缺席属性填入默认值会制造一个写侧从未声明过的取值，且该取值无法指回任何一处声明。测试替身受同一约束：替身为被测属性补默认值时，断言绿在替身上而不是被测规则上，而这种假绿在替身与被测代码同时演进时不产生任何信号。
- 决策：判否收缩用户可见路径时，终态与恢复动作是该判否的一部分，不是后续工作。本决策把若干「原来能看、能点」改成「不能看、不能点」，而收缩本身不产生终态：宿主对象缺席期间的渲染态与「加载已结束但对象仍缺席」是两个必须分别可达的终态，后者不得以失败对象在场为前提。闭集外取值的终态文案不得复用断言性措辞——把「本端未声明该取值」说成「内容已被删除」，会把客户端版本落后谎报成内容发生了变化。判否而不给终态，会把一个静默的错误答案换成一个静默的死路，用户的处境并没有变好。
- 决策：本决策与相邻决策的分工按「声明位」和「判定对象」划开，不按现象划开。[DEC-029](#dec-029) 与本决策共用「判定只读显式声明」这一句判据，但声明位不同：那边是 config schema 键与 env 键，这边是对象契约的字段与枚举成员；同一句判据在两个平面各有自己的合法形态与豁免，合成一个 DEC 会让 Redis `mode` 的分层默认与属性闭集的类型化互相污染。[DEC-025](#dec-025) 管一次返回如何表达其结果状态，本决策管属性取值凭什么进入判定分支：前者的四态是返回值的形态，后者的四形态是输入的来源，`status` 取零值时 DEC-025 无话可说而本决策判否。[DEC-007](#dec-007) 拥有删除语义的三层 owner 与保留期，本决策只要求删除态不被第二个载体独立表达，不改判其 owner。[DEC-014](#dec-014) 裁定读投影值域可宽于写侧闭集，本决策不收窄它，只要求宽出来的取值同样是显式声明的成员而不是就地发明的字面量。
- 理由：判定语义的显式化在配置面已由 [DEC-029](#dec-029) 落地，而模型属性面的失效形态更隐蔽且更贴近用户。配置面的隐式推断在装配期一次暴露，属性面的隐式推断每次请求都发生一次且各自看起来正常：会话状态取零值时授权门放行、圈子详情未到达时按公开渲染、分享目标状态未知时按可打开渲染——三处都不产生任何错误信号，都要等用户撞上才显形。三者的共同形状是「取值没有落在闭集里，于是代码替它选了一个」，而代码选的总是最宽松的那个。
- 约束：证据层按判定的可观察位置分层，不按改动所在的目录分层。授权门的零值判否经导出命令观察，属 `local_contract`。服务侧 `internal/**` 不适用旁路同包测试，因此不得为可测性把授权门改成导出符号。渲染态与终态的可达性经 Widget 观察，属 `local_contract`。入站取值到未知成员的映射必须经公开工厂观察并绕开测试替身的补值，同属 `local_contract`。存储适配器的查询谓词只存在于发给存储的 filter 里，`local_contract` 只能断言被抽为导出构造函数的谓词，真实存储行为归 `api_integration`——用注入替身证明适配器的过滤，证明的是消费方而不是适配器自身。
- 约束：本决策的门禁不得依赖豁免名单或存量基线文件成立。契约里「为空表示 X」形态的声明存在三类，判据必须分开：分页游标的「空表示无更多数据」是协议定义的终止信号、可选引用的「为空即无关联」是缺席本义、而「为空表示待投递」「为空表示继承默认」「为空表示全部维度」才是被缺席承载的业务状态。只判第一层文本形态会对前两类产出压倒性误报并很快被绕过。门禁自证必须双向——对新增违规样本变红，且对既有合规样本不误报；只测变红时，判据与合法文本在语法上同形这一事实不会被发现。
- 被否决方案：把本决策并入 [DEC-029](#dec-029)。两者判据同源但声明位与合法形态不同，合并后 Redis `mode` 的四层分层默认会与属性闭集的类型化传播共用一段约束，而分层默认恰恰是本决策在读侧禁止的形态——配置取值允许四层回落且每层都是声明，属性取值不允许读侧回落。
- 被否决方案：为闭集外取值保留「映射到最宽松成员」作为兼容路径。它让「服务端新增了取值」与「本端解析错了」在运行期形状相同，而前者应当收缩、后者应当报错，两者都不该表现为放行。
- 被否决方案：先批量把裸字符串消费点替换为具名常量，再逐服务开启 typed enum。批量替换不会让任何一处编译失败，因此漏掉的消费点无信号；开启 typed enum 让全部裸字符串消费点编译失败，编译错误就是逐点裁决的导航。
- 被否决方案：把「宿主对象缺席」并入「属性缺席」统一处理。两者的修复位置不同：属性缺席在解码与契约声明处修，宿主对象缺席在调用方的加载态与终态处修；并入后修复会一律落到属性侧，而缺的那个终态永远不会出现。
- 约束与影响：服务侧 typed enum 生成能力已存在但只有一个服务的生成器调用它，因此本决策的 `REQ-001` 在其余服务上按 Story `OPEN-001` 承载。共享闭集的简写列表形态无法声明未知成员的 wire 语义，按 `OPEN-002` 承载。多载体与默认值多轨的存量逐处裁决按 `OPEN-003` 承载，全仓静态门禁按 `OPEN-004` 承载。四笔都不进中央台账，随各自完成判定关闭。
- 影响 Story：[`model-attribute-semantics`](./model-attribute-semantics/spec.md) 承接类型化传播、四形态独立判定、单一可写载体、写侧默认物化与收缩路径终态。
- 关联要求：`REQ-001`、`REQ-002`
- 关联验收：`SIT-001`、`SIT-002`

<a id="dec-031"></a>
### DEC-031 代码健康只阻断增量新债，存量按热点收敛，AI 不拥有准出

- 决策：代码健康事实由 `quwoquan_ops/policies/code_health_policy.yaml` 与 `make verify-code-health-delta` 单轨拥有。delta 复用 canonical impact planner 的 exact base/head 与 changed paths，并以 EvidenceFingerprint 绑定 candidate 字节、policy、命令和 toolchain；不得建立第二 impact registry、扫描结果台账或路径 allowlist。
- 决策：source path 必须互斥落入 `handwritten-production`、`test`、`generated`、`vendor`、`contract-metadata`、`config-data`、`docs` 七类之一。总代码量只作容量与趋势观测；generated/vendor 由重生成与供应链门负责，不进入复杂度、重复和认知预算判罚；测试独立报告且模板式重复默认不阻断。
- 决策：首日只阻断可机械证明的新增/恶化项：手写生产文件新越过 2000 行、既有超限继续上升、明确新增且无语言或仓库入口的 private Python module，以及 tracked 源码树可执行构建产物。复杂度、片段重复与 1000 行 advisory 在至少 14 天或 20 个 PR、confirmed false-positive 不高于 10% 前保持 `PR_WARN`；策略不得自动升格。文件规模只有这一套阈值：Python 脚本治理等其他门不得维护第二套行数预算、路径 allowlist 或机器派生豁免。
- 决策：L0 只运行无需安装且 p95 不超过 30 秒的 changed-file 快判（staged 对 HEAD）；L1/L2 与 `make verify-code-health-delta` 以 HEAD 与 dev1.0 的 merge-base 为 base 执行完整 delta，让已提交的 lane 分歧同样进入判罚，缺少 dev1.0 引用时 fail-closed；hosted `code-health-integration` 对每次 dev1.0 快进的 exact before/after 复算并发布 report-only OCI fact（5 分钟超时），是否成为 promotion required evidence 归交付链 owner；每周任务执行全仓 report-only 增长与 `change-frequency × health` 热点，以 OCI fact 保存历史、对照上期给出棘轮方向与 hotspot 连续在榜周数，不阻断 PR、不提交 snapshot。
- 决策：确定性检查唯一拥有 `PASS / PR_WARN / GATE_BLOCK`，terminal 由 engine 代码与 policy 阈值决定，policy 的 `notes` 只是文档、不含任何开关。Agent PRE 与 plan-next 只经 `make code-health-hotspots OWNER=<scope>` 加载目标 owner 的阈值、热点与薄弱点，连续两期在榜且可行动的热点才进入最低 owner OPEN；POST 产出 current receipt 并以同一 Markdown 投影展示 blocker、recovery 与债务 delta；Reviewer 与 AI advisory 只消费脱敏命名证据，不重跑、不改写 terminal、不自动改 baseline。重复坏味道只有在存在第二个独立实例时才进入 distill。
- 理由：当前 351 万 source LOC 中测试、generated 与 vendor 超过一半，总代码量与原始 churn 会把可再生和验证资产误判为维护债；同时单次大规模 sync 已超出人和 Agent 的认知窗口。增量判罚把成本放到引入问题的 candidate，热点排序使存量治理集中在高变更且低健康的代码。硬顶从 1000 放宽到 2000 的依据：37 个 >1000 行的手写生产存量中 33 个介于 1000–2000，20 个历史 merge 样本中 8 个因新越过 1000 行被阻断且全部是发布链拆分未完成的过渡态；2000 以上仍冻结增长，1000–2000 区间的数量与总超出行数进入 weekly 棘轮观测，因此放宽不等于放弃约束。
- 被否决方案：部署 SonarQube/CodeScene 常驻平台、全仓存量门一次阻断、以 LOC 或 commit 数评价 Agent、为误报增加 per-file waiver，以及让模型输出 gateStatus。它们分别引入额外状态源、使无关 PR 陪葬、激励错误行为或把准出交给不可复现判断。
- 约束与影响：大迁移只有在混入无关 owner/目的、无法绑定唯一验收切片或无法独立测试时才以 `CANDIDATE.SPLIT_REQUIRED` 阻断；纯删除、codegen、fixture regeneration 与机械 rename 单列。误报只能修分类器/规则并以 `superseded_measure` 留下旧口径实测，不能豁免路径。
- 失败与恢复：policy、Git range、工具身份或 candidate 字节不完整时 fail-closed 且不写 PASS；外部分析器缺失时只将对应 advisory 指标标记 unavailable，不得吞掉首日 blocker。误报率、耗时或交付失败率超标时回退该规则的 enforcement 到 advisory，但保留观测。
- 观测：记录 delta p95、confirmed false-positive、Agent 修复轮次、手写 churn、Top 20 hotspot、Delivery calendar critical path、change failure/recovery/rework；Delivery 关键路径增长超过 5% 或 60 秒、交付 lead time/失败率恶化超过 10% 时触发 rollout 回退。
- 适用工程根：`quwoquan_ops/policies/code_health_policy.yaml`、`quwoquan_ops/gate/code_health_delta`、`quwoquan_ops/gate/verify_incremental_code_health.py`、`quwoquan_ops/tests/local_contract/gate/test_incremental_code_health__gate__local_contract_test.py`、`quwoquan_ops/gate/run_code_health_calibration.py`、`quwoquan_ops/gate/report_code_health_weekly.py`、`quwoquan_ops/gate/report_code_health_hotspots.py`、`quwoquan_ops/ci/verify_code_health_integration.py`、`quwoquan_ops/ci/code_health_evidence.py`、`.github/workflows/code-health-integration.yml`、`.github/workflows/code-health-weekly.yml`
- 关联要求：`REQ-001`、`REQ-002`、`REQ-003`
- 影响 Story：[`incremental-code-health-governance`](./incremental-code-health-governance/spec.md)
- 关联验收：`GWT-001`、`GWT-002`、`GWT-003`

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
