# L1 规格：圈子社区（v2 — 全面重构）

## 背景与动机

圈子是趣我圈的核心社区单元，是用户围绕共同兴趣/领域聚合的空间。当前圈子存在以下瓶颈：

1. **分类体系孤立**：圈子频道分类（遇见/校园/车友/人文/生活/运动/科技/旅行/美食）与个人助理的领域路由体系（weather/travel/local_life/health/education/...）完全独立，无法实现内容-智能联动。
2. **圈子主页功能单薄**：当前仅有 3-Tab（创作/互动/生活），缺少协作深度——无共享存储、无群聊入口、无自定义板块。
3. **端侧代码未迁移**：仍在 `features/circles/` 目录，无独立 `CircleRepository`，数据全部来自 `AppContentRepository` 的 mock。
4. **圈子详情页代码质量**：存在大量硬编码值（字号/间距/尺寸/圆角），违反编码规范。

本次重构目标：将圈子从「浏览型列表页」升级为「同频社区空间」，具备发现-聚合-协作-创作全链路能力。

## 目标用户

- **圈子发现者**：寻找与自身兴趣同频的社区，需要高效匹配推荐。
- **圈子成员**：在圈内浏览作品、参与群聊、使用共享存储空间、发布内容。
- **圈子管理者（圈主/管理员）**：管理成员、配置圈子板块、审核内容、查看运营数据。
- **创作者**：在圈子内发布作品、获得同频用户的互动和反馈。

## 功能范围

### R1：圈子发现与领域对齐

- R1.1：建立统一领域标签体系（domain taxonomy），圈子频道分类与个人助理领域路由共享同一套领域 ID。
- R1.2：圈子主页（circles_page）频道基于领域标签体系驱动，支持频道管理面板（已有特性 circles-channel-management-panel 对齐）。
- R1.3：同频发现推荐——基于用户兴趣画像（助理交互历史 + 浏览行为 + 圈子参与）匹配推荐圈子。
- R1.4：圈子与助理联动——在特定领域圈子内唤起助理时，自动路由到对应领域技能。

### R2：圈子主页重构

- R2.1：**作品发布区**——圈子内独立的内容 feed，支持图文/视频/文章多类型，瀑布流 + 列表视图切换。
- R2.2：**群聊入口**——圈子绑定群聊（IM），成员可通过即时消息联系；群聊支持自定义（名称、头像、公告）；圈主可管理群聊权限。
- R2.3：**存储空间（网盘）**——圈子内共享存储区，成员可上传/下载/浏览文件（文档、图片、压缩包等），支持文件夹组织、容量限制、权限控制。
- R2.4：**自定义板块**——圈主可配置圈子主页板块顺序和可见性（如：隐藏存储空间、调整群聊/作品区位置），支持自定义板块名称。
- R2.5：圈子主页布局从固定 3-Tab 升级为可配置板块式结构，各板块独立加载、独立降级。

### R3：圈子协作工具

- R3.1：存储空间 CRUD（创建文件夹、上传文件、下载、删除、重命名），对接云端对象存储。
- R3.2：存储空间权限模型——圈主完全控制、管理员可管理、成员可上传/下载、访客只读。
- R3.3：群聊与圈子成员同步——加入圈子自动进群、退出圈子自动退群（可配置）。
- R3.4：群聊自定义——支持修改群名、群头像、群公告、@全体成员、消息置顶。

### R4：端侧平台化重构

- R4.1：目录迁移 `features/circles/` → `ui/circle/`（pages + providers + widgets + models）。
- R4.2：创建独立 `CircleRepository`（Abstract + Mock + Remote 三层模式），注册到 `app_providers.dart`。
- R4.3：圈子 mock 数据从 `PrototypeMockData` 提取到 `lib/cloud/services/circle/mock/`。
- R4.4：圈子详情页硬编码清理——全部替换为 AppSpacing/AppTypography/AppColors 语义标签。
- R4.5：圈子页面组件拆分——从单文件大 Widget 拆分为独立 widget（CircleCard、ChannelPanel、DiscoveryPostCard 等）。

### R5：云侧服务实现（端云一体化）

- R5.1：基于已有 `contracts/metadata/social/circle/` 实现 circle-service 核心 API（ListCircles, CreateCircle, GetCircle, JoinCircle, LeaveCircle, GetCircleFeed, GetCircleStats）。
- R5.2：扩展 metadata 支持 CircleStorage 实体（fields.yaml, service.yaml, events.yaml）。
- R5.3：圈子-群聊集成事件（CircleMemberJoined → 自动加群，CircleMemberLeft → 自动退群）。

### R6：既有能力增强（已有 L2 覆盖）

- 圈子生命周期（activity-member-governance）
- 圈内推荐闭环（in-circle-recommendation-loop）
- 圈子运营统计（circle-management-and-stats）

## 不做什么（Out of Scope）

- OS1：不做圈子内支付/电商功能（打赏、商品橱窗等）。
- OS2：不做跨圈内容搬运（圈子间内容同步/转发到其他圈子）。
- OS3：不做 IM 协议层实现——群聊依赖已有 chat 域能力，圈子仅做集成层。
- OS4：不做存储空间在线编辑（Office 文档在线协作等）——仅做上传/下载/浏览。
- OS5：不做圈子付费/VIP 等级体系。
- OS6：不做圈子广告投放系统。

## 约束

### 技术约束
- 端侧遵循 DDD 分层约束（ui/circle/ → cloud/services/circle/ → contracts/metadata/social/circle/）。
- 圈子频道分类必须由 metadata 驱动（domain_taxonomy.yaml → codegen），禁止硬编码。
- 存储空间对接云端对象存储（S3-compatible），文件元数据存 MongoDB。
- 群聊集成通过事件驱动（CircleMemberJoined/Left → chat-service 消费），非同步 RPC。
- 圈子活动流接口支持游标分页与推荐排序。
- 成员与权限变更必须可审计，错误码可定位模块与原因。

### 业务约束
- 圈子存储空间有容量上限（按圈子等级配置），超限需提示。
- 群聊与圈子成员同步为默认行为，圈主可在设置中关闭。
- 领域标签对齐是增量方案——现有圈子分类保持不变，新增领域标签映射层。

### 编码约束
- 所有 UI 代码禁止硬编码视觉字面量（遵循 02-dart-coding 规范）。
- 所有 import 使用绝对路径（package:quwoquan_app/...）。
- 错误码由 errors.yaml 定义，codegen 生成，禁止硬编码。

## 验收重点

详见 `acceptance.yaml`，核心维度：
- A1~A2：端侧目录迁移 + Repository 创建。
- A3~A4：领域标签对齐 + 圈子主页重构。
- A5~A6：存储空间 + 群聊集成。
- A7：代码质量（硬编码清理）。
- A8~A9：云侧 API + 同频发现推荐。
