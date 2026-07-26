# L3 Story：搜索高风险配置灰度发布 (`search-risky-config-gray-release`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为搜索平台运维者，我希望 search-service 的 ES/Redis 高风险配置按 revision 灰度并可回滚，从而在不暴露密钥或破坏搜索可用性的前提下发布配置。

## 2. 范围与非目标

### In Scope

- search-service config schema、单环境 overlay、发布 revision 与摘要。
- ES/OpenSearch 与 Redis 的启用、TLS、凭据 binding、SLO 门禁和回滚边界。

### Out of Scope

- 真实 prod-hosted 放量执行。
- 业务主存储迁移。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 search-service release config 版本快照与配置门禁

- 每个发布 revision 必须绑定兼容镜像范围和配置摘要；环境 overlay 不得包含真实 endpoint 密钥、password 或 token。
- gamma 验证和 SLO 判定通过前不得推进 prod；阈值越界时必须回退上一份已验证 revision。

## 4. 契约引用

- canonical：`quwoquan_service/services/search-service/config/schema.yaml`
- canonical：`quwoquan_service/services/search-service/environments/gamma/config.yaml`
- canonical：`quwoquan_service/services/search-service/environments/prod/config.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 search-service release config 版本快照与配置门禁

- GIVEN search-service 的新 revision 修改 ES 或 Redis 高风险配置，并声明兼容镜像和回滚目标。
- WHEN 发布链在 gamma 合成 schema、环境 overlay 与 secret binding，并评估搜索 SLO。
- THEN 只有摘要与兼容性通过且不含明文凭据的 revision 可推进；SLO 越界时恢复上一 revision，prod 不接收未验证配置。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 search-service release config 版本快照与配置门禁

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前尚缺在完整第一方拓扑执行 search-service 配置 revision 推进、SLO 越界和回滚演练。Gamma-local 的外部能力已由统一材料器装配 Port 对等替身，不要求真实第三方 secret；四环境 package 与单快照摘要门禁虽已通过，但运行时恢复仍未形成可追溯闭环。
- 完成判定：Gamma 配置发布与回滚演练通过，`GWT-001` 的 package、运行时 SLO 和回滚证据均可追溯。
