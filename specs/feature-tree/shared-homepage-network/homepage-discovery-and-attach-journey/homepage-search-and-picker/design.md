# homepage-search-and-picker 设计

## 设计动因

主页挂载的第一步不是发布，而是准确选中对象。  
如果主页搜索和选择器没有统一 contract，最常见的问题会是：

1. 同名主页无法区分；
2. 搜索页展示一套字段，选择回填又只返回另一套字段；
3. 发布器被迫额外维护自由文本兜底，破坏 canonical attach。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 搜索入口和主页 metadata：`_shared/app_routes.yaml`、`_shared/ui_surfaces.yaml`

当前 app 已具备主页 picker 页面和主页仓储接口，因此本设计重点冻结“搜索结果字段、选择器返回值和空态/弱网语义”，而不是重新设计搜索系统。

## 方案对比

### 方案 A：搜索结果只显示名称，选择后再补拉详情

优点：

- payload 小。

缺点：

- 同名主页误选率高；
- 选择前无法建立判断；
- 详情和回填会出现两次确认成本。

### 方案 B：搜索结果直接展示足够区分信息，并返回 canonical reference

优点：

- 用户可在列表内完成大部分判断；
- 选择后能直接回填 canonical homepage；
- 与发布器和主页详情可共用数据模型。

缺点：

- 需要冻结结果摘要字段集合。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：搜索结果只展示已发布主页

候选或待审核主页不进入 picker 结果。  
picker 的职责是“帮助用户选正式主页”，不是暴露治理态数据。

### D2：结果摘要字段集固定

最小字段包含：

- 名称
- 类目
- 副标题
- 地点/品牌系列摘要
- 封面
- 评分或状态摘要

目标是足以区分高频同名主页，而不是让用户每次都跳详情再判断。

### D3：选择器返回 canonical reference，不返回自由文本

选择后返回值统一为 canonical homepage reference：

- `id`
- `homepageType`
- `title`
- `subtitle`
- `coverUrl`
- `status`

发布器、详情页和内容写入只消费这份引用，不再保留自由文本主页字段。

### D4：空态与弱网是正式交互，不是异常补丁

- 空结果时给出明确空态与补充主页入口；
- 弱网时先显示 skeleton，再逐步渲染结果；
- 返回选择器后，原页面状态不被重置。

## metadata / codegen 方案

- `entity/homepage/service.yaml`：冻结 `SearchHomepages`
- `_shared/request_context.yaml`：主页 picker page id
- `_shared/ui_surfaces.yaml`：picker surface 与搜索 operation 绑定
- app 端 repository：统一输出 `HomepageSummary` / canonical reference

## TDD / ATDD 策略

- `T1_schema`：搜索 operation、surface 和返回模型字段稳定
- `T2_module_interaction`：picker 搜索、空态、选择回填稳定
- `T4_user_journey`：用户能找到、区分并选中正确主页

## 回滚策略

- 一级回滚：关闭主页挂载入口，但保留主页浏览
- 二级回滚：禁用详情预览，仅保留 picker 选择
- 不允许回滚到自由文本长期替代主页绑定的旧路径
