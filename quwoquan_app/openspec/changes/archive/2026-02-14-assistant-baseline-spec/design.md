## Context

小趣私人助手在应用内已有入口（发现页图标、聊天置顶助理、我的页等），但当前多为直接跳转全屏助理页或会话页，缺少与用户当前浏览上下文的结合；浏览行为（首次/再次/常用）也未持久化，无法驱动个性化欢迎与推荐。本设计在不大改现有聊天与路由骨架的前提下，引入浏览信息存储与「先半弹窗再可选进入完整对话」的入口形态，为后续小趣能力扩展建立技术基线。

## Goals / Non-Goals

**Goals:**
- 定义 VisitTarget/VisitRecord 数据模型与 VisitRecorderService 封装，使用 Hive 单 box 持久化，支持 experienceLevel（first_time/returning/frequent）派生与 5 分钟同 target 去重。
- 定义 VisitSyncService 抽象接口与数据契约，不实现具体同步逻辑，便于后续云端同步接入。
- 定义 AssistantOpenContext（source、tab/entityId、VisitTarget、experienceLevel、hints）与半弹窗 UI 契约；所有「打开小趣」入口统一先展示半弹窗，再可选「进入完整对话」并 push 会话页并携带 context。
- 在发现/圈子/作者/圈子主页/创作等关键场景挂载 recordVisit 调用，由路由或页面状态解析 VisitTarget 并去重写入。

**Non-Goals:**
- 不实现云端同步、鉴权与冲突策略。
- 不在此设计内定义帮读卡、任务抽屉、多形态切换或主动触发策略；仅建立半弹窗 + 进入完整对话的基线。
- 欢迎页、发现页 IA 升级与助理交互协议 V1 留待其他 change。

## Decisions

### 决策 1：浏览信息用 Hive 单 box，key = targetKey
- 方案：VisitRecord 以 targetKey（如 `page_discovery_photo`、`entity_author_<id>`）为 key 存入单一 Hive box（如 `visit_records`），由 VisitRecorderService 统一 recordVisit/getExperience/getRecord。
- 原因：项目已使用 Hive，单 box 便于备份与后续同步时批量读写；targetKey 数量在可预期范围内（页面型有限、实体型按访问过的作者/圈子增长）。
- 备选：SharedPreferences 存 JSON。放弃原因：实体型 target 增多时单一大 JSON 或大量 key 均不如 Hive 高效。

### 决策 2：云端同步仅抽象接口，数据契约与本地 VisitRecord 一致
- 方案：定义 VisitSyncService 抽象类（如 uploadLocalVisits、pullAndMergeRemoteVisits），方法签名与注释明确数据契约与 VisitRecord 结构一致，不实现网络与冲突逻辑。
- 原因：基线阶段聚焦本地能力与半弹窗体验，云端可后续在同一数据模型上扩展。
- 备选：暂不定义接口。放弃原因：提前约定接口可避免后续实现时破坏本地模型。

### 决策 3：半弹窗为统一入口形态，会话页通过 push 并携带 AssistantOpenContext
- 方案：所有打开小趣的入口改为先 `AssistantHalfSheet.show(context, assistantOpenContext)`；半弹窗内「进入完整对话」执行关闭弹窗 + `context.push('/chat/assistant', extra: assistantOpenContext)`；会话页 builder 读取 state.extra 用于首条欢迎与推荐。
- 原因：统一「先轻量半弹窗、再深度对话」的心智，且 context 一次组装、两处使用（半弹窗与会话页），避免重复逻辑。
- 备选：保留部分入口直接进会话。放弃原因：入口形态不一致会拖慢基线建立与后续扩展。

### 决策 4：VisitTarget 由各页或 RouteToVisitTargetMapper 解析，5 分钟同 target 去重
- 方案：在发现/圈子/作者/圈子主页/创作等页的 initState 或路由 builder 中解析当前 VisitTarget（来自 GoRouterState + 页面状态），调用 VisitRecorderService.recordVisit(target)；Service 内对同一 targetKey 在 5 分钟内仅更新 lastSeenAt 不增加 visitCount。
- 原因：记录时机与路由/页面强相关，集中在一层 Mapper 或各页显式调用均可接受；去重避免短时间重复切换 tab 刷高次数。
- 备选：仅路由层统一解析。放弃原因：部分 target 依赖页面状态（如创作子步骤），路由层难以完全覆盖，允许各页参与更灵活。

### 决策 5：欢迎句与 chips 由配置驱动（常量或小型配置表）
- 方案：按 (source, tab/entityKind, experienceLevel) 维护欢迎句模板与推荐 chips 列表（Dart 常量或 JSON），半弹窗只做查表与渲染，不内联复杂分支。
- 原因：产品会持续迭代文案与推荐项，配置化便于修改与 A/B，且与实现解耦。
- 备选：硬编码在 widget 内。放弃原因：不利于后续多语言与运营配置。

## Risks / Trade-offs

- [Risk] 半弹窗与现有「直接进会话」习惯不一致，部分用户可能多一步操作。  
  → Mitigation：半弹窗内提供输入框与「进入完整对话」明显入口，且可拖拽展开，降低认知负担；后续可根据数据决定是否保留或简化半弹窗。

- [Risk] VisitRecord 随实体型 target 增长，本地存储与同步量会增大。  
  → Mitigation：基线仅本地；云端同步实现时可做 TTL 或按 lastSeenAt 裁剪，规格中不强制保留无限期历史。

- [Risk] 各页 recordVisit 调用遗漏或重复，导致 experienceLevel 不准。  
  → Mitigation：在 spec 与 tasks 中明确列出需挂载的页面与解析规则；实现后通过「首次进入 / 再次进入」人工走查验收。

## Migration Plan

- 实现顺序建议：VisitRecorderService + Hive 注册 → VisitSyncService 抽象 → AssistantOpenContext + 配置 → AssistantHalfSheet → 各页 recordVisit 挂载 → 所有小趣入口改为半弹窗。
- 回滚：若半弹窗需下线，可将入口改回直接 push 会话页，并保留 VisitRecorderService 与存储（只读不写亦可），无数据迁移需求。

## Open Questions

- 无。基线范围已收窄至存储、半弹窗与入口统一；欢迎/发现页叙事与助理多形态扩展在后续 change 中再定。
