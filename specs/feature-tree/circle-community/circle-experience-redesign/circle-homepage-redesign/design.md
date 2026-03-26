# L3 群组详情模板与圈子主页基线 — 设计方案

## 设计动因

本 L3 不再只是“把 CircleDetailPage 做漂亮”，而是要完成两件事：

1. 用一套共享壳层承接 `通用圈子模板` 与 `组织主页模板`。
2. 把 `首页 / 内容 / 群(组织) / 成员` 的信息架构真正冻结下来，避免后续实现继续把详情页做成内容流或聊天入口的拼装页。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `circle-homepage-redesign/spec.md` | 已冻结共享壳层、双模板、二级页面模式、内容模型和角色边界 |
| `circle-homepage-redesign/acceptance.yaml` | `A1~A7` 已能覆盖本轮设计 |
| `circle-community/design.md` | 已冻结 `CircleGroup`、角色分层、组织节点聚合和搜索统一词 |
| `circle-collaboration-tools/spec.md` | 已冻结群协作能力边界 |

## 对标输入分析

| 对标 | 吸收点 | 不吸收点 |
|---|---|---|
| ProfileShell | 共享详情壳层、吸顶、统一头部节奏 | 不强制完全复用作者主页的页签语义 |
| Discord | 子单元区分、角色可见性、群内入口清晰 | 不照搬频道列表和实时在线表达 |
| 微信群资料页 | 群不只有聊天，也有资料和公告入口 | 不照搬聊天列表作为群主页本身 |

## 方案对比

### 方案 A：一套详情页，组织型只改文案

优点：

- 开发量最小

缺点：

- 学校/班级/部门会明显像“兴趣圈套皮”
- 组织节点无法自然承载内容与资料沉淀

### 方案 B：为组织型和兴趣型各写一套完全独立详情页

优点：

- 前台最自然

缺点：

- 壳层、模块、状态、测试几乎全部重复
- 容易导致一处升级、另一处落后

### 方案 C：共享壳层 + 模板适配器 + 节点主页变体

优点：

- 结构统一，模板差异清晰
- 能兼顾复用与语义自然
- 最适合后续继续扩节点与群能力

缺点：

- 需要提前冻结哪些模块共享、哪些模块差异化

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### DK-1：群组详情采用共享壳层

共享壳层最少包含：

- 头部信息区
- 主操作区
- 模块化首页容器
- 四页签导航
- 独立模块降级能力

### DK-2：通用圈子模板

页签固定为：

- `首页`
- `内容`
- `群`
- `成员`

首页默认模块顺序：

1. 头部信息
2. 公告与圈规
3. 我的群 / 公共群入口
4. 内容精选
5. 关联具体事物摘要卡（如有）
6. 活跃成员

### DK-3：组织主页模板

页签固定为：

- `首页`
- `内容`
- `组织`
- `成员`

首页默认模块顺序：

1. 头部信息
2. 官方公告
3. 找到我的组织
4. 组织结构入口
5. 内容精选
6. 交流 / 资料快捷入口
7. 关键成员

### DK-4：二级页面分成两类

#### 通用群主页

页签：

- `首页`
- `交流`
- `资料`
- `成员`

#### 组织节点主页

页签：

- `首页`
- `内容`
- `交流`
- `资料`
- `成员`

原因：

- 班级、院系、部门不能被弱化成一个聊天群页
- 节点本身就需要承接内容沉淀和上级聚合

### DK-5：内容页统一为群组层主公开分发面

- 群组详情页内容页统一承接 `笔记 / 作品 / 提问 / 口碑`
- 群页与组织节点页的 `内容` 只表示该节点内容视图，不生成第二条群级公开时间线
- 群层首页仍以 `交流 / 资料 / 公告` 为主

### DK-6：发布入口和文案

