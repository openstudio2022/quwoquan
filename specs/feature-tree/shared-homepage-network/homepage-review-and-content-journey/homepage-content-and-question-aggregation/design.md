# homepage-content-and-question-aggregation 设计

## 设计动因

主页要形成社区活性，必须把内容和提问聚合起来，但不能反客为主替代内容域。  
如果没有正式聚合设计，最容易出现两种失控：

1. 主页自己维护一套内容模型；
2. 内容虽已挂载主页，但主页看不到或看法不一致。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 内容域主页引用 contract：`content/post/fields.yaml`、`service.yaml`

当前共享主页已经把 canonical homepage reference 接进发布器与内容写入，因此本设计重点冻结“主页如何按主页引用消费内容和提问聚合结果”。

## 方案对比

### 方案 A：主页复制内容卡片数据做本地拼装

优点：

- 前端表面上灵活。

缺点：

- 主页和内容域很快各有一份真相；
- 回流和排序问题难以治理；
- 字段演进成本高。

### 方案 B：主页只消费内容域按主页引用生成的聚合结果

优点：

- 主页与内容域职责清晰；
- 内容一旦发布，回流路径明确；
- 字段演进只需维护主页引用 contract。

缺点：

- 需要明确 eventual consistency 边界。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：主页聚合只认主页引用字段

进入主页聚合面的前提，是内容具备正式主页引用：

- `primaryHomepageId`
- `primaryHomepageType`

主页不接受自由文本或临时上下文作为聚合依据。

### D2：内容与提问在主页内可区分，但共享同一聚合面

主页聚合 baseline 包含：

- 笔记
- 作品
- 提问

它们可以分 tab 或分 section，但都属于主页聚合视图，不另起一套子产品。

### D3：主页只展示预览，不接管详情

主页模块负责：

- 展示预览卡片
- 展示数量或最近更新
- 导航去内容详情或更多列表

内容正文、问答详情仍属于内容域本体。

### D4：最终一致是正式合同

内容发布成功后，主页聚合允许短暂延迟，但必须：

- 最终可见；
- 不产生重复；
- 不出现“内容显示在主页，但主页引用字段实际不存在”的倒挂。

## metadata / codegen 方案

- `content/post/fields.yaml`：主页引用字段唯一真相源
- `content/post/service.yaml`：写入和读取主字段保持一致
- `entity/homepage/service.yaml`：主页 shell / aggregation 读取契约
- app 端：内容预览模型与主页 summary 同向

## TDD / ATDD 策略

- `T1_schema`：主页引用字段与聚合读取字段稳定
- `T2_module_interaction`：内容/提问模块的 loading、empty、error 稳定
- `T3_cross_service_integration`：发布内容后能回流主页聚合
- `T4_user_journey`：用户从主页继续浏览内容和提问的路径成立

## 回滚策略

- 一级回滚：关闭提问聚合，只保留内容聚合
- 二级回滚：保留聚合入口，暂停预览卡片
- 不允许回滚到主页自建第二套内容真相
