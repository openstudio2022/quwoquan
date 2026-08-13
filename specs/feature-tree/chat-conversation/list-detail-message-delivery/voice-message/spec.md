# L3 Story：语音消息（Voice Message） (`voice-message`)

> 所属能力：[`list-detail-message-delivery`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为参与会话的用户，
我希望按住录音、上滑取消并松手发送语音，取消或重复按下不会留下残余录音，
从而可靠完成 1v1 与群聊语音沟通。

## 2. 范围与非目标

### In Scope

- “语音消息（Voice Message）”的输入、可观察主路径、失败语义以及与父能力的交接。
- 趣聊 1v1 和群聊中的按住录音、上滑取消、松手发送。
- 真实麦克风振幅驱动的录音 HUD 波形。
- audio 消息 media payload、上传、发送、播放、缓存和失败状态。
- 麦克风权限、录音、上传、发送、播放、缓存失败的统一错误语义。
- 评论、回复、文章内联评论、沉浸评论面板无 ASR/语音入口。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 语音消息（Voice Message）

- 上滑取消、页面退出或重复按下必须终止并释放当前录音，且不得上传或发送幽灵消息。

<a id="req-002"></a>
### REQ-002 上滑取消、页面退出和并发录音不会产生幽灵录音或重复发送

- 上滑取消、页面退出或重复按下必须终止并释放当前录音，且不得上传或发送幽灵消息。

<a id="req-003"></a>
### REQ-003 权限与失败统一映射到临时或永久恢复动作

- 权限拒绝、录音失败、上传失败与发送失败必须映射到明确的临时或永久恢复动作。

<a id="req-004"></a>
### REQ-004 audio Message 与 MediaAsset 强类型引用端云一致

- audio Message 必须以强类型 `MediaAsset` 引用在端云间传递，不得复制临时 URL 字段。

<a id="req-005"></a>
### REQ-005 播放、缓存和并发播放状态可用可靠

- 同一时刻只能播放一条语音；切换、失败与缓存不可用时必须收敛到可恢复状态。

<a id="req-006"></a>
### REQ-006 评论和回复入口在 ASR 未支持时不展示语音能力

- ASR 未支持时，评论、回复、文章内联评论与沉浸评论面板不得展示语音入口。

<a id="req-007"></a>
### REQ-007 评论语音不复用聊天语音链路

- 评论、回复、文章内联评论和沉浸评论面板不展示聊天语音入口；评论语音属于内容评论能力，必须使用独立规格、契约与验收，不能复用聊天语音发送链路。
- 录音库必须支持 AAC 编码、iOS/Android 双端，推荐 `record` 包。
- 播放库必须支持流式播放（边下边播）、进度回调，推荐 `just_audio`
- 上传必须通过 `runtime/content.source.media.MediaStore`（`CategoryMessaging`），禁止直接调用 OSS。
- 发送必须通过 `ChatRepository.sendMessage`，禁止绕过消息链路。
- 语音气泡 UI 必须使用 `AppTypography`/`AppSpacing`/`AppColors`，禁止硬编码。
- metadata 变更必须走 `metadata → verify → codegen` 流程。
- 录音 HUD 波形只保留固定窗口采样，最新采样从右侧进入并整体向左推进，长录音不得导致 UI 状态无限增长。
- 权限、录音、上传、发送、播放、缓存失败均按统一错误语义展示临时/永久失败和恢复动作。

<a id="req-008"></a>
### REQ-008 必须聊天语音消息从录音、真实波形、上传、发送到播放的商用化闭环，以及评论 ASR 入口关闭约束，且失败时不得写入成功事实

- 系统必须聊天语音消息从录音、真实波形、上传、发送到播放的商用化闭环，以及评论 ASR 入口关闭约束，且失败时不得写入成功事实。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#SendMessage`
- canonical：`quwoquan_service/contracts/metadata/_shared/types.yaml#MessageType`
- 协作规格：[`error-permission-display-semantics`](../../../runtime/runtime-client-foundation/error-permission-display-semantics/spec.md)
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml#SendMessage`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/events.yaml#MessageSent`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/operations.yaml#GetMediaAssetDeliveryReference`
- 协作规格：[`recent-search-sync-and-voice-asr`](../../../global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 语音消息（Voice Message）

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“语音消息（Voice Message）”对应的公开行为。
- THEN 取消或离开页面后不产生消息。
- THEN 重复按下不会并发录音，成功发送后接收方可播放同一音频资产。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-004"></a>
### GWT-004 audio Message 与 MediaAsset 强类型引用端云一致

- GIVEN 用户录制并发送一条语音消息。
- WHEN App 与服务端写入、读取该消息。
- THEN audio Message 只通过强类型 MediaAsset 引用同一音频资产，且不依赖临时 URL。
- AND `audioDurationMs` 与 `audioWaveform` 仅 `type=audio` 合法，非 audio 携带返回 canonical MessageInvalid。
- AND 落库、MessageSent 事件、List/Sync 读面与接收端语音气泡渲染同一真实时长与波形。

## 6. 依赖

- 前置要求：[`list-detail-message-delivery`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 按住录音展示真实音量波形并松手发送

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：录音、上传、发送、消息展示、播放闭环在 Widget/Provider 测试和 user_acceptance 记录中均有证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

