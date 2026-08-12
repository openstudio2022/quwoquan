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
- 公共 migration/template/policy/static/model 位于 `resources/`。Skill package 的受控发布源码固定为 `resources/skill_packages/official`，已构建且供运行时按 active release digest 读取的 immutable asset 固定为 `resources/skills/packages/official`。两者必须是互不链接的物理根，禁止运行时扫描源码或保留 fallback。环境只选择 Data release、artifact digest 与 Provider binding。“同源”只表示相同 publish/release/importer/contract/readback，绝不复制 Prod 数据库。Creator 属于 release 内容身份而不是登录 Actor，非生产 Actor 与交易数据由所属领域公开 command/event 在候选验证期产生。
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
- 关联要求：服务自治与目录反向映射对应 `REQ-001`、`REQ-002`
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
- 约束：领域业务 seed job 数量为零；Data 大制品只通过 `releaseRef + digest` 绑定，Alpha/Beta/Gamma 验收数据只由 `stackctl verify` 经公开 command/event 创建。
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
- 影响 Story：[`app-cloud-business-object-commercial-closure`](./app-cloud-business-object-commercial-closure/spec.md) 的 `OPEN-013` 据本条更新声明位。
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
- 关联要求：`REQ-001`、`REQ-002`
- 关联验收：`SIT-001`

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
