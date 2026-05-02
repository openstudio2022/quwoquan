# homepage-offline-report-and-history-retention 设计

## 设计动因

现实世界里的酒店、门店、景点和其他实体会自然停止运营，但共享主页不能因此失去记录锚点。  
如果没有正式的 offline contract，系统很容易回到两种错误：

1. 直接删除主页；
2. 或者只是文案写“已关闭”，但搜索、详情和记录内容表现都不一致。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 内容和群组消费方：`content`、`circle` 聚合摘要

当前仓库已具备状态上报、审核与主页 `offline` 状态更新，因此本设计重点冻结“上报原因、软下线展示与记录保留”的正式合同。

## 方案对比

### 方案 A：下线即删除或深度隐藏

优点：

- 表面上最干净。

缺点：

- 记录内容和口碑失去锚点；
- 用户无法理解为什么链接失效；
- 平台可信度受损。

### 方案 B：软下线并保留记录

优点：

- 主页记录、口碑和内容可继续访问；
- 搜索和推荐可控降级；
- 与共享主页“长期锚点”定位一致。

缺点：

- 需要冻结状态原因和展示策略。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：下线通过显式 status report 触发

允许发起者包括：

- 普通用户
- 已认领维护者
- 平台运营

但都必须先进入 status report / review，而不是直接改主页状态。

### D2：主页进入 `offline` 后仍保留原 URL 和记录

保留范围包括：

- 原主页 URL
- 记录内容
- 记录口碑
- 相关群组摘要

不允许硬删除作为 baseline 回滚手段。

### D3：搜索与推荐可降级，但不可阻断记录访问

`offline` 后：

- 搜索曝光和推荐曝光可以降级；
- 主页详情仍可访问；
- 详情页应展示原因标签和状态提示。

### D4：恢复是受控能力，不是前台直接切换

本期允许状态机为未来恢复预留空间，但不在前台开放复杂恢复后台。  
错误下线只能通过显式审核恢复，不允许 silently flip。

## metadata / codegen 方案

- `entity/homepage/fields.yaml`：offline status、report reason、report status
- `entity/homepage/service.yaml`：create / review status report
- `entity/homepage/errors.yaml`：非法上报、越权审核等错误码
- app 端：上报页、详情页 offline badge 与原因标签

## TDD / ATDD 策略

- `T1_schema`：offline 状态和原因字段稳定
- `T2_module_interaction`：上报、审核和详情页状态展示稳定
- `T3_cross_service_integration`：offline 后记录内容、口碑和群组摘要仍可见
- `T4_user_journey`：用户可上报并继续浏览记录页

## 回滚策略

- 一级回滚：关闭前台下线上报入口
- 二级回滚：暂停新的 offline 审核通过动作
- 不允许回滚到硬删除主页
