# L3 Story：Redis Scene 客户端 (`redis-scene-client`)

> 所属能力：[Redis 运行时](../spec.md)
>
> Journey / Scenario：[`JNY-006 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为业务服务调用方，我希望按 scene 获得配置一致、可观测且健康受控的 Redis 客户端，从而不在各服务重复处理连接、前缀和降级。

## 2. 范围与非目标

### In Scope

- scene 到连接、key prefix、健康状态和指标的统一解析。
- 必需依赖 fail-fast；允许降级的 scene 返回明确恢复策略。

### Out of Scope

- 业务 key schema、业务事实所有权和以 Memory 充当集成证据。

## 3. 行为要求

### REQ-001 Scene 配置与失败语义

- 同一 scene 在同一环境必须解析到唯一连接与 prefix；prod 必需 scene 缺地址、凭据或健康状态时必须拒绝启动。

## 4. 契约引用

- runtime：`quwoquan_service/runtime/redis`

## 5. 验收场景

### GWT-001 必需 Scene 缺配置时 fail-fast

- GIVEN 服务声明一个 prod 必需 Redis scene，但有效配置缺少地址或 secret。
- WHEN 服务创建该 scene 客户端或执行启动健康检查。
- THEN 初始化失败并产生低基数诊断信息，不创建 Memory/Noop 客户端继续服务。

## 6. 依赖

- 前置要求：runtime-config 提供环境有效配置。
- 上游事实：scene、环境和 secret binding。
- 下游结果：可用客户端或明确启动失败。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 Scene 端到端证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：需把多服务装配和真实 Redis 健康失败直接绑定本节点。
- 完成判定：`GWT-001` 具有 local_contract 与 api_integration 的直接 `spec_ref`。