- 顶层动作统一叫 `发布`
- 技术模型统一叫 `发布内容`
- 前台按场景文案分流：
  - 笔记：发笔记 / 发动态
  - 作品：发作品
  - 提问：提问题
  - 口碑：写口碑

### DK-7：组织节点父子聚合

- 节点独立发布内容
- 父节点默认聚合所有子节点内容
- 默认排序按 `最近活跃时间`
- 最近活跃时间由发布时间与评论/回复更新时间共同决定

### DK-8：管理页的可见性

- 圈主 / 圈管、负责人 / 管理员、群主 / 群管可看到真实可操作控件
- 普通成员也可进入同一管理页面骨架
- 无权限操作必须 disabled，而不是隐藏

### DK-9：具体事物集成方式

- 通用圈子模板可展示关联具体事物摘要卡和口碑精选
- 组织主页模板默认不强调具体事物，除非业务上明确关联
- 前台始终显示具体类目名，不显示“实体”

## metadata / codegen 方案

为支撑双模板与节点主页，需要以下类型化视图：

### `social/circle/fields.yaml`

- `Circle.kind`
- `Circle.display_subject_type`
- `CircleHomepageTemplateView`
- `CircleGroupSummaryView`
- `OrganizationNodeSummaryView`

### `social/circle/service.yaml`

新增或扩展：

- `GetCircleHomepage`
- `ListCircleGroups`
- `ListOrganizationNodes`
- `GetCircleGroup`

说明：

- API 可以继续由 `circle-service` 提供
- 不需要为组织主页单独发服务

### `content/post/*`

支持：

- 按 `circleId` 查询
- 按 `groupId/nodeId` 过滤
- 按 `lastActiveAt` 排序
- 父节点聚合

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- `CircleDetailPage` 从单模板演进为共享壳层 + 模板适配
- `CircleGroupSummaryView` 与 `OrganizationNodeSummaryView` 成为子单元统一摘要模型

### 迁移 / 回填

- 旧圈子详情页默认映射为 `通用圈子模板`
- 组织型新主页创建后显式写入 `kind=organization`
- 旧数据没有节点层级时，不强制回填组织树

### 双读 / 双写

- 前端可短期兼容旧 `circleData.sectionConfig`
- 新的模板信息优先由 `Circle.kind` 与 `display_subject_type` 派生
- dev 完成后逐步移除只适用于旧圈子详情的分支逻辑

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 不新增用户可见 feature flag

### 观测

- `group_hub_home_open_count`
- `group_hub_tab_switch_count`
- `group_home_module_error_count`
- `organization_node_open_count`
- `parent_node_aggregate_latency_ms`

### SLO 验证

- 首页头部与主操作区即时可见
- 单模块失败不影响其他模块
- 组织节点页切换和聚合内容首批结果符合性能要求

### 回滚

- 详情模板整体回退到旧详情实现
- 不单独灰度组织模板

## TDD / ATDD 策略

- `T1_schema`
  - Circle kind/template/group summary
  - node summary and aggregation fields
- `T2_module_interaction`
  - 首页模块
  - 双模板页签
  - disabled 管理页面
- `T3_cross_service_integration`
  - 节点内容聚合
  - group summary loading
- `T4_user_journey`
  - 兴趣型详情
  - 组织型详情
  - 组织节点详情

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结详情模板、节点摘要与子单元 typed view | `T1_schema` |
| `P2` | 落地共享壳层和双模板页签 | `T2_module_interaction`, `T4_user_journey` |
| `P3` | 落地群主页与组织节点主页 | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |
| `P4` | 落地父节点聚合与管理页面可见性策略 | `T2_module_interaction`, `T3_cross_service_integration` |

## 未来演进

- 若后续出现第三类模板需求，优先通过模块组合扩展，不直接新增第三套大模板。
- 若首页模块需要更强个性化，再补用户级模块偏好，不改变模板骨架。
- 若节点内容聚合量大，再引入专门读模型，而不是改变页面结构。
