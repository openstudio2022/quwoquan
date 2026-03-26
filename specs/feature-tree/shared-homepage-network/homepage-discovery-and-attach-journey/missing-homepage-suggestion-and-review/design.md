# missing-homepage-suggestion-and-review 设计

## 设计动因

主页搜索的空态不是流程终点，而是补齐主页网络的入口。  
如果“没搜到主页”后只能返回发布器，用户会被迫：

1. 放弃主页绑定；
2. 用自由文本临时替代主页；
3. 或者彻底中断发布。

这会让共享主页网络在冷启动阶段持续失血。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 候选主页治理输入：`homepage-claim-maintain-and-offline-journey/homepage-candidate-intake-and-publish`

当前实现已有补充主页页面和主页候选 intake 能力，因此本设计只冻结“最小表单、candidate 边界和返回当前上下文”的标准合同。

## 方案对比

### 方案 A：允许自由文本继续发布

优点：

- 发布链路阻力最低。

缺点：

- 长期形成第二套非 canonical 主页引用；
- 后续无法稳定回流主页聚合；
- 用户会误以为文本等于主页。

### 方案 B：补充主页进入 candidate pipeline，并返回原上下文

优点：

- 不打断用户；
- 不破坏主页治理；
- 与候选审核、正式发布链路完全一致。

缺点：

- 需要设计最小必填字段和提交后反馈。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：补充主页只能生成 candidate，不能直接公开

补充主页提交后进入：

- `candidate`
- `pending_verify`

审核通过前：

- 不进入正式搜索结果；
- 不作为正式主页公开浏览；
- 不允许绕过审核直接挂载成公开主页。

### D2：表单只收最小必要信息

baseline 最小字段：

- 名称
- 类型
- 城市 / 地址
- 副标题或补充说明
- 分类标签

目的是快速补录，不是让前台承担完整运营建档。

### D3：提交后必须回到当前上下文

需要被保留的上下文：

- 当前搜索 query；
- 发布器中已写内容；
- 当前入口来源。

失败时必须保留表单内容，允许直接重试。

### D4：重复与近似结果优先提示，而不是强阻断

在提交前或提交后可做重复提示，但 baseline 不要求复杂合并流程。  
只要不让 candidate 直接公开，重复治理可以后置到审核阶段。

## metadata / codegen 方案

- `entity/homepage/service.yaml`：冻结 `SuggestHomepageCandidate` / `IntakeHomepageCandidate`
- `entity/homepage/fields.yaml`：冻结 candidate 必填字段与来源字段
- `_shared/request_context.yaml`：补充主页 page id 与 operation 绑定
- app 端：suggest page 和返回上下文 contract

## TDD / ATDD 策略

- `T1_schema`：candidate 状态与 suggestion 字段稳定
- `T2_module_interaction`：空态补充主页、失败保留表单、返回上下文
- `T4_user_journey`：搜不到主页时可连续完成补充并回到主流程

## 回滚策略

- 一级回滚：临时隐藏补充主页入口
- 二级回滚：保留表单但关闭提交
- 不允许回滚到自由文本长期替代主页绑定
