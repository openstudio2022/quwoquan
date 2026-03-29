# local-search-lifecycle-and-account-isolation 设计方案

## 方案对比

### 方案 A：登出即清空

缺点：

- 与当前需求冲突。
- 弱化本地搜索价值。

### 方案 B：长期保留 + 账号隔离 + 用户主动删除

优点：

- 与当前需求一致。
- 复杂度可控。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

- 登出不清空。
- 账号命名空间 = owner + sub account。
- 删除 / 撤回事件同步删索引。
- 低存储设备治理后续独立冻结。

## metadata / codegen 方案

- `_shared/search/search_objects.yaml`
- `messages/conversation/service.yaml`（用于同步 / 删除事件来源）

## TDD / ATDD 策略

- `T2_module_interaction`：账号隔离与删除同步
- `T4_user_journey`：子账号切换后结果隔离
