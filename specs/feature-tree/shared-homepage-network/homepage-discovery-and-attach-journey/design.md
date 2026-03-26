# homepage-discovery-and-attach-journey 设计方案

## 设计动因

`homepage-discovery-and-attach-journey/spec.md` 已把“发现主页并挂载主页”的用户旅程冻结为正式 `L2_journey`，但如果没有一版 Journey 级设计，后续开发仍会发生四类漂移：

1. 搜索入口会继续分裂成“全局搜索一套、发布器一套、主页内入口一套”，用户无法建立稳定心智。
2. 主页选择结果会停留在松散文本或临时对象，导致内容写入、主页回流和详情预览各自维护第二真相源。
3. 搜索不到主页时，补充主页很容易退化回“自由文本描述”，破坏主页网络的可治理性。
4. 发布成功与主页回流之间若没有明确的跨域合同，就会出现“内容已发出，但主页没挂上”的静默不一致。

本次 `/design` 的目标，是把本 Journey 收口为一套真正可实施的方案：

- **统一 `SearchHomepages` typed contract**
- **专用主页选择器 route + 与全局搜索复用同一结果模型**
- **补充主页进入候选态，而不是自由文本替代**
- **内容域单写主页引用字段，主页域异步聚合回流**

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `shared-homepage-network/spec.md` | 已冻结主页挂载契约、口碑必绑主页、主页候选与已发布状态边界 |
| `homepage-discovery-and-attach-journey/spec.md` | 已冻结范围、SLO/KPI、异常与回滚口径 |
| `homepage-discovery-and-attach-journey/acceptance.yaml` | `J1/J2/J3/R1` 足以承接 plan slices |
| 4 个 L3 scenario spec / acceptance | 已明确最小实施单元：搜索选择、补充主页、详情预览、发布挂载 |
| `shared-homepage-network/design.md` | 已冻结 `entity-service` 作为主页域、主页挂载作为内容锚点、软下线与认领不在本 Journey 展开 |
| `global-search-experience/cross-domain-search-journey/design.md` | 已冻结 route-driven 搜索壳层与 typed 搜索 contract 的总体方法，可复用给主页搜索结果面 |
| `discovery-content` 现有发布主线 | 可复用统一发布器，不重造第二套编辑器 |

结论：

- `/design` 准入满足。
- 本 Journey 的实施顺序固定为：`_shared metadata -> homepage search/attach metadata -> codegen -> picker/detail/publish handoff -> content/entity aggregation -> tests`。
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
- 当前仓库生成链路健康，说明本 Journey 后续 metadata/codegen 改动可以按正式链路推进

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|---|---|---|
| 小红书 | 发布时搜索并关联具体事物、从详情上下文继续发布 | 不吸收标签式弱绑定和自由文本补位 |
| 大众点评 | 搜地点后直接进入稳定主页，主页是长期锚点 | 不吸收只做目录页、不做内容回流 |
| Booking/Airbnb | 搜索结果提供足够区分信息，减少错选 | 不吸收重交易预订流和供应侧后台 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|---|---|
| `global-search-experience` | route-driven 搜索壳层、typed result model、metadata-first 写法 |
| `discovery-content` 发布器 | 统一编辑器与发布动作，不额外新建“主页专属发布器” |
| `shared-homepage-network/design.md` | `entity-service` 作为主页主档与读模型归属 |

结论：

- 主页搜索不能只做 UI picker，而必须有正式搜索 contract。
- 发布器不能自己保存一份“主页自由文本”，必须只认 canonical homepage reference。
- 主页回流不应走同步双写事务，而应由内容域事实写入后驱动主页读模型异步聚合。

## 方案对比

### 方案 A：发布器内本地搜索 + 自由文本兜底

核心思路：

- 发布器自己调一个轻量搜索接口。
- 搜不到主页时允许用户手输名字继续发内容。
- 内容侧保存自由文本和可选主页 id。

优点：

- 改动小。
- UI 上可以很快做出来。

缺点：

- 自由文本会重新成为第二真相源。
- 主页详情、主页聚合和搜索结果无法稳定回流同一对象。
- 口碑“必须绑定主页”会被自由文本直接破坏。

### 方案 B：所有主页选择都收进全局搜索壳层

核心思路：

- 不做独立主页选择器。
- 无论是发布器、内容卡还是主页入口，都跳到全局搜索，再从全局搜索选主页。

优点：

- 入口统一。
- 壳层复用度高。

缺点：

- attach 场景会被全局搜索其它对象打断。
- 发布器需要额外保留跨页编辑上下文，交互成本更高。
- “搜不到主页时补充主页再回到发布器”的路径更长更脆弱。

### 方案 C：独立主页选择器 route + 复用同一 `SearchHomepages` contract

核心思路：

