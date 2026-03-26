# homepage-entry-and-preview 设计

## 设计动因

`homepage-entry-and-preview/spec.md` 已冻结“先看主页摘要，再决定是否进入详情”的最小用户语义，但如果没有单独设计，落地时很容易出现三套不一致路径：

1. 搜索结果自己跳详情；
2. 内容卡片自己跳详情；
3. 发布器又维护一套不同的预览/返回逻辑。

这会直接造成上下文丢失、返回不可预期，以及主页详情被不同入口打成多个语义版本。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- app 路由唯一真相源：`contracts/metadata/_shared/app_routes.yaml`
- surface 真相源：`contracts/metadata/_shared/ui_surfaces.yaml`

当前实现基线已经具备主页详情页与 route extra 能力，因此本设计只冻结“入口、预览摘要和返回上下文”的统一合同，不再引入中间页或第二套路由。

## 方案对比

### 方案 A：各入口直接自己跳详情

优点：

- 实现快。

缺点：

- 返回路径和 route extra 很快分叉；
- 搜索、内容、发布器会维护三套详情跳转规则；
- 无法稳定保留原上下文。

### 方案 B：统一详情 route + 统一预览摘要 + 统一返回 contract

优点：

- 详情入口唯一；
- 不同入口只负责传入上下文，不重写详情逻辑；
- 详情加载失败时也能统一回退。

缺点：

- 需要冻结 route extra 与上下文结构。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：主页详情 route 只有一个

统一使用主页详情 route 承载：

- 搜索结果进入详情；
- 内容卡片进入详情；
- 发布器或选择器中的预览进入详情。

各入口只允许传入 route extra，不允许各自再做业务 path 拼接。

### D2：预览摘要使用同一份 `HomepageSummary`

进入详情前可显示的最小预览信息统一为：

- 名称
- 类目
- 副标题或位置摘要
- 封面
- 状态/评分摘要

这份摘要既服务结果卡，也可作为详情页首帧占位。

### D3：返回上下文显式保留

需要保留的上下文包括：

- 搜索 query 与当前 tab；
- 发布器中的已选主页或编辑上下文；
- 内容卡片来源的浏览路径。

详情页不自己猜测返回逻辑，而是消费入口传入的上下文。

### D4：详情失败时统一回退

若详情加载失败：

- 用户可直接返回上一步；
- 选择器场景允许退回“仅选择、不看详情”的保守路径；
- 不允许因为详情失败阻断主发布链路。

## metadata / codegen 方案

- `_shared/app_routes.yaml`：主页详情 route 唯一化
- `_shared/ui_surfaces.yaml`：主页详情 surface 与操作绑定
- `_shared/request_context.yaml`：详情 page id 与 request context 绑定
- app 端 route extra：统一承载 `selectionMode`、`initialSummary` 和返回语义

## TDD / ATDD 策略

- `T1_schema`：route / surface / request context 绑定正确
- `T2_module_interaction`：不同入口都能进入同一详情页
- `T4_user_journey`：进入详情后返回原上下文不丢失

## 回滚策略

- 一级回滚：关闭详情预览入口，仅保留主页选择
- 二级回滚：保留详情页浏览，但暂停从发布器中进入详情
- 不允许回滚到多入口各自维护详情 route 的状态
