# L2 群内核与协作工具 — 设计方案

## 设计动因

本 L2 的重点不再是“给圈子补几个协作功能”，而是把 `群` 从聊天能力里解耦出来，冻结为真正的子单元模型。没有这一步：

- 公共群 / 自建群 / 组织节点都无法统一建模
- 群主 / 群管的治理边界无法成立
- 资料、公告、聊天会继续散落在多个模型里

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `circle-collaboration-tools/spec.md` | 已冻结公共群、自建群、群内空间与组织节点复用 |
| `circle-community/design.md` | 已冻结 `CircleGroup` 是子单元聚合，不再把群等同会话 |
| `circle-homepage-redesign/design.md` | 已冻结群主页与组织节点主页结构 |
| `content/post/*` | 需增加 `groupId/nodeId` 分发上下文 |
| `messages/conversation/*` | 需增加 `circleGroupId` 绑定字段 |

## 对标输入分析

| 对标 | 借鉴点 | 不借鉴 |
|---|---|---|
| 微信群资料页 | 群主页包含聊天、资料、公告，不等于聊天线程 | 不把聊天记录本身当群主页 |
| Discord | 子单元治理、角色边界、频道承载多能力 | 不照搬频道树与语音结构 |
| QQ 群文件 | 资料列表、权限和轻协作 | 不引入复杂版本管理 |

## 方案对比

### 方案 A：继续把 `Conversation` 当成群

优点：

- 复用现有 chat 域，开发量最小

缺点：

- 群主 / 群管、资料、公告、公开/私有都无处表达
- 组织节点无法复用
- 会继续把产品语义压扁成“聊天群”

### 方案 B：群组只有主页，不再拆群子单元

优点：

- 模型最简单

缺点：

- 无法承接多公共群、自建群、班级/部门节点
- 无法实现“加入群组后再申请入群”的明确边界

### 方案 C：引入 `CircleGroup` 子单元，绑定聊天 / 资料 / 公告 / 节点

优点：

- 公共群、自建群、组织节点可以统一建模
- 聊天、资料、公告成为群的能力，而不是群本身
- 角色、审批、搜索和聚合边界都可冻结

缺点：

- 需要 metadata、chat、content 一起补字段与契约

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### DK-1：`CircleGroup` 才是群的聚合根

- `Conversation` 只是交流能力绑定
- `CircleGroup` 才承接：
  - 群主 / 群管
  - 公开 / 私有
  - 公共群 / 自建群 / 组织节点
  - 资料
  - 公告
  - 加入审批

### DK-2：加入群组与加入群严格分离

- 加入群组后不自动加入任何群
- 公共群一律 `申请加入`
- 默认公共群也不自动加入

### DK-3：公共群手动创建与扩容

- 公共群由圈主 / 圈管或组织负责人 / 管理员手动创建
- 不做系统自动分裂
- 多个公共群必须先命名后展示

### DK-4：自建群默认公开，私有群只在圈内精确/模糊搜索

- 默认公开
- 私有群不出现在默认列表
- 私有群搜索规则：
  - `groupId` 精确匹配
  - `groupName` 模糊匹配
- 搜索范围只限已在该群组中的成员

### DK-5：群治理权边界

- 上位治理者仅对公共群有最终处置权
- 不处置私有自建群
- 私有自建群由群主 / 群管自行治理

### DK-6：群资料与公告跟着群走

- 资料默认挂在 `CircleGroup`
- 公告也挂在 `CircleGroup`
- 文件上传仍采用预签名 URL 直传对象存储

### DK-7：组织节点复用同一模型

- 班级、院系、部门、团队都落在 `CircleGroup`
- 通过 `groupType=org_node` 与 `nodeType` 区分前台表现

### DK-8：节点内容归内容域，聚合归 circle 域编排

- 内容仍由 content 域存储
- `groupId/nodeId` 进入内容分发表
- 父节点聚合按 `lastActiveAt` 排序

## metadata / codegen 方案

### `social/circle/fields.yaml`

新增：

- `CircleGroup`
- `CircleGroupMember`
- `CircleGroupNotice`
- `CircleGroupType`
- `CircleGroupVisibility`
- `CircleGroupJoinPolicy`
- `OrganizationNodeType`

### `social/circle/service.yaml`

新增或扩展：

- `ListCircleGroups`
- `CreateCircleGroup`
- `ApplyJoinCircleGroup`
- `ApproveCircleGroupJoin`
- `RejectCircleGroupJoin`
- `ListCircleGroupFiles`
- `CreateCircleGroupFile`
- `ListCircleGroupNotices`

### `messages/conversation/*`

- 增加 `circleGroupId`
- chat-service 只负责 Conversation 生命周期与消息

### `content/post/*`

- 增加 `groupId/nodeId`
- 支持节点内容聚合与最近活跃排序

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- `Circle.conversationId` 不再代表群本身
- 群相关权限迁到 `CircleGroup / CircleGroupMember`

### 迁移 / 回填

- 记录 `Circle.conversationId` 迁为默认公共群的 `conversationId`
- 原有群文件与群公告能力若落在圈级，迁移到默认公共群
- 无法准确归属的记录资料可先保留在圈级并逐步清理

### 双读 / 双写

- 迁移期允许圈级与群级 conversation 兼容读
- 退出条件：
  - 所有活跃群组均存在 `CircleGroup`
  - chat 侧全部改读 `circleGroupId`

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 不新增用户可见 feature flag

### 观测

- `circle_group_create_count`
- `circle_group_apply_count`
- `circle_group_apply_decision_latency_ms`
- `circle_group_private_search_hit_count`
- `circle_group_file_upload_success_count`

### SLO 验证

- 入群申请链路稳定
- 文件与公告能力不阻塞群主页
- 群内搜索与节点聚合符合性能约束

### 回滚

- 整版回退到旧圈子协作实现
- 必要时回落到“默认公共群兼容读”

## TDD / ATDD 策略

- `T1_schema`
  - CircleGroup contract
  - conversation `circleGroupId`
  - content `groupId/nodeId`
- `T2_module_interaction`
  - 公共群 / 自建群列表
  - 申请入群
  - 私有群搜索
  - 群资料与公告
- `T3_cross_service_integration`
  - CircleGroup 与 chat
  - CircleGroup 与 content
  - 节点聚合
- `T4_user_journey`
  - 加入群组 -> 申请公共群
  - 圈内建私有群
  - 组织节点查看资料与交流

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 CircleGroup 元数据与角色/审批模型 | `T1_schema` |
| `P2` | 完成 codegen 与 conversation/content 关联字段 | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地公共群 / 自建群 / 私有群搜索流程 | `T2_module_interaction`, `T4_user_journey` |
| `P4` | 落地群资料、公告与节点内容聚合 | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |

## 未来演进

- 若未来协作编辑需求变强，再把群资料抽成更完整的文件协作域。
- 若大型群组需要更多公共群分区，再在 `CircleGroup` 上扩展排序与推荐，而不是重新建模。
- 若群治理需要审计流水，再补 `CircleGroupAuditLog`。
