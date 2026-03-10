# L4 特性：page-session-device-propagation

## 功能说明
- 待补充

## 约束
- 待补充

## 验收标准
- 待补充（A1~A8 重点组）

## Folded legacy node `propagation-completeness-check`

# L5 特性：propagation-completeness-check

## 背景与动机

本节点仅负责“客户端上下文是否完整传播到 gateway / downstream”这一消费侧治理。

`operation / surface / route / path template` 的主定义、主设计与 codegen 唯一源，已迁移到：

- `runtime/runtime-codegen/struct-repo-handler-migration-generation/operation-surface-route-single-source`

因此本节点不再作为唯一真相源主归属，而是负责消费上游生成结果，确保请求头、trace、decoder context 与网关传播链路稳定一致。

## 功能范围

- 定义请求头中需要传播的客户端上下文字段
- 约束 gateway / request-context-propagation 链路正确消费 codegen 生成的 operation / surface 标识
- 验证弱网重试、页面重入、回退后上下文不会漂移

## 不做什么（Out of Scope）

- 不负责定义 route / surface metadata schema
- 不负责 codegen 生成 route / surface 常量
- 不负责 `app_router.dart` 的主归属治理

## 约束

- gateway 不得根据业务字符串字面量推断 operation / surface
- 请求头与 decoder context 必须消费 `runtime-codegen` 生成结果
- 兼容期旧 `pageId` 可保留，但不得脱离 codegen 单独维护

## 验收重点

- 请求头传播完整
- operation / surface 到达网关与下游时无漂移
- 弱网重试与页面重入后口径保持稳定
