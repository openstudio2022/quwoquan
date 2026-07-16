# L1：runtime（统一运行时能力域）

本目录是 `runtime` L1 领域服务的特性树入口。节点数量、层级和路径只以
`specs/feature-tree/tree_index.yaml` 为准，本文件不维护手工统计。

## 权威入口

- D0/F1/G1：
  `system-architecture-and-engineering-guide/design.md` 与 `acceptance.yaml`
- Metadata/ContractGraph：
  `quwoquan_service/contracts/metadata/DESIGN.md`
- 扩展执行：
  `specs/runtime_extension_catalog.md`

## 边界

公共 runtime 只承载跨域机制：

- OperationContext、RuntimeFailure/RecoveryPolicy/ErrorResponse。
- typed config、HTTP client/server、observability、messaging、governance、health、
  clock/id。
- Page、Version、IdempotencyKey 等值类型。

业务对象的 command/query Facade、AggregateStore、named Reader、typed Slice 与具体
存储 adapter 都归属各服务；adapter 放在服务 `internal/infrastructure/**`，由服务
composition root 显式装配。

Metadata 只由构建期 ContractGraph compiler 消费。Go、Dart、OpenAPI 与 coverage
共享同一个 Graph；服务运行期不扫描 metadata，也不根据存储类型动态创建业务数据访问
实现。

## 主要能力入口

- `runtime-config`：typed config 与环境 overlay。
- `runtime-errors`：结构化错误与恢复策略。
- `runtime-observability`：日志、指标、trace 与 OperationContext。
- `runtime-http` / `runtime-rpc`：transport 公共机制。
- `runtime-messaging`：消息 envelope、outbox/inbox 公共机制。
- `runtime-governance`：限流、熔断与健康治理。
- `runtime-codegen`：唯一 ContractGraph compiler 与派生产物。
- `runtime-testinfra` / `runtime-test-pyramid`：三层测试基础设施与证据治理。
- `runtime-client-foundation`：App 公共底座。
- `system-architecture-and-engineering-guide`：D0/F1/G1 架构和准出。

其余当前节点按 `tree_index.yaml` 导航；不得在 README 复制第二套状态或实施计划。
