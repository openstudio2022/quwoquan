# L3：本地对象缓存架构（local-cache-architecture）

## L1 / L2 / L3 映射

| 层级 | 标识 |
|---|---|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `local-cache-architecture` |

## 目标

建立一套端云一体的对象级缓存架构，覆盖 `UserProfile`、`Post`、`Conversation`、`Comment`、媒体资源与查询快照，确保页面能复用统一缓存输出、离线可回显、弱网不闪空、滚动不重复请求，并通过对象版本与出站队列实现最终一致。

## 范围

负责：

- 定义统一 `CacheReadResult<T>` 输出合同。
- 定义对象级缓存策略模板与生命周期。
- 定义端云 freshness / invalidation / sync 协议。
- 定义用户可见的分层缓存清理入口。
- 定义业务对象特性树必须补齐的缓存规格与验收项。
- 定义测试与门禁证据口径。

不负责：

- 替代 `contracts/metadata/**` 的字段、错误码、路由与 surface 唯一真相源。
- 把创作草稿、待发送消息、待同步 outbox 当作普通可清缓存。
- 承诺图片/视频原始字节永久离线保留。
- 在首版强制引入全局 `ETag` / `304`；首版以对象版本与 `stale-while-revalidate` 为主。

## 分层模型

| 层级 | 名称 | 职责 | 真相源 |
|---|---|---|---|
| L0 | UI 状态缓存 | tab 保活、滚动位置、页面局部状态 | 页面/Provider |
| L1 | 查询快照缓存 | feed/search/profile/circle query key、对象 id 列表、cursor | query snapshot store |
| L2 | 对象缓存 | 用户、post、会话、评论的强类型对象与版本 | object cache store |
| L3 | 资源缓存 | 头像、封面、正文图、视频缩略图、大图/视频字节 | resource cache controller |
| L4 | 同步一致性层 | outbox、overlay、sync patch、版本对账 | metadata + sync runtime |

## 统一输出合同

所有面向 UI 的缓存读必须输出 `CacheReadResult<T>` 语义结构，页面禁止直接读取 Hive/SQLite/file/cache manager：

| 字段 | 说明 |
|---|---|
| `value` | 强类型对象或查询快照 |
| `source` | `memory`、`disk`、`remote`、`seed`、`optimisticOverlay` |
| `freshness` | `fresh`、`stale`、`expired`、`unknown` |
| `syncState` | `idle`、`refreshing`、`offline`、`pendingWrite`、`conflict`、`error` |
| `objectVersion` | `updatedAt`、`avatarVersion`、`groupAvatarVersion`、`membersRosterRevision`、`postReadVersion` 等 |
| `cacheClass` | `pinned`、`recent`、`ephemeral` |
| `resourceRefs` | 资源 URL / objectKey / version / variant 引用，不包含大资源字节 |
| `overlay` | 本地未确认的赞、藏、转、评、关注等 desired state |
| `diagnostics` | 命中层级、请求次数、刷新耗时、失败原因 |

页面显示规则：

- `fresh`：直接展示。
- `stale`：先展示旧值并后台刷新。
- `expired`：可展示骨架或旧值，但必须触发刷新。
- `offline`：展示最近可用对象与离线标识。
- `pendingWrite`：展示本地 desired state，等待 sync/remote 确认。

## 对象策略模板

每个可缓存业务对象必须在对应特性树补 `object_cache` 规格，至少包含：

- `object_type`
- `owner_scope`
- `identity_key`
- `cache_fields`
- `resource_refs`
- `cache_class_rules`
- `freshness_keys`
- `write_overlay`
- `retention_policy`
- `clear_policy`
- `offline_contract`
- `sync_contract`
- `tests`

模板与首批对象策略见 [`object-cache-policy.yaml`](./object-cache-policy.yaml)。

## 分级保留

| 等级 | 进入条件 | 清理策略 |
|---|---|---|
| `pinned` | 当前用户、关注/联系人、最近会话、收藏或最近阅读 post、待同步对象 | 普通缓存清理不得删除；退出账号或清除本机数据另行确认 |
| `recent` | 最近 feed/query/detail 命中对象 | 可被“清理离线内容”删除，需保留仍被 pinned 引用的对象 |
| `ephemeral` | 大图、视频、临时搜索页、未交互对象 | 可随空间压力或“清理临时图片和视频”删除 |

## 用户清理入口

设置页提供统一存储管理入口，所有清理通过 `CacheManagementService` 执行：

| 操作 | 删除 | 保留 |
|---|---|---|
| 清理临时图片和视频 | 大图、视频、临时缩略图字节 | 对象 metadata、头像 URL、post 标题文字 |
| 清理离线内容 | query snapshot、post detail、comment pages、非 pinned 用户详情 | 当前用户、关注/联系人、最近会话、草稿、outbox |
| 清理搜索和浏览记录 | 搜索记录、浏览/最近访问 query snapshot | 被收藏/关注/会话引用的对象本体 |
| 清理全部本地缓存 | 全部可重建缓存 | 账号凭证、创作草稿、待发送消息、待同步 outbox |

高风险“清除本机数据/退出账号”不属于普通缓存清理，必须另有二次确认与数据风险说明。

## 端云同步合同

- 读路径：本地对象缓存先展示，后台按版本/时间戳对账；云端返回新版本后更新对象缓存，再派生更新查询快照。
- 写路径：点赞、收藏、关注、评论等先写本地 overlay/outbox；云端确认或 sync patch 返回后合并；失败则回滚或标记待重试。
- 资源路径：对象版本变化触发资源 URL/variant 更新；旧字节缓存自然淘汰，不作为业务真相源。
- 冲突口径：云端新版本优先于旧本地快照；本地未确认操作以 outbox desired state 叠加展示，直到云端确认。
- 同步分层：`push hint` 只传对象 id/版本，`pull diff` 拉差异，`batch get` 补齐对象，`repair full snapshot` 修复 gap。

## 业务对象覆盖

首批必须覆盖：

- `UserProfile`：用户资料、头像、关注关系、当前用户保护策略。
- `Post`：metadata、摘要/正文详情、互动 overlay、媒体资源引用。
- `Conversation`：会话投影、群头像、成员头像、消息摘要、待发送消息保护。
- `Comment`：评论分页、作者快照、本地新增/删除 overlay。
- `MediaResource`：图片/视频/头像资源字节、CDN variant、空间淘汰。
- `QuerySnapshot`：feed/search/profile/circle 的 query key、cursor、离线回显。

## 验收概要

- T1：规格、对象策略、inventory、runbook、业务特性树缓存章节齐全。
- T2：对象缓存、查询快照、资源缓存、清理入口的单元/组件测试覆盖。
- T3：RemoteRepository 与 metadata 版本字段对齐，弱网/离线/恢复后最终一致。
- T4：真机冷启动、滚动、重复详情、头像/封面变更、用户清理缓存有录屏/抓包证据。
