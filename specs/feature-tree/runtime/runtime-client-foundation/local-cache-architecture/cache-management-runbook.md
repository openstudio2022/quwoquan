# 缓存管理 Runbook

## 入口

用户入口位于设置/存储管理页。页面只调用 `CacheManagementService`，不得直接删除图片文件、数据库行或 cache manager 目录。

## 清理层级

| 层级 | 用户文案 | 清理内容 | 不清理内容 |
|---|---|---|---|
| L1 | 清理临时图片和视频 | 大图、视频、临时缩略图、可重建 full variant | 对象 metadata、头像 URL、post 标题/摘要/正文 |
| L2 | 清理离线内容 | query snapshot、post detail、comment page、非 pinned 用户详情 | 当前用户、关注/联系人、最近会话、草稿、outbox |
| L3 | 清理搜索和浏览记录 | 搜索记录、浏览 query snapshot、最近访问 query key | 被收藏/关注/会话引用的对象本体 |
| L4 | 清理全部本地缓存 | 全部可重建对象缓存、查询快照、资源字节 | 账号凭证、创作草稿、待发送消息、待同步 outbox |

“清除本机数据/退出账号”是更高风险流程，不属于普通缓存清理。

## 执行步骤

1. `estimateUsage()` 统计资源字节、对象缓存、查询快照、访问记录的可释放空间。
2. `planClear(level)` 生成清理计划，列出将删除的 bucket、对象数量、受保护数量。
3. UI 展示影响说明与二次确认。
4. `executeClear(planId)` 执行清理。
5. `CacheDiagnosticsProbe` 记录释放空间、耗时、失败 bucket。
6. Provider 接收清理事件，刷新当前页面。

## 保护规则

- 创作草稿不可被普通缓存清理删除。
- 待发送消息不可被普通缓存清理删除。
- 点赞、收藏、关注、评论等待同步 outbox 不可被普通缓存清理删除。
- 当前用户最小资料、关注/联系人、最近会话列表快照默认受保护。
- 只清理资源字节时，不得删除对象 URL、版本、metadata。

## 测试要求

### local_contract 静态

- `object-cache-policy.yaml` 每个对象必须声明 `clear_policy`。
- 设置页不得直接 import 或操作底层 cache manager/file/db。
- 图片入口 allowlist 不得新增新债。

### local_contract 单元/组件

- 清理临时图片后，post metadata 与头像 URL 仍存在。
- 清理离线内容后，非 pinned post detail 被删除，收藏/最近阅读 post 保留。
- 清理全部本地缓存后，草稿、待发送消息、outbox 仍存在。
- 同一头像被多个对象引用时，只删除字节，不破坏对象引用。

### api_integration 集成

- 离线清理资源后恢复网络，资源按对象版本重新下载。
- outbox 操作在清理后仍可重试并合并远端确认。
- sync patch 到达时能刷新已被标记 stale 的对象。

### user_acceptance 真机

- `flutter run` 冷启动首页 feed，断网后仍显示最近 snapshot。
- 连续滚动图文 feed，头像/封面不逐项闪烁重拉。
- 重复进入文章/图片/视频详情，请求数不线性增长。
- 执行 L1/L2/L4 清理后分别验证空间下降、保护对象不丢失、离线回显符合文案。

## 观测字段

| 字段 | 说明 |
|---|---|
| `cache.clear.level` | L1/L2/L3/L4 |
| `cache.clear.bytes_released` | 释放字节数 |
| `cache.clear.objects_removed` | 删除对象数 |
| `cache.clear.objects_protected` | 受保护对象数 |
| `cache.clear.duration_ms` | 清理耗时 |
| `cache.clear.failed_bucket` | 失败 bucket |
| `cache.hit.source` | memory/disk/remote/seed/overlay |
| `cache.refresh.duration_ms` | stale 后台刷新耗时 |

## 回滚

- 若清理入口存在误删风险，立即隐藏入口并保留后台自然淘汰。
- 若对象缓存 schema 不兼容，清理可重建缓存后回退 RemoteRepository。
- 若资源清理导致图片异常，先回退资源清理 bucket，保留对象缓存。
