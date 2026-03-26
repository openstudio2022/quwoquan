# homepage-review-and-content-journey 设计方案

## 设计动因

`homepage-review-and-content-journey/spec.md` 已把主页阅读与回流定义为正式 Journey，但如果没有一版 Journey 级设计，后续实现仍会出现四类失真：

1. 主页会继续退化成“详情卡 + 若干跳转入口”，无法形成稳定的首屏理解心智。
2. 评分摘要、内容聚合、问答聚合与相关群组会各自独立请求和独立展示，模块边界与失败降级不可控。
3. 主页内发布入口若没有与全局发布器共享同一 contract，很快会裂成第二套上下文发布协议。
4. 主页若直接吞掉内容域或群组域的详细治理，未来会重新出现多域边界漂移。

本次 `/design` 的目标，是让主页成为一个真正可商用落地的阅读与回流容器：

- **主页首屏总览 + 评分摘要作为首帧核心**
- **模块化 homepage shell + 模块级独立降级**
- **内容/问答/相关群组采用聚合消费，不重造二级真相源**
- **主页内发布入口与全局发布器共享同一上下文写入协议**

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `shared-homepage-network/spec.md` | 已冻结主页统一骨架、口碑依附主页、相关群组只消费摘要 |
| `homepage-review-and-content-journey/spec.md` | 已冻结范围、异常边界、SLO/KPI 与回滚口径 |
| `homepage-review-and-content-journey/acceptance.yaml` | `J1/J2/J3/R1` 足以承接 plan slices |
| 4 个 L3 scenario spec / acceptance | 已明确最小实施单元：总览壳层、评分摘要、内容问答聚合、主页上下文发布 |
| `shared-homepage-network/design.md` | 已冻结 `entity-service` 为主页域、内容与群组只消费边界 |
| `circle-community` 设计主线 | 群组详细治理不在本 Journey 展开，只消费 related group summary |
| `discovery-content` 发布与聚合主线 | 可复用内容写入、问答写入与内容聚合来源 |

结论：

- `/design` 准入满足。
- 本 Journey 的顺序固定为：`homepage read metadata -> codegen -> overview/review shell -> content/question/group aggregation -> contextual publish -> tests`。
- G1 已实际执行：
  - `make -C quwoquan_service verify-metadata`
  - `make codegen`
  - `make codegen-app`

## G1 基线结果

已执行：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

结果：

- metadata 校验通过
- codegen / codegen-app 基线通过
- 后续对主页读模型、聚合 DTO 和请求 page ids 的新增修改可以按正式生成链路推进

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|---|---|---|
| 大众点评 | 首屏先看评分、标签、精选内容，再继续看详情 | 不吸收只做本地生活目录 |
| 汽车之家 | 车型页中口碑、资讯、论坛并存 | 不吸收垂类参数站式重信息架构 |
| Booking/Airbnb | 信息、评价和行动入口集中在一屏可理解范围内 | 不吸收重交易 CTA 主导的页面节奏 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|---|---|
| `article-display-journey/design.md` | “轻量首帧 + 异步水合 / 模块加载” 的分层方法 |
| `circle-homepage-redesign` | 模块化首页、模块级降级、操作区与摘要区分层 |
| `discovery-content` 聚合能力 | 主页只消费内容与提问聚合，不重造内容域 |

结论：

- 主页必须是 **read-first**，而不是 feed-first。
- 首帧应由总览和评分摘要承接，内容/问答/群组区可以异步补齐。
- 主页详细页不直接承担内容域、群组域的治理和复杂写入，只承担聚合消费与上下文 handoff。

## 方案对比

### 方案 A：信息卡式主页 + 全部内容跳转外部二级页

核心思路：

- 主页只展示基础信息和少量摘要。
- 口碑、内容、提问、群组全部跳外部列表。

优点：

- 实现最轻。
- 主页读模型压力小。

缺点：

- 主页首屏无法形成稳定“读懂 + 继续看”的心智。
- 用户会感觉主页只是一个中转页。
- 发布完成后回流主页的语义会变弱。

### 方案 B：content-first 单列表主页

核心思路：

- 主页本质上是一个带头部的内容 feed。
- 评分和摘要压缩成头部胶囊。

优点：

- 实现直观。
- 可快速复用已有内容流容器。

缺点：

- 用户无法先理解主页的结构化信息和口碑摘要。
- 问答、相关群组和官方信息很容易被埋没。
- 会让主页重新退化成“内容详情上方挂个 header”。

