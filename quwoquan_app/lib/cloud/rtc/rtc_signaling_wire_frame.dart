/// WebSocket 通道入站一帧（与 `web_socket_channel` 元素类型隔离后的业务侧表示）。
sealed class RtcSignalingWireFrame {
  const RtcSignalingWireFrame._();

  /// 与第三方 `Stream.listen` 接壤的唯一入口；其后逻辑仅使用 [RtcSignalingWireFrame]。
  factory RtcSignalingWireFrame.fromChannelData(Object? data) {
    if (data == null) return const RtcSignalingWireUnsupported._();
    if (data is String) return RtcSignalingWireText(data);
    if (data is List<int>) {
      return RtcSignalingWireBytes(List<int>.from(data));
    }
    return const RtcSignalingWireUnsupported._();
  }
}

/// UTF-8 文本帧（常见 JSON）。
final class RtcSignalingWireText extends RtcSignalingWireFrame {
  const RtcSignalingWireText(this.utf8Text) : super._();

  final String utf8Text;
}

/// 二进制帧按 UTF-8 解码后再当 JSON 解析（与记录行为一致）。
final class RtcSignalingWireBytes extends RtcSignalingWireFrame {
  RtcSignalingWireBytes(this.bytes) : super._();

  final List<int> bytes;
}

/// 不支持的帧形态（忽略）。
final class RtcSignalingWireUnsupported extends RtcSignalingWireFrame {
  const RtcSignalingWireUnsupported._() : super._();
}
