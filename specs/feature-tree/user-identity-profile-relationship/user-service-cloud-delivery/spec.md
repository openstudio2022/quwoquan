# L2 特性：用户服务云侧实现与端云一致性交付

## 背景与动机

端侧"我的主页"和"作者主页"（`profile-homepage-redesign`）已完成 UI 重构，`ProfileShell` 统一组件通过 `UserProfileRepository`（18 方法）驱动全部业务数据。然而：

1. **云侧零实现**：`contracts/metadata/user/` 下 `user_profile`（聚合）、`follow_edge`（实体）、`block_edge`（实体）的 fields/service/storage/errors/events 已完整定义，但 `services/` 下无 `user-service` 目录，无 domain/application/adapters/infrastructure 任何代码。
2. **端侧全 Mock**：`UserProfileRepository` 的 18 个方法有 Abstract + Mock + Remote 三层实现，但 Remote 无后端可调，当前默认使用 Mock；`UserWorkItem`/`UserLifeItem` 为手写类型（非 codegen），`UserErrorCode` 枚举缺失。
3. **无法部署到生产**：`process_domain_mapping.yaml` 中 user 域已归属 seed-box（integration/prod），但 seed-box Go 二进制不存在，user-service 镜像不存在，CI 流水线无构建步骤。
4. **测试缺口**：端侧 L1 契约测试已有但缺 DTO 字段契约和错误码契约；云侧 L2 契约测试完全缺失；L3 端云集成测试断路；L4 旅程测试不完整。

本特性是 `profile-homepage-redesign` spec.md O8（Out of Scope）所标注的"Go 云侧 UserProfile 服务实现——独立 story"，将 Mock 驱动的端侧主页升级为端云完整链路。

## 目标用户

- 所有趣我圈用户（通过"我的主页"查看/编辑个人档案、管理分身、查看统计）
- 其他用户（通过"作者主页"查看他人档案、关注/取关、屏蔽/取消屏蔽）
- 跨域服务消费方（chat-service 检查屏蔽关系、recommendation-engine 读取用户画像、notification-service 读取设备和设置）

## 功能范围

### F1: user-service 云侧 DDD 四层实现

基于 `contracts/metadata/user/` 已有 metadata，实现完整的 Go 服务：

- **Domain 层**：按 D0 对象裁决实现 UserAccount、Persona、Relationship 等聚合/
  对象模型、对象专属 AggregateStore 端口与 typed 领域事件。
- **Application 层**：按对象拆分 command/query Facade；command 绑定 aggregate owner，
  query 绑定 named Reader/Slice 且不加载 aggregate。
- **Adapter 层**：HTTP Handler，对齐 `service.yaml` 定义的 20+ 路由
- **Infrastructure 层**：PostgreSQL（user_profiles、personas、user_settings、block_edges、user_works、user_life_items）、MongoDB（follow_edges）、Redis 缓存（profile 600s、setting 600s、block_set 3600s）

### F2: 存储与缓存

严格按 `storage.yaml` 定义实现：

- PostgreSQL：Migration DDL（表、索引、唯一约束、GIN trigram 全文搜索）
- MongoDB：follow_edges 集合索引（follower+createdAt、followee+createdAt、unique follower+followee）
- Redis 缓存：`cache:user_profile:{userId}` TTL=600s（UserProfileUpdated 失效）、`cache:user_setting:{userId}` TTL=600s（UserSettingUpdated 失效）、`blocked_set:{userId}` TTL=3600s set 类型（UserBlocked/UserUnblocked 失效）
- UserAuth 标记 `cache_excluded`，不缓存

### F3: 端侧 codegen 对齐

- 执行 `make codegen-app` 生成 `user_profile_dto.g.dart`、`user_work_dto.g.dart`、`user_life_item_dto.g.dart`、`UserErrorCode` 枚举
- 替换手写 `UserWorkItem`/`UserLifeItem` 为 codegen 产物
- Remote 实现错误处理从 `throw Exception` 对齐到 `CloudException(UserErrorCode)`

### F4: 部署到灰度与生产

- Dockerfile（多阶段构建 Go 1.24 + Alpine）
- user-service 作为 seed-box Pod sidecar 容器（与 recommendation-service 模式一致）
- Kustomize overlay 更新（integration/prod）
- CI 流水线增加构建/测试/镜像步骤
- 配置版本快照 + 灰度阶段（50% auto → 100% 审批）

### F5: 三层测试覆盖

- **local_contract**：metadata/codegen、对象边界、Facade/Ports、端侧 DTO 与错误码。
- **api_integration**：Profile、Follow、Block、Persona、Cache、Error 使用真实
  PostgreSQL/MongoDB/Redis 与运行态 HTTP。
- **user_acceptance**：关注/取关、编辑资料、分身管理与屏蔽旅程。

