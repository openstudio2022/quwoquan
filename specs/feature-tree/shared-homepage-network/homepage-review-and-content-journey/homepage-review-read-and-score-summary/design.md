# homepage-review-read-and-score-summary 设计

## 设计动因

共享主页的“信任入口”来自口碑摘要，而不是只有一个孤立平均分。  
如果主页口碑模块没有正式设计，常见问题会是：

1. 只有总评分，没有维度心智；
2. 评分摘要和真实口碑模板脱节；
3. 写口碑入口、更多口碑入口和摘要读取互相混杂。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 口碑模板与内容域口碑能力：`content` metadata 和 review summary 读模型

当前详情页已具备评分摘要展示位，因此本设计重点冻结“评分摘要字段、类目维度模板和精选口碑预览”的读取合同。

## 方案对比

### 方案 A：主页只显示一个总评分

优点：

- 读取最轻。

缺点：

- 用户无法判断评分来源与维度；
- 不适合酒店、餐饮、景点、车型等差异化类目；
- 主页难以形成可信口碑心智。

### 方案 B：总评分 + 维度摘要 + 精选口碑预览

优点：

- 能兼顾“快速决策”和“继续深入”；
- 与类目口碑模板天然对齐；
- 写口碑与更多口碑入口也有稳定锚点。

缺点：

- 需要冻结维度摘要和预览字段。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：评分摘要是聚合结果，不是前台即时计算

主页消费的是已发布口碑的聚合读模型，包括：

- 总评分
- 评分数量
- 维度摘要
- 标签或分布摘要

前台不自行重新计算评分。

### D2：维度模板跟主页类目绑定

不同主页类型拥有不同维度模板，例如：

- 酒店
- 餐饮
- 景点
- 商品类

主页只负责读取当前类目对应的维度摘要，不自行硬编码另一套维度规则。

### D3：精选口碑是预览，不等于完整口碑页

主页只展示有限数量的精选口碑摘要和入口：

- 继续看更多口碑
- 写口碑

完整口碑阅读和写入不在本场景承载。

### D4：空态必须可信

暂无口碑时：

- 展示明确空态；
- 保留写口碑入口；
- 不伪造评分或用空值冒充正常聚合。

## metadata / codegen 方案

- `entity/homepage/service.yaml`：冻结 review summary 读取 operation
- `content/post` 或 review 聚合模型：冻结口碑摘要字段
- app 端：评分模块消费统一 summary model

## TDD / ATDD 策略

- `T1_schema`：评分摘要字段和类目模板绑定稳定
- `T2_module_interaction`：评分、维度、精选口碑和空态稳定
- `T4_user_journey`：用户可在主页快速建立口碑心智

## 回滚策略

- 一级回滚：保留总评分与数量，暂停维度摘要
- 二级回滚：保留口碑入口，隐藏精选口碑预览
- 不允许回滚到评分摘要与真实口碑模板长期脱节
