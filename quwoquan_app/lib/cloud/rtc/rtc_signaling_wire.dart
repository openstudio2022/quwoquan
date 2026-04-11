import 'dart:convert';

import 'package:quwoquan_app/cloud/rtc/rtc_signaling_wire_frame.dart';

/// RTC 信令 WS 文本帧解析（与 [RtcSignalingClient] 共用，便于单测）。
Map<String, dynamic>? decodeRtcSignalingJsonMessage(RtcSignalingWireFrame frame) {
  final String? text = switch (frame) {
    RtcSignalingWireText(:final utf8Text) => utf8Text,
    RtcSignalingWireBytes(:final bytes) => utf8.decode(
      bytes,
      allowMalformed: false,
    ),
    RtcSignalingWireUnsupported() => null,
  };
  if (text == null) return null;
  try {
    final decoded = jsonDecode(text);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
    return null;
  } on FormatException {
    return null;
  }
}
