# local-chat-search-contract 设计方案

## 设计动因

本 Scenario 要解决的不是“聊天里能不能搜”，而是把聊天对象正式收口为统一搜索体系中的 `local_only` 对象，并让 Journey、页面与业务层都不再继续暴露聊天域自有的产品语义接口。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `local-chat-search-contract/spec.md` | 已冻结本地聊天搜索对象边界、生命周期与账号隔离规则 |
| `cross-domain-search-journey/design.md` | Journey 已明确只消费 canonical `search(request)` |
| `search-provider-routing-and-storage-topology/*` | `local_only`、provider registry 与 canonical contract 由上游治理 L2 提供 |

## 方案对比

### 方案 A：继续沿用云侧聊天搜索接口

优点：

- 改动最少。

缺点：

- 与“聊天对象端侧搜索”的新前提冲突。
- 继续把执行位置暴露到产品接口层。

### 方案 B：每个页面自行接本地列表过滤

优点：

- 视觉改造成本低。

缺点：

- 无法形成统一对象契约。
- 账号隔离、删除同步和 observability 会继续分散。

### 方案 C：canonical `search(request)` + 本地聊天 provider

优点：

- 与统一搜索 contract 完全一致。
- 能同时满足离线、弱网和高并发成本要求。
- 生命周期与账号隔离可统一治理。

缺点：

- 需要补本地 snapshot / index 结构与删除同步规则。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：聊天对象作为 `local_only` searchable object

- `chat.contact`
- `chat.conversation`
- `chat.message`

这三类对象全部通过本地 provider 暴露，不再把云侧搜索 operation 作为产品主 contract。

### KD2：本地聊天搜索基于 snapshot + index

- snapshot 来源：现有会话、消息、成员与联系人同步读取。
- index 负责 query / highlight / sorting。
- Journey 只消费统一 `SearchHit`，不直接依赖 snapshot 结构。

### KD3：账号隔离与删除同步是 contract，不是实现细节

- 登出不清空。
- 切换子账号必须切分本地搜索命名空间。
- 消息撤回、删除或用户主动清理时，同步删索引。

### KD4：不冻结低存储设备治理阈值

- 本期只冻结“后续单独治理”，不在此 Scenario 内定义自动淘汰阈值。
- 该缺口不阻塞本次 baseline。

## metadata / codegen 方案

- `_shared/search/search_objects.yaml`：
  - 注册 `chat.contact / chat.conversation / chat.message`
  - execution mode = `local_only`
- `_shared/search/search_contract.yaml`：
  - 统一 `SearchRequest / SearchResponse / SearchHit`
- `messages/conversation/service.yaml`：
  - 不再把聊天搜索 operation 作为产品主入口
  - 仅保留本地 snapshot 建立所需的同步 / 读取契约

## 字段演进、迁移/回填、必要时双读双写方案

### 字段演进

- `联系人 / 社交关系 / 聊天记录` 的散乱 UI 语义 -> `chat.contact / chat.conversation / chat.message`

### 迁移 / 回填

- 旧搜索页消费聊天结果时，统一迁移到 canonical `SearchHit`
- 若本地已有聊天缓存，允许构建一次 index 回填

### 双读 / 双写

- 不引入聊天搜索结果双写
- 只允许 snapshot / index 的本地双层结构

## feature flag、观测、SLO 验证与回滚方案

- 不新增业务 feature flag
- 观测：
  - `global_search_local_index_hit_count`
  - `global_search_local_index_delete_sync_count`
  - `global_search_local_index_namespace_switch_count`
- 回滚：
  - 整体回退到旧搜索实现

## TDD / ATDD 策略

- `T1_schema`：object taxonomy、execution mode、统一 hit model
- `T2_module_interaction`：本地结果渲染、子账号切换、删除同步
- `T4_user_journey`：从本地联系人 / 会话 / 消息结果进入聊天上下文

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结聊天对象 taxonomy 与 canonical hit model | `T1_schema` |
| `P2` | 冻结本地 snapshot / index 与账号隔离规则 | `T2_module_interaction` |
| `P3` | 冻结删除同步与 Journey 接入 | `T2_module_interaction`, `T4_user_journey` |
