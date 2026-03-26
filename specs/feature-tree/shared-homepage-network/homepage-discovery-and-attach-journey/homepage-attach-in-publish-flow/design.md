# homepage-attach-in-publish-flow 设计

## 设计动因

主页绑定真正有价值的地方，不在 picker 本身，而在发布写入能否形成稳定 canonical fact。  
如果全局发布入口和主页内发布入口各写一套规则，最容易出现的问题是：

1. 口碑绑定规则前后不一致；
2. 主页上下文无法自动带入；
3. 内容发布成功了，但主页挂载字段丢失或不完整。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 内容域写入 metadata：`contracts/metadata/content/post/fields.yaml`、`service.yaml`

当前 app 端已把 `homepage` 纳入 `PublishSettings`，并让主页详情页可上下文进入发布器，因此本设计的重点是冻结“单主页绑定规则、默认带入和发布后回流”的正式合同。

## 方案对比

### 方案 A：主页上下文只停留在 UI，不进入正式写入

优点：

- 实现简单。

缺点：

- 发布后无法稳定回流主页；
- 搜索、详情和内容聚合无法共用 canonical homepage；
- UI 与内容写入出现第二真相源。

### 方案 B：主页绑定进入 `PublishSettings` 与发布 payload 的正式 contract

优点：

- 全局入口和主页内入口共用同一发布器；
- 发布成功即可形成主页引用事实；
- 回流主页聚合与详情读取可稳定建立。

缺点：

- 需要冻结四类内容的绑定规则。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：主页绑定字段进入正式发布 payload

发布 payload 统一承载：

- `primaryHomepageId`
- `primaryHomepageType`
- `primaryHomepageSnapshot`

不再允许长期依赖自由文本主页描述。

### D2：四类内容的绑定规则固定

- `口碑`：必须且只能绑定 1 个主主页
- `笔记 / 作品 / 提问`：可选绑定 1 个主主页

同一内容 baseline 不支持多主页挂载。

### D3：主页内发布入口与全局发布入口共用同一发布器

主页详情页进入发布器时：

- 当前主页默认带入；
- 非口碑场景允许用户更换或移除；
- 口碑场景不允许移除主页。

### D4：发布成功后由主页引用驱动回流聚合

主页不自行生成内容副本，而是消费内容域基于主页引用聚合的结果。  
只有写入成功的主页字段，才能进入主页内容与问答聚合面。

## metadata / codegen 方案

- `content/post/fields.yaml`：冻结主页引用字段
- `content/post/service.yaml`：冻结主页引用为 writable fields
- app `PublishSettings`：统一主页绑定真相源
- `entity` / `content` repository：共享 canonical homepage reference

## TDD / ATDD 策略

- `T1_schema`：主页引用字段和写入 contract 稳定
- `T2_module_interaction`：发布器中主页选择、清除和默认带入稳定
- `T3_cross_service_integration`：发布成功后内容回流主页聚合
- `T4_user_journey`：从主页进入发布器再回到主页的路径成立

## 回滚策略

- 一级回滚：关闭主页内 contextual publish 入口
- 二级回滚：暂停主页写入，只保留无主页发布
- 不允许回滚到“内容已发布但主页引用不一致”的静默状态
