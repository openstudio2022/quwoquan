# L3 Story：服务本地契约目录 (`metadata-domain-restructure`)

> 所属能力：[`content-service-contract-foundation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望把业务域契约归入所属服务 contracts，仅保留跨服务共享 schema 在中心 metadata，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “服务本地契约目录”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 服务本地契约目录

- 把业务域契约归入所属服务 contracts，仅保留跨服务共享 schema 在中心 metadata。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 服务本地契约目录

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“服务本地契约目录”对应的公开行为。
- THEN 把业务域契约归入所属服务 contracts，仅保留跨服务共享 schema 在中心 metadata。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-service-contract-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-002"></a>
### OPEN-002 Post 聚合根仍有十个弱类型值对象

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前模型重构已完成，但尚缺 content-service 对应 API integration、候选绑定的真实发布读回 UAT、四环境 SLI/SLO 与回滚证据，因此不得提前认定商用 READY。`Post` 十个弱类型字段已迁移为 metadata-owned 具名值对象，Go 聚合、导入器、Mongo 读写、公开 projection 与 App codegen 已单轨消费，旧 `mediaItems` 写入键和 `aggregateRootBareObjectAllowlist` 对应项已删除，定向生成、静态分析与 60 个 App local_contract 已通过。
- 完成判定：十个字段全部迁移为 metadata-owned 具名值对象后 `GWT-001` 的契约归属口径在 `Post` 上成立——Go 聚合、导入器、Mongo 读写、公开 projection 与 App codegen 消费同一单轨类型；删除 `aggregateRootBareObjectAllowlist` 对应项并通过 `make verify-metadata`、content local_contract/api_integration 与发布回读 UAT。
- 依赖：Post 发布、release importer 与 Work Browser projection 同步迁移。

<a id="open-001"></a>
### OPEN-001 服务本地契约目录 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“服务本地契约目录”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
