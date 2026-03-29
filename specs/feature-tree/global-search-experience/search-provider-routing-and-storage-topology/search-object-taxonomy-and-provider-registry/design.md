# search-object-taxonomy-and-provider-registry 设计方案

## 方案对比

### 方案 A：继续用自由字符串

缺点：

- 易拼写漂移。
- codegen 与观测无法稳定追踪。

### 方案 B：metadata 注册的 taxonomy + provider registry

优点：

- 唯一真相源。
- 便于 codegen 和 planner 统一消费。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

- objectType 示例：
  - `chat.contact`
  - `chat.conversation`
  - `chat.message`
- `web.document`
  - `circle.group`
  - `content.post`
  - `entity.homepage`
  - `integration.location_poi`
- registry 至少包含：
  - `objectType`
  - `provider`
  - `executionMode`
  - `defaultSections`
- `toolVisibility`

## metadata / codegen 方案

- `_shared/search/search_objects.yaml`
- registry 需同时描述网页 provider 与趣我圈内部 provider

## TDD / ATDD 策略

- `T1_schema`：taxonomy schema
- `T2_module_interaction`：planner 消费 registry
