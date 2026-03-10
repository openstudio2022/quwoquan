# 语音录制与发送（Voice Record and Send）

> **层级**：L4_story（隶属 L3 `voice-message`）
> **状态**：specified
> **依赖**：`runtime-media/media-upload-and-storage/upload-session-and-cdn-delivery`

## 背景与动机

语音消息端到端闭环的"发送侧"Story：从用户按住录音按钮开始，到消息成功发送到云端。覆盖录音引擎、波形采集、上传流程、消息发送、离线队列五个关键环节。

## 目标用户

- 趣聊用户（发送语音消息的一方）

## 功能范围

### 录音引擎

1. 集成 `record` 包，输出 AAC/m4a 格式，采样率 16kHz
2. 录音开始/停止/取消 API
3. 录音时实时采集音量/波形数据（50-100 采样点 float 数组）
4. 录音时长计时，到达 120 秒自动停止
5. 录音低于 1 秒不发送，Toast 提示

### 录音交互

6. 按住录音按钮开始录音（长按手势）
7. 松手发送
8. 上滑取消（上滑超过 80dp 进入取消区域，松手取消）
9. 录音中 UI 反馈：音量波形、计时器、取消提示

### 上传流程

10. 录音完成 → 通过 `MediaUploadManager` 上传（category=messaging, mediaType=audio, mimeType=audio/aac）
11. 上传进度回调 → UI 显示上传进度
12. 上传成功 → 获取 cdnUrl + mediaId

### 消息发送

13. 上传成功后调用 `sendMessage(type: 'audio', media: {url, mediaId, mimeType, durationMs, waveform, codec, fileSizeBytes})`
14. 乐观插入：录音完成即在本地列表插入消息（status=sending），上传完成更新为 sent
15. 发送失败可重试

### 离线队列

16. 断网时录音保存到 Hive 离线队列：{localPath, conversationId, clientMsgId, durationMs, waveform, status=pending}
17. 网络恢复后按 FIFO 自动从队列取出 → 上传 → 发送
18. 离线消息在 UI 中显示 ⏳ 待发送状态
19. 离线队列容量 ≥ 100 条

### metadata 变更

20. `_shared/types.yaml` MessageType 新增 `audio`（新增 `file` 备用）
21. `messages/conversation/fields.yaml` Message 新增 `media`（object, NULLABLE）
22. `messages/conversation/service.yaml` SendMessage writable_fields 新增 `media`
23. `messages/conversation/events.yaml` MessageSent payload_fields 新增 `mediaUrl`、`media`
24. `make verify-metadata → make codegen → make codegen-app`

## 不做什么（Out of Scope）

- 语音转文字（ASR）
- 录音降噪/增强
- 录音文件压缩优化
- 变速播放（属于 playback Story）

## 约束

- 同时只允许一个录音任务
- 录音期间不阻塞主线程（录音在 native 线程）
- 麦克风权限使用 `permission_handler`，首次使用前请求
- 权限被永久拒绝时展示权限引导卡片（复用 `error-permission-display-semantics`）
- 录音文件临时存储在 `getTemporaryDirectory()`，上传成功后删除

### 弱网约束

- 上传超时：强网 30s，弱网（检测到 <100kbps）延长至 120s
- presigned URL 过期（15min）后自动重新 InitUpload
- 上传失败重试 3 次（1s→2s→4s），全部失败标记消息 status=failed，用户可手动重试

### 并发约束

- 同时最多 3 个语音上传任务（MediaUploadManager 全局队列）
- 录音与上传可并行（录音结束后立即入队上传）

## 适用范围与约束

- **适用**：趣聊 1v1 私聊和群聊中的语音消息发送
- **前置**：runtime/media MediaStore 已实现、麦克风权限可获取
- **不适用**：AI 助手语音输入（当前仍走 ASR 路径）

## 对标输入与吸收结论

| 对标 | 借鉴 | 不借鉴 |
|------|------|--------|
| 微信 | 按住/松手/上滑取消交互范式 | 左滑转文字（后续 Phase） |
| Telegram | 锁定录音模式（松手不停止） | 锁定模式增加复杂度，MVP 不实现 |

## 验收重点

详见 `acceptance.yaml`。
