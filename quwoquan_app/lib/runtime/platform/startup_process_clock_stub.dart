import 'dart:async';

import 'package:flutter/services.dart';

const MethodChannel _startupTimingsChannel = MethodChannel(
  'quwoquan/startup/timings',
);

/// 返回 null 表示该平台没有进程级启动计时能力，不表示测量失败。
int? tryReadPlatformStartupElapsedMs() => null;

String? readPlatformStartupDeadlineOrigin() => null;

void recordPlatformStartupEvent(String json) {
  unawaited(
    _startupTimingsChannel
        .invokeMethod<void>('recordStartupEvent', json)
        .catchError((_) {}),
  );
}
