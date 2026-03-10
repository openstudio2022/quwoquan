# 语音录制与发送 设计方案

> 本节点为 L4_story，设计决策继承自 L3 `voice-message` design.md。

## 设计动因

语音消息发送侧 Story：录音引擎 + 录音交互 + 上传 + 发送 + 离线队列。

## 上游输入评审

L3 spec + design 完整，无阻断项。

## 关键设计决策

继承 L3 design.md KD-1 ~ KD-9。本 Story 关注以下实现细节：

### 录音引擎封装

```dart
class VoiceRecorder {
  final Record _recorder;
  final List<double> _amplitudes = [];

  Future<void> start() async {
    await _recorder.start(
      encoder: AudioEncoder.aacLc,
      samplingRate: 16000,
      bitRate: 64000,
    );
    _recorder.onAmplitudeChanged(const Duration(milliseconds: 50)).listen((amp) {
      _amplitudes.add(amp.current.clamp(-50, 0).normalize());
    });
  }

  Future<VoiceRecordResult?> stop() async {
    final path = await _recorder.stop();
    if (_recordDuration < Duration(seconds: 1)) return null;
    return VoiceRecordResult(
      filePath: path!,
      durationMs: _recordDuration.inMilliseconds,
      waveform: _downsample(_amplitudes, targetPoints: 80),
    );
  }
}
```

### 发送流程

```
录音完成(VoiceRecordResult)
    │
    ├── 有网？
    │   ├── 是 → MediaUploadManager.upload(
    │   │         category: messaging,
    │   │         mediaType: audio,
    │   │         mimeType: audio/aac,
    │   │         filePath: result.filePath,
    │   │         clientMeta: {durationMs, waveform}
    │   │       )
    │   │   → 获得 MediaAssetDto {cdnUrl, mediaId}
    │   │   → ChatRepository.sendMessage(
    │   │         type: audio,
    │   │         media: {url: cdnUrl, mediaId, mimeType, durationMs, waveform, codec: aac, fileSizeBytes}
    │   │       )
    │   │
    │   └── 否 → VoiceOfflineQueue.enqueue(result, conversationId, clientMsgId)
    │             → UI: ⏳ 待发送
    │
    └── 乐观插入 ChatMessageNotifier（status=sending，含本地波形）
```

## 适用场景与约束

同 L3 design.md。

## 未来演进

同 L3 design.md。
