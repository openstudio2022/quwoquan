# recent-search-sync-and-voice-asr 设计方案

## 设计动因

最近搜索和语音输入都属于“搜索入口能力”，但它们的生命周期与综合结果完全不同。设计阶段需要把这两个子问题单独收口，避免后续把问小趣 query、聊天语音发送链路或临时本地缓存混进来。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `recent-search-sync-and-voice-asr/spec.md` | 已冻结 recent search local+cloud 双写与语音只做 ASR 转词 |
| `recent-search-sync-and-voice-asr/acceptance.yaml` | `A1/A2/S1` 足以承接实施切片 |
| 现有 chat voice 能力 | 只能复用权限与波形交互经验，不能复用发送链路 |

## 对标输入分析

- 微信的语音入口提供了“说完即搜”的心智，但本产品已经冻结为 ASR 转词，不做语义理解。
- 最近搜索需要强调“可复用、可清理、可跨设备恢复”。

## 方案对比

### 方案 A：local-only history + 语音直接写搜索框

优点：

- 实现简单。

缺点：

- 不满足云同步要求。

### 方案 B：cloud-only history + 语音直接问小趣

优点：

- 统一云端。

缺点：

- 与 PRD 冻结要求冲突。
- 弱网下体验差。

### 方案 C：local-first history + cloud sync + 独立 `SearchVoiceAsrAdapter`

优点：

- 同时满足即时体验和跨设备恢复。
- 与问小趣 query 生命周期清晰分离。

缺点：

- 需要定义 history sync contract。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：recent search 采用 local-first 双写

写入顺序：

1. 本地成功
2. 异步触发云同步

读取顺序：

1. 本地即时展示
2. 页面初始化时拉云端做 reconcile

### KD2：云端 sync contract 落在 `user` 域

推荐 contract：

- `ListRecentSearches`
- `UpsertRecentSearch`
- `DeleteRecentSearch`
- `ClearRecentSearches`

返回模型：

- `RecentSearchEntryView`

### KD3：语音入口封装为 `SearchVoiceAsrAdapter`

- 独立于 chat voice recorder / sender
- 输出只有文本 query
- 不落原始音频

### KD4：问小趣 query 不进入 recent search

- 搜索 query 和问小趣 query 生命周期完全分离
- UI 层要在触发 handoff 时明确区分两类动作

### KD5：metadata / codegen 方案

- `user/user_profile/fields.yaml`
  - 新增 `RecentSearchEntryView`
- `user/user_profile/service.yaml`
  - 新增 4 个 recent search 同步操作
- `_shared/request_context.yaml`
  - 新增 recent search sync request page ids

## 字段演进、迁移/回填、必要时双读双写方案

- 本地 schema 统一为：
  - `query`
  - `scope`
  - `facet`
  - `timestamp`
- 如果已有本地临时历史，启动时迁移到新 schema
- 采用 local + cloud 双写；云失败不回滚本地成功

## feature flag、观测、SLO 验证与回滚方案

- 无业务 feature flag。
- 观测：
  - `recent_search_sync_failure_count`
  - `recent_search_clear_count`
  - `search_asr_success_count`
  - `search_asr_failure_count`
  - `search_microphone_permission_denied_count`
- SLO：
  - recent search 首页即时可见
  - ASR 成功后快速回填搜索框
- 回滚：
  - 语音能力异常时回退到手动输入
  - recent search 云同步异常时保留本地能力

## TDD / ATDD 策略

- `T1_schema`：recent search contract、本地 schema
- `T2_module_interaction`：history 展示、删除、清空、语音回填
- `T3_cross_service_integration`：cloud sync、reconcile
- `T4_user_journey`：语音转词后继续搜索

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 recent search sync contract 与 local schema | `T1_schema` |
| `P2` | 落地 recent search sync 与 ASR adapter | `T2_module_interaction`, `T3_cross_service_integration` |
| `P3` | 验证 clear/reconcile/fallback 主路径 | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 后续若需要统一自动过期时间，可把 history retention 接入 user 域配置，但不改变 query 模型。