- attach 场景有独立 `HomepagePickerPage`。
- 全局搜索里的主页结果与 picker 复用同一 `SearchHomepages` typed contract。
- 搜不到主页时，进入 `SuggestHomepagePage`，提交后只进入候选态。
- 发布器只写 canonical homepage reference；主页聚合异步消费内容事件。

优点：

- attach 场景最短、最稳，不会被其它域结果打断。
- 全局搜索与发布器依然共用同一主页搜索真相源。
- 主页引用、详情预览、发布回流可以用一套 typed contract 贯通。

缺点：

- 需要同时补齐 `_shared` metadata、主页搜索 contract、内容写入 contract 和异步聚合。
- 需要清理任何旧的自由文本附着写法。

## 选型决策

**选定方案：方案 C**

决策理由：

1. attach 是高频高确定性场景，必须比全局搜索更短路径。
2. 主页网络的可信度依赖 canonical reference，不能容忍自由文本长期存在。
3. 复用同一 `SearchHomepages` contract，可以同时满足“attach 场景最短路径”和“全局搜索统一真相源”。
4. 内容域写事实、主页域做异步聚合，最符合现有 metadata-first 和跨域边界约束。

## 关键设计决策

### KD1：主页搜索 contract 统一为 `SearchHomepages`

Journey 内正式 contract：

- `SearchHomepages`
- `GetHomepageDetail`
- `SuggestHomepageCandidate`

正式结果模型：

- `HomepageSearchItemView`
- `HomepageDetailPreviewView`
- `HomepageReferenceView`

规则：

- attach 场景和全局搜索主页结果共用 `HomepageSearchItemView`
- 发布写入只认 `HomepageReferenceView`
- 主页详情和结果预览都由 `GetHomepageDetail` / `HomepageDetailPreviewView` 承接，不允许 UI 自己拼装摘要

### KD2：attach 场景采用独立 `HomepagePickerPage`，不是复用全局搜索整页

路由策略：

- `HomepagePickerPage`：服务发布器和 attach 型入口
- `HomepageDetailPage`：主页详情
- `SuggestHomepagePage`：补充主页最小表单

同时：

- 全局搜索若要展示主页结果，消费相同 `SearchHomepages` contract
- 但 attach 场景默认不走全局搜索整页，避免被其他域结果打断

### KD3：内容域只写一份 canonical homepage reference

内容写入事实字段建议冻结为：

- `primaryEntityId`
- `primaryEntityType`
- `primaryEntitySnapshot`

其中：

- `primaryEntityId` 是真正外键语义
- `primaryEntityType` 用于类目快速分流
- `primaryEntitySnapshot` 只作为发布完成后列表和回流首帧所需的轻量展示快照

不保留：

- 自由文本主页名
- 第二套手写主页 chip 数据
- 发布器本地的永久化对象缓存字段

### KD4：补充主页只进入候选态，不直接生成正式主页

提交结果：

- 写入 `candidate / pending_verify`
- 返回一个 `suggestionReceiptId`
- 恢复原发布上下文

不允许：

- 补充主页后立即作为正式搜索结果返回
- 用“用户刚补充”的候选记录绕过审核直接给其它用户挂载

### KD5：口碑与其他内容的挂载规则统一但不相同

统一规则：

- 四类内容都走同一发布器
- 都使用同一主页选择器和同一 `HomepageReferenceView`

差异规则：

- `口碑`：必须且只能绑定 1 个主主页
- `笔记 / 作品 / 提问`：可不绑定，也可绑定 1 个主主页

这两个规则都必须在：

- UI 校验
- App contract
- content metadata
- 服务端写入校验

四层同时成立。

### KD6：主页回流采用“内容域写事实，主页域异步聚合”

写入链路：

1. 发布器提交内容
2. `content-service` 写入 canonical homepage reference
3. content 事件或投影驱动主页聚合刷新
4. `entity-service` 读模型更新主页内容区 / 问答区 / 口碑区

不采用：

- content 和 entity 的同步双写事务
- UI 发布成功后本地假写主页计数作为长期事实

允许：

- 发布成功后主页聚合短暂最终一致
- UI 在返回主页时先用 optimistic local item 展示首帧，再等服务器聚合刷新覆盖

### KD7：composer 上下文必须完整可恢复

需要保留的上下文：

- query
- 已输入正文
- 已选媒体
- 内容类型
- 已选主页
- 从哪个页面进入发布器

恢复原则：

- picker 返回不丢失编辑内容
- suggest page 返回不丢失编辑内容
- detail preview 返回不丢失 query 与已选主页

### KD8：metadata / codegen 方案

