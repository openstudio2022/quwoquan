# L3 Story：富媒体消息（Rich Media Message） (`rich-media-message`)

> 所属能力：[`list-detail-message-delivery`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望Office 文档优先调用系统可用应用打开；存在 canonical PDF 派生资源时使用统一预览器，
从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- “富媒体消息（Rich Media Message）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 富媒体消息（Rich Media Message）

- Office 文档优先调用系统可用应用打开；存在 canonical PDF 派生资源时使用统一预览器。

<a id="req-002"></a>
### REQ-002 Office 文档打开与 PDF 预览

- DOCX、DOC、PPTX 与 PPT 优先调用系统可用应用打开；服务端提供 canonical PDF 派生资源时使用统一预览器。
- 视频/文件/图片上传必须通过 `MediaUploadManager`（OSS presign → 直传 → complete），禁止绕过。
- 发送必须通过 `ChatRepository.sendMessage(type=video/file/image)`，禁止降级为 text。
- 所有气泡 UI 使用 `AppTypography`/`AppSpacing`/`AppColors`，禁止硬编码。

<a id="req-003"></a>
### REQ-003 压缩后格式统一为 mp4/H.264

- 压缩后格式统一为 mp4/H.264。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 富媒体消息（Rich Media Message）

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“富媒体消息（Rich Media Message）”对应的公开行为。
- THEN Office 文档可由系统应用打开；存在 canonical PDF 派生资源时进入统一预览器。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`list-detail-message-delivery`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 富媒体消息（Rich Media Message） 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺图片查看器旅程与 api_integration 层富媒体交付证据。
  文件与视频消费入口已闭环并有 widget 证据：文件气泡点击经平台能力打开交付 URL（无本地文件系统平台走 platform default）；
  交付 URL 缺失时给结构化不可用提示；
  视频气泡点击经 `MediaDeliveryResolver` 校验交付引用后进入全屏 `VideoPlayerWidget` 播放；
  动作绑定与失败提示证据见 `chat_message_bubble_widget__local_contract_test.dart` 与 `message_paging_scroll_anchor__local_contract_test.dart`。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
