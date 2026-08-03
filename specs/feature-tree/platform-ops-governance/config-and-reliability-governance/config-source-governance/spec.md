# L3 Story：配置来源治理 (`config-source-governance`)

> 所属能力：[`config-and-reliability-governance`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为平台运维、安全或审核角色，
我希望系统必须由 config schema 与单个环境 overlay 合成服务有效配置，并以 revision 与摘要识别发布内容，且失败时不得写入成功事实，
从而获得可审计且可回滚的平台治理结果。

## 2. 范围与非目标

### In Scope

- “配置来源治理”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 配置来源治理

- 系统必须由 config schema 与单个环境 overlay 合成服务有效配置，并以 revision 与摘要识别发布内容，且失败时不得写入成功事实。

<a id="req-002"></a>
### REQ-002 配置合成、发布标识与失败原子性

- 系统必须由 config schema 与单个环境 overlay 合成服务有效配置，并以 revision 与摘要识别发布内容，且失败时不得写入成功事实。
- APP_ENV 与 CONFIG_VERSION 能支撑灰度范围、回滚点和发布证据追踪。
- 服务配置不得声明镜像最低/最高版本或任何兼容范围；每个运行实例只能绑定部署包提供的一份精确不可变镜像身份，缺失、可变占位或与部署证据不一致时必须在启动或发布门禁中失败。
- 本地 workload、Data 执行控制面及调试依赖的 host 端口都必须引用同一个 `local_env_port_manifest.yaml` 中互不重叠的 role；独立控制面不得借用 Alpha、Beta、Gamma 环境 workload 的 MongoDB、Redis 或 Elasticsearch role。
- `stackctl down` 只能撤销目标拥有的容器、隧道和 lease；检测到外部占用时必须保留证据并失败，不得通过重启 Docker、Colima 或其它共享运行时抢占资源。

<a id="req-003"></a>
### REQ-003 搜索存储配置来源

- 搜索存储连接配置 `es.enabled`、`es.endpoints` 与 `es.insecureTls` 由统一搜索索引写侧消费，覆盖内容、圈子、实体与用户对象。
- 高风险变更必须走灰度，不允许全量直发。
- 配置变更必须有版本号（CONFIG_VERSION）与审计记录。
- 回滚目标版本必须存在且通过记录验证。

## 4. 契约引用

- canonical：`APP_ENV`
- canonical：`CONFIG_VERSION`
- canonical：部署包绑定的不可变镜像身份

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 配置来源治理

- GIVEN 平台运维、安全或审核角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“配置来源治理”对应的公开行为。
- THEN 系统必须由 config schema 与单个环境 overlay 合成服务有效配置，并以 revision 与摘要识别发布内容，且失败时不得写入成功事实。
- AND 镜像身份只来自同一部署包的精确 digest/ref，不接受 SemVer 范围、兼容推断、缺省身份或本地绕过。
- AND 本地端口均由唯一 port manifest 分配且跨 workload 不重叠；目标 `down` 不停止或重启共享容器运行时。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`config-and-reliability-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 配置来源治理 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“配置来源治理”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