| 目录 | 设计动作 | 产物 |
|---|---|---|
| `_shared/app_routes.yaml` | 新增 `homepagePicker`、`homepageDetail`、`suggestHomepage` | `app_route_paths.g.dart` |
| `_shared/ui_surfaces.yaml` | 新增 picker/detail/suggest surfaces | `app_ui_surfaces.g.dart` |
| `_shared/request_context.yaml` | 新增 picker/detail/suggest page ids 与 publish attach context ids | `*_request_page_ids.g.dart` |
| `entity/homepage/fields.yaml` | 新增 `HomepageSearchItemView`、`HomepageReferenceView`、`HomepageDetailPreviewView`、`HomepageCandidateSuggestion` | entity generated DTO |
| `entity/homepage/service.yaml` | 新增 `SearchHomepages`、`GetHomepageDetail`、`SuggestHomepageCandidate` | entity API metadata |
| `content/post/fields.yaml` | 新增 `primaryEntityId`、`primaryEntityType`、`primaryEntitySnapshot` | content DTO / projection |
| `content/post/service.yaml` | 冻结四类内容的主页绑定写入语义 | content API metadata |

## metadata / codegen 方案

本 Journey 的正式设计顺序：

1. `_shared` route / surface / request context
2. `entity/homepage` 的 search / detail / suggestion contract
3. `content/post` 的 canonical homepage reference fields
4. 运行 G1：
   - `make -C quwoquan_service verify-metadata`
   - `make codegen`
   - `make codegen-app`
5. 再进入 picker、detail、suggest、publish attach UI 和 provider

当前 G1 基线已在本轮 `/design` 实际执行并通过。

## 字段演进、迁移/回填、必要时双读双写方案

### 字段演进

- `自由文本对象名` -> `primaryEntitySnapshot.displayName`
- `临时对象 id` -> `primaryEntityId`
- `发布器本地 attach map` -> `HomepageReferenceView`

### 迁移 / 回填

- 历史内容若已有稳定对象 id，可回填到 `primaryEntityId`
- 无稳定对象 id 的历史文本，不在本 Journey 自动升级为主页绑定
- 新的主页 attach 入口上线后，不再允许新内容继续写自由文本主页

### 双读 / 双写

- **不做跨服务同步双写**
- 内容写路径只写 content canonical reference
- 主页聚合采用异步消费内容事实
- 旧自由文本如必须短期兼容，仅允许 read fallback，不允许继续 write

退出条件：

- 所有新内容写入都只经过 canonical homepage reference
- UI、Repository、服务端校验均不再依赖自由文本 attach

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- `enable_homepage_attach`
- `enable_homepage_suggest`
- `enable_homepage_attach_from_homepage_detail`

策略：

- 先开 picker + attach
- 再开 suggest
- 最后开主页详情页内的上下文发布入口

### 观测

- `homepage_search_query_latency_ms`
- `homepage_search_empty_result_count`
- `homepage_picker_selection_success_count`
- `homepage_attach_write_failure_count`
- `homepage_attach_return_flow_latency_ms`
- `homepage_suggest_submit_failure_count`

### SLO 验证

- 搜索首批结果 `p95 < 800ms`
- picker 可交互时间 `p95 < 1.2s`
- attach 上下文带入额外开销 `p95 < 300ms`
- attach 写入成功率 `>= 99%`

### 回滚

- 一级回滚：关闭 `enable_homepage_attach`，恢复无主页挂载发布
- 二级回滚：关闭 `enable_homepage_suggest`，保留 picker 但关闭补充主页
- 不允许回滚到“口碑可不绑主页”的旧语义

## TDD / ATDD 策略

### T1：schema / metadata

- 校验 route / surface / request context 归属
- 校验 `SearchHomepages`、`HomepageReferenceView`、`primaryEntityId` 等 metadata

### T2：module interaction

- picker 搜索、结果选择、detail preview、suggest page 返回
- 发布器上下文恢复与主页 chip 更新

### T3：cross service integration

- content 写入 canonical reference
- entity 聚合消费内容事实
- attach 失败与回流延迟的异常路径

### T4：user journey

- 发布笔记/作品/提问并挂主页
- 发布口碑必须选主页
- 搜不到主页 -> 补充主页 -> 返回发布器

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 验证层 |
|---|---|---|
| `P1` | 冻结 route / surface / request context 与 search metadata | `T1` |
| `P2` | 建立 codegen baseline | `T1` |
| `P3` | 落主页 picker / detail / suggest | `T2`, `T4` |
| `P4` | 落发布器 attach 规则和 canonical write path | `T2`, `T3`, `T4` |
| `P5` | 打通 entity 聚合回流、观测和回滚 | `T3`, `T4` |

## 未来演进

- 支持多主页挂载，但只在 canonical homepage reference 成熟后再进入
- 在 picker 中加入地理优先、品牌系列优先和别名召回增强
- 引入 OCR / AI 推荐主页，但只能作为建议，不可替代用户确认
- 全局搜索把 homepage 正式提升为独立结果域时，继续复用本 Journey 已冻结的 `SearchHomepages` contract