### 方案 C：模块化 homepage shell + 首帧总览/评分摘要 + 异步聚合

核心思路：

- 主页有统一 shell。
- 首帧固定优先加载：总览、评分摘要、主操作。
- 内容、问答、相关群组等模块异步加载、独立降级。
- 主页内发布入口只做上下文 handoff，发布仍走统一发布器。

优点：

- 主页心智清晰，首帧信息密度与后续深读路径兼得。
- 模块化利于跨域聚合和局部失败降级。
- 上下文发布与回流边界清楚。

缺点：

- 需要定义正式的 homepage read model 和 module DTO。
- 要求 entity/content/circle 三域的聚合边界非常清晰。

## 选型决策

**选定方案：方案 C**

决策理由：

1. 主页的首要任务是“让用户读懂一个具体事物”，不是先给用户一个滚动列表。
2. 模块化 shell 能同时满足首屏理解、深度浏览、局部降级和异步聚合。
3. contextual publish 只做 handoff，既保证主页回流，又不会侵入内容域写入真相源。

## 关键设计决策

### KD1：主页读模型分成首帧核心和异步模块

首帧核心：

- `HomepageOverviewView`
- `HomepageScoreSummaryView`
- `HomepagePrimaryActionsView`

异步模块：

- `HomepageReviewHighlightsModule`
- `HomepageContentPreviewModule`
- `HomepageQuestionPreviewModule`
- `HomepageRelatedGroupsModule`
- `HomepageOfficialInfoModule`

规则：

- 首帧核心必须尽量一次可见
- 模块可独立加载、独立失败、独立重试
- 单模块失败不能导致整页失败

### KD2：entity-service 拥有 homepage shell 真相源，但不吞掉内容与群组事实

归属划分：

- `entity-service`
  - 主页主档
  - 主页 shell
  - 评分摘要
  - 相关群组摘要读模型
- `content-service`
  - 笔记/作品/提问/口碑本体
  - 主页引用字段事实
- `circle-service`
  - 群组本体
  - 群组摘要来源

设计原则：

- homepage shell 由主页域消费聚合结果后输出
- 内容本体与群组本体仍分别属于原域
- 主页 UI 不得在 App 层自行拼第二套聚合逻辑作为长期真相源

### KD3：主页总览和评分摘要作为统一首帧

首帧必须回答：

- 这是什么主页
- 评分/口碑如何
- 我下一步能做什么

最小字段建议：

- `displayName`
- `homepageType`
- `locationOrSeries`
- `heroMedia`
- `summaryTags`
- `overallRating`
- `ratingCount`
- `dimensionHighlights`
- `primaryActions`

不允许：

- 首屏只有名称和封面
- 评分摘要被压到二屏之后

### KD4：主页内容与提问采用“聚合预览 + 进入来源域”

主页内展示：

- 内容预览
- 提问预览
- 类型筛选或计数摘要

进入后：

- 仍进入内容详情页 / 提问详情页 / 相关列表

不采用：

- 在主页域复制一套内容详情协议
- 在主页域复制评论或群组治理逻辑

### KD5：相关群组只展示 summary，不展示治理能力

`HomepageRelatedGroupsModule` 只负责：

- 群组名称
- 群组类型
- 成员数
- 活跃度
- 加入状态摘要

不负责：

- 群组详情治理
- 群角色与群权限
- 组织树规则

### KD6：主页内发布入口只是 contextual handoff

允许从主页直接发：

- 笔记
- 作品
- 提问
- 口碑

但：

- 统一走已有发布器
- 当前主页自动带入为上下文
- 发布完成后通过 canonical homepage reference 回流聚合

不新增：

- 主页专属编辑器
- 主页内嵌写作页
- 第二套 `CreatePost` 变体

### KD7：评分摘要只读，不在本 Journey 定义评分写入

本 Journey 只消费：

- 总评分
- 维度摘要
- 标签分布
- 精选口碑摘要

评分写入：

- 继续属于内容发布和口碑模板主线
- 本 Journey 不在 UI 或 entity-service 新造一套评分写入口

### KD8：metadata / codegen 方案

