# homepage-contextual-publish-entry 设计

## 设计动因

主页要形成社区闭环，就必须允许用户在看到主页后直接继续贡献内容。  
如果主页内发布入口不是共享发布器的一层上下文封装，而是单独的新入口，就会立刻出现：

1. 主页内外两套发布规则；
2. 当前主页无法默认带入；
3. 发布后回到主页的语义不稳定。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 发布器主页挂载合同：`homepage-attach-in-publish-flow`

当前 app 端已从主页详情进入共享发布器并可默认带入主页，因此本设计只冻结“主页上下文入口、带入规则和回流语义”。

## 方案对比

### 方案 A：主页内做独立发布器

优点：

- 表面上更像“主页专属创作入口”。

缺点：

- 与全局发布器分叉；
- 主页挂载规则重复实现；
- 后续内容类型扩展成本高。

### 方案 B：主页内入口只是共享发布器的 contextual wrapper

优点：

- 规则唯一；
- 当前主页默认带入简单稳定；
- 与主页回流和 canonical attach 完全一致。

缺点：

- 需要冻结主页入口 extra 与返回语义。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：主页内入口和全局入口共用同一发布器

主页内只决定：

- 当前主页是否默认带入；
- 当前动作是发笔记、作品、提问还是口碑；
- 完成后返回主页还是继续浏览。

编辑器、发布设置和写入 payload 均复用全局发布器。

### D2：主页上下文默认带入，但不改变绑定规则

- 口碑：默认且必须绑定当前主页
- 笔记 / 作品 / 提问：默认带入当前主页，但允许调整

主页内入口不产生新的绑定语义。

### D3：返回主页语义是显式 contract

发布成功后：

- 可以回到当前主页；
- 或停留在继续浏览状态；
- 但都必须保证主页回流结果最终可见。

失败时必须保留内容和主页上下文。

### D4：主页内入口属于主页 shell 的主操作之一

主页内发布入口应与：

- 写口碑
- 提问
- 认领/维护

共同组成主页主操作层，不埋在聚合模块深处。

## metadata / codegen 方案

- `_shared/ui_surfaces.yaml`：主页 contextual publish surface
- `content/post/service.yaml`：主页引用写入 contract
- app route extra：主页进入发布器的默认 homepage reference

## TDD / ATDD 策略

- `T1_schema`：主页上下文带入字段与 surface 绑定稳定
- `T2_module_interaction`：主页主操作入口与发布器打开稳定
- `T3_cross_service_integration`：发布后主页回流成立
- `T4_user_journey`：从主页直接发内容并回到主页主链路成立

## 回滚策略

- 一级回滚：关闭主页内发布入口
- 二级回滚：保留主页上下文带入，但隐藏“发布后返回主页”行为
- 不允许回滚到主页内外两套发布器并行
