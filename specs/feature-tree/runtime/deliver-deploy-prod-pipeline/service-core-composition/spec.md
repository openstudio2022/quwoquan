# L3 Story：Service Core 组合部署 (`service-core-composition`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为环境运行与发布角色，我希望以一个可验证、可整体回滚的 Go `service-core`
部署单元承载稳定的核心服务集合，同时保留领域边界、公开契约和独立的长连接/模型故障域，
从而在不改变端云行为的前提下减少部署开销并建立可重复的三环境稳定性结论。

## 2. 范围与非目标

### In Scope

- `api-edge`、`assistant-service`、`chat-service`、`circle-service`、`content-service`、
  `entity-service`、`integration-service`、`notification-service`、`search-service`、
  `tag-service` 与 `user-service` 的单进程组合部署。
- 原 HTTP route、服务 hostname、端口、契约 owner、数据源、迁移、错误和可观测身份保持不变。
- `test_live` 与 immutable candidate 的同构 `service-core` 制品、整体切换与精确回滚。
- 按 module 归因的健康、资源公平性、故障恢复和三环境验收证据。

### Out of Scope

- 合并业务领域、服务 contracts、数据库、迁移所有权或跨服务调用语义。
- 将 Python `recommendation-service`、`realtime-gateway`、`rtc-service`、`product-ops-service`
  或 `platform-ops-service` 纳入 `service-core`。
- 在同一环境同时运行 split-services 与 `service-core`，或以运行时 feature flag 在两者间切换。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Service Core 保持服务语义与独立故障归因

- `service-core` 只组合进程、镜像和部署单元；每个 module 仍保留原服务 identity、公开
  hostname/port/route、generated contract、数据源和 migration owner。
- module 间仍经原公开 HTTP/WS 契约协作；禁止 host 或 module 通过跨服务私有 import、
  共享业务 store 或进程内业务直调绕过鉴权、错误 mapper 或 trace。
- host 在任何 listener admission 前完成全部 module 的配置、secret scope、端口、迁移 ownership
  与依赖校验；任一 required module 无法达到 ready 时 aggregate readiness fail-closed。
- Python Recommendation 与 Realtime/RTC 保持独立进程和故障域；Search 在 `service-core`
  内仍独立拥有 Elasticsearch client、索引消费和 unavailable 语义。

<a id="req-002"></a>
### REQ-002 Service Core 候选、切换与回滚保持单轨

- `test_live` 从当前工作树构建不可晋级的 `service-core` 开发制品；immutable candidate
  从 input capsule 构建同一 topology，并绑定精确 OCI、SBOM、provenance、module、
  config 与 migration digest。
- 环境 workload、Compose/Podman projection、package、health、inspect、CI 和 Green Matrix
  从同一服务自治部署输入生成 `service-core` composition；不得维护手写第二份 module registry。
- 同一 target 的切换是整体的：新候选不含原 11 个独立核心服务 workload；回滚只启动上一份
  immutable split-services 或 `service-core` candidate 的精确 bytes，且两种 topology 不并存。
- 每个 module 继续以独立 `service.name`、module、operation、candidate 与 trace identity
  输出观测；资源、panic、migration 或 shutdown 失败可定位并不产生半活成功事实。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 环境运行时与打包：[`environment-topology-and-packaging`](../../runtime-config/environment-topology-and-packaging/spec.md)。
- 环境隔离与启动事务：[`multi-environment-instance-isolation`](../multi-environment-instance-isolation/spec.md)。
- 服务自治与三层测试：[`system-architecture-and-engineering-guide`](../../system-architecture-and-engineering-guide/spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Service Core 在不改变公开服务行为下完成整体切换

- GIVEN 当前候选的 11 个核心 Go module、独立服务、配置、迁移与环境部署输入均有效。
- WHEN 环境从其精确 immutable candidate 启动 `service-core`。
- THEN 每个 module 保持原 hostname、port、route、generated contract、数据源、migration
  owner 与 `service.name`，且任一 required module 失败时 aggregate readiness 为失败。
- AND 运行面只存在 `service-core` 的核心 workload；当前 target 不与 split-services 并存，
  且 package、health、inspect、CI 与 Green Matrix 消费同一 topology identity。
- AND 同一候选的三环境验收可按 Alpha、Beta、Gamma 串行完成，并可整体回滚到上一 immutable
  candidate 后以精确 bytes 重放。

<a id="gwt-002"></a>
### GWT-002 Service Core 在受控故障下可归因并保持公平恢复

- GIVEN `service-core` 已达到 aggregate ready，且 Search、Content import 或 Chat fan-out
  发生受控压力或依赖不可用。
- WHEN 运行环境采集 module 资源、health、日志、metric 与 trace 证据。
- THEN 登录、Chat 与 API Edge 不被无界 Search 或导入工作耗尽，且每项降级返回所属公开契约的
  typed unavailable 或 recovery。
- AND module fatal、panic、迁移或 shutdown 超时使 host fail-closed 并留下 module 归因；
  非 fatal 的独立依赖恢复不形成 restart storm。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-003](../design.md#dec-003)。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Service Core 三环境实现与验收证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺运行期故障闭环与三环境实际收据；11-module host、standalone parity、
  不可变 composition/topology identity 与环境 package/OCI 投影已形成本地契约。
- 尚缺实现：module fatal/panic 的持续运行期聚合监测与资源公平预算尚未闭合。
- 尚缺验收证据：Alpha/Beta/Gamma immutable candidate 的实际 startup/health/verify、
  原子回滚、稳定性与资源公平性收据尚未取得。
- 完成判定：`GWT-001` 与 `GWT-002` 的全部结果由 local_contract、api_integration 和
  Alpha/Beta/Gamma 当前 immutable candidate 的 user_acceptance/ResultBundle 直接证明。
