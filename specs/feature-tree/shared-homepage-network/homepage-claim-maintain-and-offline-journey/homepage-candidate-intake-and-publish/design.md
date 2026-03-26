# homepage-candidate-intake-and-publish 设计

## 设计动因

共享主页网络的起点不是用户浏览，而是把“可能存在的对象”治理成可信正式主页。  
如果候选链路不正式，平台会很快被：

1. 重复主页；
2. 来源不明主页；
3. 未审核就公开的低可信主页

拖垮。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- discovery journey 中的补充主页输入：`missing-homepage-suggestion-and-review`

当前仓库已经有 `entity-service` 的 candidate intake / publish 最小实现，因此本设计重点冻结“统一来源、状态机和发布边界”。

## 方案对比

### 方案 A：用户或抓取结果直接生成正式主页

优点：

- 冷启动最快。

缺点：

- 重复和脏数据不可控；
- 正式主页可信度迅速下降；
- 无法形成长期治理闭环。

### 方案 B：统一 candidate pipeline，再审核发布

优点：

- 所有来源治理一致；
- 正式主页可追溯；
- 与后续认领、下线状态机天然兼容。

缺点：

- 需要运营或审核链路支撑。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：所有来源先入 candidate

来源包括：

- 抓取
- 导入
- 用户补充
- 内容反抽

任何来源都不能跳过 candidate 直接变成正式主页。

### D2：候选状态机显式化

baseline 状态：

- `candidate`
- `pending_verify`
- `published`

未发布前不进入正式搜索结果与主页浏览入口。

### D3：来源证据必须可追溯

候选主页至少记录：

- 来源类型
- 来源提交者或来源系统
- 最小结构化证据

来源缺失或证据不足时，不允许直接发布。

### D4：发布后的主页才进入正式网络

一旦发布：

- 可被搜索
- 可被挂载
- 可被详情页读取

发布动作是主页加入共享网络的正式闸门。

## metadata / codegen 方案

- `entity/homepage/fields.yaml`：candidate、source evidence 字段
- `entity/homepage/service.yaml`：intake / publish operations
- `entity/homepage/errors.yaml`：来源缺失、非法发布等错误码
- app / service codegen：共享同一状态常量

## TDD / ATDD 策略

- `T1_schema`：candidate 状态、来源字段、发布边界稳定
- `T2_module_interaction`：候选提交、审核发布和驳回稳定
- `T3_cross_service_integration`：发布后可被搜索与挂载

## 回滚策略

- 一级回滚：暂停新的 candidate intake
- 二级回滚：暂停 publish 操作，但保留已发布主页
- 不允许回滚到“候选直接公开”的状态