## 不做什么（Out of Scope）

- **O1**: 认证/登录流（auth/login/token refresh）-- 由 `auth-profile-snapshot/auth-token-lifecycle` 节点承接
- **O2**: content-service 改造（`listUserPosts` 已由 content 域实现，本特性不修改）
- **O3**: circle-service 改造（`listUserCircles` API 路由已在 circle 域 service.yaml 声明，本特性不修改 circle-service 代码）
- **O4**: seed-box 聚合二进制（本期 user-service 作为 sidecar 独立容器，seed-box 聚合为长期演进项）
- **O5**: 端侧 UI 重构（已由 `profile-homepage-redesign` 完成，本特性不修改 UI 层代码）
- **O6**: 推荐引擎集成（user 特征向量供给属于 recommendation 域）
- **O7**: 通知服务集成（设备 token + 推送属于 notification 域）
- **O8**: 用户搜索（GIN trigram 索引已建，搜索 API 属于 gateway/orchestrator 域）

## 适用范围与约束

### 适用范围

- 云侧 Go 服务实现（`quwoquan_service/services/user-service/`）
- 存储基础设施（PostgreSQL + MongoDB + Redis）
- 端侧 codegen 对齐（`quwoquan_app/lib/cloud/runtime/generated/user/`）
- 端侧 Repository Remote 实现错误处理对齐
- 部署流水线（Dockerfile + Kustomize + CI + 灰度）
- 四层测试覆盖

### 技术约束

- **DDD 分层**：domain ← application ← adapters ← infrastructure（单向依赖）；domain 层禁止 import 数据库驱动
- **runtime 统一**：必须使用 `RuntimeFailure/RuntimeRecoveryPolicy`、
  `runtime/config.RuntimeConfigProvider` 与统一 observability；数据访问只经
  UserAccount/Persona/Relationship 对象专属 Store/Reader port，禁止跨对象泛型
  CRUD、动态查询和运行时对象注册
- **codegen 保护**：`DO NOT EDIT` 文件禁止手改，`make gate` 通过 hash 比对守护
- **metadata-first**：任何新实体/字段/事件必须先更新 YAML → verify → codegen → 业务逻辑
- **错误码 metadata 约束**：errors.yaml 定义 code/l10n_key/user_message，禁止硬编码
- **部署拓扑约束**：integration 与 prod 映射必须一致；同一环境中 domain 只能出现一次

### 不适用情形

- 当 seed-box 聚合二进制实现后，user-service sidecar 部署模式将被替换为 seed-box 内置域
- 当前不处理高并发下的 followerCount 精确计数（最终一致即可）

## 对标输入与吸收结论

### 内部对标：content-service（标杆服务）

| 维度 | content-service 做法 | 借鉴 | 适用边界 |
|------|---------------------|------|---------|
| DDD 四层 | object model/ports → object command/query Facade → transport → infrastructure adapters | **完全借鉴** | user-service 按相同模式组织 |
| main.go 启动流 | resolveRuntimeIdentity → loadRuntimeConfig → validate → 依赖注入 → HTTP handler → ListenAndServe | **完全借鉴** | user-service 增加 PostgreSQL/MongoDB/Redis 初始化 |
| 双存储实现 | 对象专属 Mongo/PG adapter + 显式 composition root | **借鉴** | test adapter 仅用于 local contract，beta/gamma/prod 使用真实实现 |
| 三层测试 | local_contract + api_integration + user_acceptance | **借鉴** | user-service 按 Profile/Follow/Block/Persona/Cache/Error 拆分 |
| 配置分层 | default → env → version 三层合并 | **完全借鉴** | user-service 同模式 |
| Kustomize 部署 | seed-box base + overlays(dev/integration/prod) | **完全借鉴** | user-service 作为 sidecar 加入 seed-box Pod |

### 外部对标：无需对标

用户服务是标准的 CRUD + 关系图 + 缓存模式，不涉及算法或复杂交互设计，内部对标 content-service 即可。

## 验收重点

核心维度（详见 acceptance.yaml）：
1. getUserProfile 端云完整链路：端侧 Remote → HTTP → user-service → PostgreSQL → Redis cache → 返回
2. followUser/unfollowUser 幂等操作，followerCount/followingCount 实时更新
3. blockUser/unblockUser O(1) Redis set 检查，跨域 CheckBlocked 可调用
4. Persona 管理事务一致性：同时只有一个 active persona
5. 缓存策略生效：profile TTL=600s，block_set TTL=3600s，事件驱动失效
6. 端侧 DTO codegen 替换手写，错误码 codegen 替换硬编码
7. L1+L2+L3+L4 四层测试全部通过
8. 部署到 integration 成功，灰度到 prod 可执行
9. 错误码端云一致：errors.yaml 定义 → Go AppError → Dart UserErrorCode
