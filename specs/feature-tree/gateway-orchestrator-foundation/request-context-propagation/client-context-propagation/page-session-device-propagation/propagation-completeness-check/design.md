# propagation-completeness-check 设计方案

## 设计动因

当前客户端上下文传播已经部分 metadata 化，但仍存在三个残留断点：

- operation 对应的 page/context 仍有代码维护 override 表
- Router 业务路径仍在 `app_router.dart` 里手写
- Repository header 与 decoder context 已局部生成化，但尚未与 UI surface / route 契约统一

结果是“请求契约”和“页面契约”分裂，导致 operation、surface、route 名称在不同文件有多份真相源。本设计的目标是把它们收敛成一套分层 metadata。

## 上游输入评审

- `spec.md` 已明确问题边界：统一 operation / surface / route / path template 的唯一真相源
- `acceptance.yaml` 已补齐 A1~A6，可映射到 T1~T4
- 当前无阻断依赖：已有 `service.yaml`、`ui_config.yaml`、codegen_app_metadata、semantic gate 可复用
- 阻断项已解除：本轮 design 同时更新 feature tree 与 rules/commands，不再只停留在局部代码修补

## 对标输入分析

- 外部产品层面对标：本特性不是终端交互创新，暂无强依赖外部产品对标
- 内部架构对标：
  - `errors.yaml` → 错误码 codegen：唯一真相 + gate 守门
  - `ui_config.yaml` → `ContentUIConfig`：UI 配置元数据化
  - `service.yaml` → `*ApiMetadata`：API path 与 method 元数据化
- 吸收结论：
  - 借鉴：由 metadata 定义、由 codegen 分发、由 gate 禁止回退到字符串字面量
  - 不借鉴：在 codegen 或业务代码中继续维护 `override map` 作为第二份规则表

## 方案对比

### 方案 A：分层元数据统一模型

将不同职责拆分为两个真相层：

- `service.yaml`
  - 继续定义 `api_routes`
  - 为每个 route 补充 operation 级稳定标识与客户端传播语义
- UI metadata（推荐沿用/扩展 `ui_config.yaml`，必要时抽出 `ui_surfaces.yaml`）
  - 定义 `surface_id`、`route_id`、`path_template`、参数、入口类型、默认 operation 绑定、投影类型

codegen 汇聚两层 metadata，生成：

- `*ApiMetadata`：API path builder / method / operation map
- `*OperationIds`：operation 常量
- `*SurfaceIds` / `AppRoutePaths`：surface 与 route 常量
- Router 装配辅助：避免 `context.go('/xxx')` 与 `path: '/xxx'` 手写
- Request context 装配辅助：由 surface + operation 统一生成请求头与 decoder context

**优点**：
- 职责清晰，API 与 UI 分层不混淆
- 支持按域逐步迁移，不要求一次性改完全部页面
- 最符合现有 metadata-first 与 codegen-first 体系

**缺点**：
- 需要扩展 metadata schema、codegen 与 gate
- 迁移期存在旧 `pageId` 与新 `surface/operation` 双写兼容成本

**适用条件**：
- 需要长期治理 App Repository、Router、埋点、decoder context 的统一口径

### 方案 B：保留现有 service.yaml + 在代码中维护全局 Router/Telemetry 注册表

保留 `service.yaml` 只描述 API；另外在 Dart/Go 代码中维护 route/surface/operation 注册表，并由业务代码引用。

**优点**：
- 实现快，初期改动少
- 不需要扩展 metadata schema

**缺点**：
- 代码注册表本质上仍是第二真相源
- 容易再次出现 override map、手写字符串、测试漂移
- 与现有 metadata-first 主线冲突

**适用条件**：
- 仅适合短期救火，不适合作为长期规则

## 选型决策

**选定方案**：方案 A，分层元数据统一模型。

**理由**：

- 符合项目既有 `errors / behaviors / ui_config / service` 元数据驱动范式
- 能同时解决 Repository、Router、decoder context、gate 四个层面的漂移问题
- 可把“业务标识不写死”从代码风格升级为结构约束

## 关键设计决策

- 决策 1：`service.yaml` 是 operation 与 API path 的唯一真相源，禁止在 codegen 中维护 operation→page override 表
- 决策 2：UI surface 与 route 不再散落在 `app_router.dart`，而是通过 UI metadata 声明，再由 codegen 生成常量
- 决策 3：operation 与 surface 是两个正交概念：
  - operation 表示“做什么请求/动作”
  - surface 表示“从哪个 UI 投影/页面/弹层发起”
- 决策 4：请求头与 decoder context 统一由 `surface + operation` 派生；迁移期允许兼容输出旧 `pageId`
- 决策 5：Router 只消费生成的 `AppRoutePaths` / `AppRouteNames` / builder，禁止业务路径字符串字面量
- 决策 6：gate 同时检查 cloud/services 与 app/navigation，不允许未来回退到硬编码

## 元数据模型设计

### 一、operation 层

载体：`quwoquan_service/contracts/metadata/**/service.yaml`

建议新增/固化字段：

```yaml
api_routes:
  - method: GET
    path: /v1/content/feed
    operation: GetFeed
    client_context:
      operation_id: content.feed.get
      default_surface_id: discovery.feed
      decoder_context_id: content.feed.get
```

说明：

