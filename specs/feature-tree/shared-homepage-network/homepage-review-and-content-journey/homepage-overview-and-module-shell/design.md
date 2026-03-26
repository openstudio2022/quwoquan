# homepage-overview-and-module-shell 设计

## 设计动因

主页首屏不是简单拼模块，而是要先建立“这是什么、值不值得继续看、接下来能做什么”的心智。  
如果首屏没有统一 shell，后续会出现：

1. 模块各自加载，各自抢主视觉；
2. 某一个模块失败就把整页拖挂；
3. 发布、写口碑、认领等主操作没有稳定锚点。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 主页详情读模型：`GetHomepageDetail`、`GetHomepageShell`

当前 app 端已经具备主页详情页和模块卡片壳层，因此本设计重点冻结“shell 先于模块、模块独立降级、主操作固定”的结构合同。

## 方案对比

### 方案 A：所有模块直接平铺到详情页

优点：

- 实现最直接。

缺点：

- 首屏不回答主页是什么；
- 模块优先级混乱；
- 单模块失败容易拖累整页。

### 方案 B：独立 shell 承载总览与主操作，模块按能力逐块加载

优点：

- 首屏信息密度和决策效率更高；
- 模块独立加载与错误态更自然；
- 后续聚合模块扩展不破坏主页骨架。

缺点：

- 需要冻结 shell 读模型与模块边界。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：总览 shell 先于模块

首屏必须优先展示：

- 名称
- 类型
- 副标题或地点摘要
- 状态
- 主操作入口

模块结果可以延迟加载，但首页不能没有 shell。

### D2：模块按能力边界分块

主页详情 baseline 模块包括：

- 评分摘要
- 内容/提问预览
- 相关群组
- 治理入口

这些模块必须能独立 loading、独立失败、独立空态。

### D3：主操作位置固定

主操作如：

- 发布
- 写口碑
- 提问
- 认领/维护/上报

必须在 shell 中有稳定位置，不允许随着某个聚合模块成败而漂移。

### D4：模块失败不影响整页可用

任何单模块错误都只能降级本模块，不能让用户失去：

- 主页基础信息
- 关键操作
- 返回路径

## metadata / codegen 方案

- `entity/homepage/service.yaml`：冻结 `GetHomepageShell`
- `_shared/ui_surfaces.yaml`：主页详情 surface 与读取 operation 绑定
- app 端 shell 模型：总览字段与模块预览字段解耦

## TDD / ATDD 策略

- `T1_schema`：shell 字段与模块字段边界稳定
- `T2_module_interaction`：各模块独立 loading / error / empty
- `T4_user_journey`：用户首屏可快速理解主页并继续操作

## 回滚策略

- 一级回滚：关闭非关键模块，只保留总览 shell
- 二级回滚：保留总览与主操作，暂停次级聚合读取
- 不允许回滚到“无 shell 只有堆模块”的详情页结构