| 目录 | 设计动作 | 产物 |
|---|---|---|
| `_shared/app_routes.yaml` | 新增或扩展 `homepageDetail` | `app_route_paths.g.dart` |
| `_shared/ui_surfaces.yaml` | 新增 `homepageDetail`、review/content/question/group module surfaces | `app_ui_surfaces.g.dart` |
| `_shared/request_context.yaml` | 新增 homepage detail / module / contextual publish page ids | `*_request_page_ids.g.dart` |
| `entity/homepage/fields.yaml` | 新增 `HomepageOverviewView`、`HomepageScoreSummaryView`、各类 module DTO | entity generated DTO |
| `entity/homepage/service.yaml` | 新增 `GetHomepageShell`、`GetHomepageReviewSummary`、`GetHomepageRelatedGroups` 等 | entity API metadata |
| `content/post/service.yaml` | 冻结 `ListHomepageRelatedContent`、`ListHomepageQuestions` 或等价查询 contract | content API metadata |
| `entity/homepage/ui_config.yaml` | 冻结模块顺序、优先级、是否首帧加载、类目差异配置 | app UI config |

## metadata / codegen 方案

实施顺序固定为：

1. `_shared` 的 route / surface / request context
2. `entity/homepage` 的 shell / review / module DTO
3. `content/post` 与 `circle` 的主页聚合查询 contract
4. 运行 G1：
   - `make -C quwoquan_service verify-metadata`
   - `make codegen`
   - `make codegen-app`
5. 再进入 entity repository、homepage provider、UI modules

当前 G1 基线已在本轮 `/design` 实际执行并通过。

## 字段演进、迁移/回填、必要时双读双写方案

### 字段演进

- `零散主页 header 字段` -> `HomepageOverviewView`
- `零散评分卡字段` -> `HomepageScoreSummaryView`
- `主页里临时拼装的内容列表` -> `HomepageContentPreviewModule`
- `主页里临时拼装的群组卡片` -> `HomepageRelatedGroupsModule`

### 迁移 / 回填

- 已存在 `primaryEntityId` 的内容可以直接进入主页内容/提问聚合
- 已存在口碑记录的主页可离线回填评分摘要和维度摘要
- 对于没有内容或没有评分的主页，优先显示空态，不阻塞整体上线

### 双读 / 双写

- **不做内容本体双写**
- entity-service 读模型可在短期双读旧摘要字段和新 module DTO，直到 UI 全面切换
- 退出条件：
  - UI 不再读取旧的散落 header / review / content 临时字段
  - 所有首页模块都从 homepage shell / module DTO 读取

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- `enable_homepage_read_shell`
- `enable_homepage_review_summary`
- `enable_homepage_contextual_publish`

策略：

- 先开 read shell
- 再开 review summary 与 content/question/group modules
- 最后开 contextual publish

### 观测

- `homepage_shell_first_paint_ms`
- `homepage_overview_load_failure_count`
- `homepage_review_summary_load_failure_count`
- `homepage_content_module_load_failure_count`
- `homepage_related_groups_module_load_failure_count`
- `homepage_contextual_publish_handoff_success_count`

### SLO 验证

- 首屏骨架 `p95 < 300ms`
- 关键摘要可见时间 `p95 < 1.2s`
- 评分摘要或内容首批结果 `p95 < 1.5s`

### 回滚

- 一级回滚：关闭 contextual publish，仅保留只读主页
- 二级回滚：关闭 review summary 或 related modules，只保留 overview shell
- 不允许把主页整体回退成纯静态卡片页

## TDD / ATDD 策略

### T1：schema / metadata

- shell DTO、module DTO、route/surface/page ids、ui config

### T2：module interaction

- overview shell、review summary、content preview、groups preview、contextual publish handoff

### T3：cross service integration

- entity shell 消费 content / circle 聚合结果
- contextual publish 后的主页回流

### T4：user journey

- 用户进入主页并在首屏理解对象
- 用户浏览口碑/内容/提问/群组
- 用户从主页发布并回到主页

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 验证层 |
|---|---|---|
| `P1` | 冻结 homepage shell / module metadata | `T1` |
| `P2` | 建立 codegen baseline | `T1` |
| `P3` | 落 overview shell 与 review summary | `T2`, `T4` |
| `P4` | 落 content/question/related groups 聚合 | `T2`, `T3`, `T4` |
| `P5` | 落 contextual publish 与回流 | `T2`, `T3`, `T4` |
| `P6` | 加固观测、回滚与 Journey 回归 | `T3`, `T4` |

## 未来演进

- 允许按类目定制更细粒度模块顺序，但继续由 `ui_config` 统一驱动
- 引入“对比主页”能力，但不侵入当前单主页 read shell
- 让 related groups 按主页类目或关系强度做更智能排序，但仍只输出 summary
- 在主页里增加 AI 摘要或亮点归纳时，只能消费现有评分与内容事实，不生成第二真相源
