## 1. 浏览信息模型与本地存储

- [x] 1.1 定义 VisitTarget（页面型/实体型）与 targetKey 生成规则，定义 VisitRecord 模型（targetKey、firstSeenAt、lastSeenAt、visitCount、count7d/count30d 或等价字段）
- [x] 1.2 实现 VisitRecorderService：recordVisit(VisitTarget)、getExperience(VisitTarget)、getRecord(VisitTarget)，5 分钟同 targetKey 去重逻辑
- [x] 1.3 为 VisitRecord 注册 Hive TypeAdapter（或 Map 序列化），在 main 或初始化处 open box `visit_records`

## 2. 云端同步预留

- [x] 2.1 定义 VisitSyncService 抽象类（或接口）：uploadLocalVisits()、pullAndMergeRemoteVisits()，注释数据契约与 VisitRecord 一致，不实现具体网络与鉴权

## 3. 打开上下文与配置

- [x] 3.1 定义 AssistantOpenContext（source、tab/dimension/entityId、VisitTarget、experienceLevel、可选 hints）
- [x] 3.2 实现助理欢迎句与 chips 配置（assistant_prompt_config 或等价）：按 (source, tab/entityKind, experienceLevel) 提供欢迎句模板、推荐 chips 与「当前适合干啥」文案

## 4. 半弹窗 UI

- [x] 4.1 实现 AssistantHalfSheet：showModalBottomSheet、约 50% 屏高、可拖拽，接收 AssistantOpenContext，拉取欢迎/chips/当前适合干啥并渲染
- [x] 4.2 半弹窗底部：输入框 +「进入完整对话」按钮，点击后关闭弹窗并 push `/chat/assistant`，extra 为 AssistantOpenContext
- [x] 4.3 会话页 builder 读取 state.extra 中的 AssistantOpenContext，用于首条欢迎与推荐（与半弹窗一致）

## 5. 记录时机挂载

- [x] 5.1 发现页：切一级 tab 时解析 VisitTarget（如 page_discovery_photo）并调用 recordVisit
- [x] 5.2 圈子页：切维度或进入圈子详情时解析并 recordVisit（page_circles_*、entity_circle_<id>）
- [x] 5.3 作者主页与圈子主页：进入时 recordVisit（entity_author_<id>、entity_circle_<id>）
- [x] 5.4 创作页：进入子步骤（选图/编辑/写文案/发布）时解析并 recordVisit（page_create_*）

## 6. 入口统一为半弹窗

- [x] 6.1 发现页小趣入口改为 AssistantHalfSheet.show(context, assistantOpenContext)，不再直接 push /assistant 或 /chat/assistant
- [x] 6.2 聊天页（置顶助理/找小趣）改为先展示半弹窗，传入来自 chat 的 AssistantOpenContext
- [x] 6.3 我的页、文章页、app_router 的 onAssistantClick 等所有「打开小趣」入口改为先半弹窗，统一传入 AssistantOpenContext