- `operation`：领域语义名，供 codegen 命名
- `operation_id`：稳定、可观测、跨端一致的传播标识
- `default_surface_id`：当请求天然归属于单一 surface 时可直接声明；多入口场景允许运行时覆盖
- `decoder_context_id`：默认与 `operation_id` 一致，只有确有必要才单独声明

### 二、surface / route 层

载体：优先扩展实体或领域下的 `ui_config.yaml`；若配置过重，再拆出 `ui_surfaces.yaml`

建议结构：

```yaml
surfaces:
  - surface_id: discovery.feed
    route_id: discovery_feed
    path_template: /discovery
    route_kind: page
    binds_operations:
      - content.feed.get

  - surface_id: rtc.pick_participants
    route_id: rtc_pick_participants
    path_template: /rtc/pick-participants
    route_kind: page
    params: []
```

说明：

- `surface_id`：页面、弹层、sheet、picker 等 UI 投影的稳定标识
- `route_id`：导航标识，供 Router/跳转/测试使用
- `path_template`：GoRouter 的 path 模板
- `route_kind`：`page` / `sheet` / `dialog` / `nested_tab` 等
- `binds_operations`：声明该 surface 默认关联的 operation 集合，用于请求头与埋点校验

### 三、生成产物

codegen 输出建议：

- `lib/cloud/runtime/generated/<domain>/<domain>_operation_ids.g.dart`
- `lib/cloud/runtime/generated/<domain>/<domain>_surface_ids.g.dart`
- `lib/app/navigation/generated/app_route_paths.g.dart`
- `lib/app/navigation/generated/app_route_names.g.dart`
- `lib/app/navigation/generated/app_route_builders.g.dart`

## 运行时装配设计

### Repository

- Remote Repository 继续通过 `*ApiMetadata` 构造 path
- 请求头从 `forPage(pageId)` 演进为 `forSurfaceOperation(...)`
- 过渡期允许：
  - 业务代码传 `surfaceId` + `operationId`
  - 头部同时写旧 `pageId` 与新字段
- `CloudResponseDecoder.context` 改为生成的 operation 常量，不再写字符串

### Router

- `GoRoute.path` 使用生成的 `AppRoutePaths.*`
- 导航跳转使用 route builder 或 path builder，不再直接 `context.go('/create?...')`
- path 参数名由 metadata 声明，测试同步消费生成 builder

### Gate

新增或增强以下静态检查：

- `verify_cloud_services_semantic.py`
  - 禁止硬编码 `/vN/`
  - 禁止 `CloudRequestHeaders.forPage('...')`
  - 禁止 `CloudResponseDecoder(... context: '...')`
- 新增 router/telemetry semantic checker
  - 禁止 `path: '/业务路径'`
  - 禁止 `context.go('/业务路径')`
  - 禁止手写 route override map
- gate 校验 metadata 与 codegen 的 route/surface/operation 覆盖关系

## TDD / ATDD 策略

- 先写 metadata/codegen/semantic gate 的失败测试与静态规则
- 再迁移 codegen 产物，确保 operation/surface/route 常量生成
- 再迁移 Repository 与 Router 消费点
- 最后补齐关键页面旅程与集成验证，确认路由、请求头、decoder context 一致

## Story 与测试层映射

- Story 1：metadata schema 扩展
  - T1：metadata contract / codegen snapshot
- Story 2：Repository 请求上下文迁移
  - T1：semantic checker
  - T2：repository tests
  - T3：remote api path / header propagation tests
- Story 3：Router 常量化迁移
  - T1：semantic checker
  - T2：router unit/widget tests
  - T4：关键旅程测试

## 角色职责与多重防护网

- 产品：定义 surface 命名与用户可见路径语义
- 架构：定义 metadata schema 与过渡兼容策略
- 开发：按 metadata → codegen → consumer migration → tests 顺序实施
- 测试：建立 route/header/context 三位一体证据
- 发布：灰度期观测断链、header 缺失、context 漂移并执行回滚

## 实时性与弱网设计

本特性不是实时协议改造，但要求在弱网重试、页面重入、离线恢复后：

- 同一请求的 `operation_id` 不漂移
- 相同 surface 重试时口径保持一致
- 兼容 header 缺失时能回退到已有观测口径，不影响基础请求成功

## 并发性能与容量设计

- 生成常量为 compile-time const，不做运行时全表扫描
- Router builder 仅封装 path 参数拼接，不引入额外状态容器
- semantic gate 基于静态文本扫描，不依赖昂贵 AST 全量分析作为第一阶段前置

## 灰度发布与回滚设计

- 灰度步进：5/25/50/100
- 观测指标：
  - 新旧 header 双写一致率
  - 关键 route 打开成功率
  - decoder context 非空率
- 回滚条件：
  - 关键页面 route 断链
  - surface / operation header 漏写
  - semantic gate 无法覆盖新增硬编码回退口

## 未来演进

- 演进 1：当所有域迁移完成后，移除旧 `pageId` 兼容头，仅保留 `surface_id + operation_id`
- 演进 2：把 route/surface metadata 扩展到页面投影、埋点事件模板与 A/B 开关联动
- 演进 3：将 router semantic checker 升级为 AST 级校验，减少误报

## 遗留带规划任务

- chat、content、rtc、user 四个高频域优先迁移；低频页面后续分批清理
- 评估 `ui_config.yaml` 与潜在 `ui_surfaces.yaml` 的拆分阈值，避免单文件过度膨胀
