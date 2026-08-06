import 'dart:async';

import 'package:flutter/services.dart';

const MethodChannel _startupTimingsChannel = MethodChannel(
  'quwoquan/startup/timings',
);

int? readPlatformStartupElapsedMs() => null;

String? readPlatformStartupDeadlineOrigin() => null;

void recordPlatformStartupEvent(String json) {
  unawaited(
    _startupTimingsChannel
        .invokeMethod<void>('recordStartupEvent', json)
        .catchError((_) {}),
  );
}
