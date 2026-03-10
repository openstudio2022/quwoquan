# operation-surface-route-single-source 设计方案

## 设计动因

operation、surface、route 现在横跨 `service.yaml`、App Router、Repository、请求头、decoder context 和测试代码，但没有统一的 metadata 分层模型，导致 codegen 仍需 override map，业务代码仍存在硬编码回退口。

这件事本质上是 **metadata schema + codegen 汇聚能力** 的缺失，因此主归属应在 `runtime-codegen`，而非单独放在 gateway 或客户端页面章节。

## 上游输入评审

- 上游需求已经明确要求“统一升级到唯一源头”
- 现有 `errors.yaml`、`ui_config.yaml`、`service.yaml`、`codegen_app_metadata` 已经提供可复用模式
- `/design` 已形成初版方案，本次迁移仅调整主归属，不改变核心设计结论

## 方案对比

### 方案 A：以 runtime-codegen 为主归属，gateway/client 为消费方

- metadata 负责声明
- codegen 负责汇聚并生成常量
- gateway/client 只消费生成结果

**优点**：
- 符合根因
- 端云共享同一套规则
- 更容易纳入 semantic gate

**缺点**：
- 需要同步扩 metadata schema 与 codegen

### 方案 B：分别挂在 gateway 和 runtime-client-foundation

- gateway 管 propagation
- client foundation 管 route / surface
- codegen 仅配合

**优点**：
- 看上去职责切分直观

**缺点**：
- 真正的“唯一真相源”被拆散
- 容易重新回到多处维护规则表

## 选型决策

**选定方案**：方案 A。

**理由**：这是一个“定义与生成”问题，不是某一个消费侧的问题。gateway、客户端、测试与门禁都应依赖 `runtime-codegen` 输出。

## 关键设计决策

- `service.yaml` 负责 API operation 与 path 契约
- `ui_config.yaml` 或未来 `ui_surfaces.yaml` 负责 surface / route 契约
- `codegen_app_metadata` 汇聚两侧 metadata，生成 operation/surface/route 常量
- `CloudRequestHeaders` 从 `forPage(pageId)` 演进到 `forSurfaceOperation(...)`
- 迁移期间可兼容旧 `X-Client-Page-Id`，但其值同样由 codegen 生成
- App Router 统一消费 route 常量 / builder
- semantic gate 同时覆盖 cloud/services 与 app/navigation

## Story 与实施顺序

1. metadata schema 扩展
2. codegen 扩展
3. request headers / decoder context 迁移
4. App Router / route builder 迁移
5. semantic gate 与测试补齐

## 未来演进

- 全域迁移完成后移除旧 `pageId` 兼容头
- 将 route/surface metadata 扩展到事件埋点模板与页面投影
- 将 semantic gate 升级为 AST 级校验
