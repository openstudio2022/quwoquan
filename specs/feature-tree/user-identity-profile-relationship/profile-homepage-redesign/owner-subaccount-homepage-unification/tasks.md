# Owner/SubAccount 一体化个人主页统一改版 — 任务列表

## 当前交付任务

### 组 1：metadata

- [ ] T01: 在 `quwoquan_service/contracts/metadata/user/user_profile/fields.yaml` 新增 `SubAccountProfileView`、`ProfileInheritanceStateView`、`SubAccountProfileMutation`
- [ ] T02: 在 `quwoquan_service/contracts/metadata/user/user_profile/fields.yaml` 为 `Persona` 补齐 `backgroundUrl`、继承/覆写相关字段
- [ ] T03: 在 `quwoquan_service/contracts/metadata/user/user_profile/service.yaml` 将 `GetSubAccountProfile`、`GetMeProfile` 收敛到 `SubAccountProfileView`，并让 `UpdateUserProfile`、`UpdateSubAccount` 统一消费 `SubAccountProfileMutation`
- [ ] T04: 新建 `quwoquan_service/contracts/metadata/user/user_profile/ui_config.yaml`，定义个人主页 route/surface、一级 Tab、创作/互动二级过滤、方向过滤，以及头图高度比例、头像侵入比例、拉伸上限与吸顶策略
- [ ] T05: 在 `quwoquan_service/contracts/metadata/user/follow_edge/*` 正式定义 `RelationshipCapabilityView` 与关系态枚举
- [ ] T06: 在 `quwoquan_service/contracts/metadata/content/post/*` 新增 `ProfileInteractionActivityView` 与 received/sent 两条互动活动读路由，互动类型仅保留 `like/comment/share`
- [ ] T07: 在 `quwoquan_service/contracts/metadata/_shared/app_routes.yaml`、`request_context.yaml`、`types.yaml` 补齐个人主页相关 route、page_id 与共享枚举
- [ ] T07a: 在 `user_profile/follow_edge/content/post` 补齐 `errors.yaml`、用户可见文案与对应 codegen 错误码枚举，覆盖资料同步、关系能力与互动活动链路

### 组 2：codegen

- [ ] T08: 执行 `make -C quwoquan_service verify-metadata`
- [ ] T09: 执行 `make codegen`
- [ ] T10: 执行 `make codegen-app`
- [ ] T11: 审核 user/content 两域生成物，确认 DTO、API metadata、request page ids、UI config 常量与设计一致
- [ ] T11a: 审核 user/content 两域生成物，确认错误码枚举、decoder context 或等价响应解码常量、header motion token 与设计一致

### 组 3：业务逻辑

- [ ] T12: `user-service` 实现 `SubAccountProfileView` 读模型与 owner/subAccount 继承合成逻辑
- [ ] T13: `user-service` 实现资料编辑同步写入链路，包括 `applyScope` 与选定同步目标
- [ ] T14: `user-service` 实现新的 `RelationshipCapabilityView` 计算和关注/粉丝卡片读模型
- [ ] T15: `content-service` 实现个人主页互动活动 received/sent 查询，打通赞/评论/转发三类活动
- [ ] T16: App 侧收敛 `user_profile_repository`、`relationship_capability_repository`、互动读取链路，停止直接消费手写 `Map<String, dynamic>`
- [ ] T17: 统一 `MyProfilePage` 与 `OtherProfilePage` 到单一 `ProfileShell`，建立单主滚动坐标系，并按新契约重做头部、编辑入口、关系态动作区、Tab、下拉拉伸、整页上卷与双阶段吸顶
- [ ] T17a: 接入 `profile_subject_view_enabled`、`profile_interaction_v2_enabled`、`profile_shell_unified_enabled`、`profile_motion_v2_enabled` 等开关与回退路径
- [ ] T17b: 补齐 profile 观测埋点与关键日志，覆盖 stretch depth、identity pin、primary tab pin、同步写入与互动查询

### 组 4：测试

- [ ] T18: T1 契约测试：metadata schema、枚举、route/page_id、codegen 生成物一致性
- [ ] T19: T2 模块与交互测试：`ProfileShell`、动作区、创作/互动二级过滤、同步提示、背景图 1/4→1/3 拉伸、头像/名称吸顶、一级 Tab 吸顶与二级 Tab 回显
- [ ] T20: T3 端云契约测试：user-service/content-service 新接口、错误码、写入同步与互动活动查询
- [ ] T21: T4 端到端旅程：编辑 owner 并同步给 subAccount、编辑 subAccount 并同步回 owner、查看他人主页并验证互关后的消息/通话入口，以及真实滚动手势下的拉伸/收拢/吸顶行为
- [ ] T21a: T1/T4 验证 feature flag、观测与回滚：验证 `profile_motion_v2_enabled` / `profile_shell_unified_enabled` 关闭时可安全回退

## 搁置任务（带规划）

- [ ] P01: 全仓 `Persona` 命名迁移为 `SubAccount`
  - 规划：待新读写链路稳定后，单开兼容清理 Story，避免本次设计和开发同时承担大规模重命名风险
- [ ] P02: `same_interest / close_friend` 关系层级恢复
  - 规划：依赖独立关系域 Story，先补齐真实产品规则和 metadata，再接回主页动作区
- [ ] P03: 服务端聚合型 `ProfileHomepage` BFF
  - 规划：若后续客户端编排成本过高，再评估是否引入聚合层；本次不提前建设

## 未来演进任务

- [ ] E01: 建立独立的 `ProfileSyncCenter`，让设置页、身份管理页、资料编辑页共用同步策略
- [ ] E02: 个人主页 surface 配置进一步 server-driven，支持灰度调整 Tab 顺序和展示
- [ ] E03: 互动活动扩展到收藏、引用链和跨圈子传播，但以独立 Story 推进，不回退本 Story 的基础 IA
- [ ] E04: 为 owner/subAccount 主页补齐更细粒度的隐私与公开范围策略
