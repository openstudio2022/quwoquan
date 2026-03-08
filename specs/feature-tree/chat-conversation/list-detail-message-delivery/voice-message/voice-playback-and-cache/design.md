# 语音播放与缓存 设计方案

> 本节点为 L4_story，设计决策继承自 L3 `voice-message` design.md。

## 设计动因

语音消息接收侧 Story：气泡 UI + 下载缓存 + 播放引擎 + 设备管理。

## 上游输入评审

L3 spec + design 完整，无阻断项。依赖 voice-record-and-send（消息模型已扩展）。

## 关键设计决策

继承 L3 design.md KD-5 ~ KD-9。本 Story 关注以下实现细节：

### 语音气泡组件结构

```
VoiceMessageBubble (StatefulWidget)
├── PlayPauseButton (GestureDetector + Icon)
│   └── 未播放: CupertinoIcons.play_circle
│       播放中: CupertinoIcons.pause_circle
├── VoiceWaveformPainter (CustomPaint + RepaintBoundary)
│   └── 未播放: 灰色波形
│       播放中: 从左到右渐变主题色（进度驱动）
│       已播放: 主题色波形
├── DurationLabel (Text)
│   └── 未播放: "0:05"
│       播放中: "0:02/0:05"（已播/总时长）
└── UnreadDot (Positioned)
    └── 接收的+未播放 → 红点；播放后消失
```

### VoicePlayerManager 生命周期

```dart
class VoicePlayerManager extends StateNotifier<VoicePlayerState> {
  final AudioPlayer _player;
  final AudioSession _session;
  final MediaDownloadCache _cache;

  Future<void> play(String messageId, String mediaUrl, String? mediaId) async {
    if (state.currentMessageId == messageId && state.isPlaying) {
      await pause();
      return;
    }
    await stop();

    final localPath = await _cache.getOrDownload(mediaId ?? mediaUrl, mediaUrl);
    await _player.setFilePath(localPath);
    await _player.play();

    state = state.copyWith(
      currentMessageId: messageId,
      isPlaying: true,
    );
  }
}
```

### 波形渲染算法

```dart
class VoiceWaveformPainter extends CustomPainter {
  final List<double> waveform;
  final double progress;     // 0.0 ~ 1.0
  final Color playedColor;   // AppColors.primaryColor
  final Color unplayedColor; // AppColors.light.textTertiary

  @override
  void paint(Canvas canvas, Size size) {
    final barWidth = size.width / waveform.length;
    for (int i = 0; i < waveform.length; i++) {
      final x = i * barWidth;
      final barHeight = waveform[i] * size.height * 0.8 + size.height * 0.1;
      final isPlayed = (i / waveform.length) <= progress;
      final paint = Paint()
        ..color = isPlayed ? playedColor : unplayedColor
        ..strokeWidth = barWidth * 0.6
        ..strokeCap = StrokeCap.round;
      canvas.drawLine(
        Offset(x + barWidth / 2, (size.height - barHeight) / 2),
        Offset(x + barWidth / 2, (size.height + barHeight) / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(VoiceWaveformPainter old) =>
      old.progress != progress || old.waveform != waveform;
}
```

### 弱网播放降级策略

```
点击播放
    │
    ├── 缓存命中？
    │   ├── 是 → 直接播放（≤200ms 起播）
    │   └── 否 → 开始下载
    │           │
    │           ├── just_audio.setUrl(cdnUrl) — 流式播放（边下边播）
    │           │   ├── 强网 → ≤1s 起播
    │           │   ├── 弱网 → ≤5s 起播（buffering 状态 UI 提示）
    │           │   └── 超时 30s → 显示"网络不佳，点击重试"
    │           │
    │           └── 断网 → 显示"无法播放，请检查网络"
    │
    └── 播放完成 → 进度重置 0:00 → 缓存写入（如未缓存）
```

## 适用场景与约束

同 L3 design.md。

## 未来演进

同 L3 design.md。
