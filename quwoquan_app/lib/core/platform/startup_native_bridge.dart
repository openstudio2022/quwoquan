import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

class NativeStartupProcessSegments {
  const NativeStartupProcessSegments({
    this.androidActivityOnCreateMs,
    this.androidFlutterEngineConfiguredMs,
    this.elapsedSinceProcessStartMs,
    this.deadlineOrigin,
    this.startupAttemptId,
  });

  final int? androidActivityOnCreateMs;
  final int? androidFlutterEngineConfiguredMs;
  final int? elapsedSinceProcessStartMs;
  final String? deadlineOrigin;
  final String? startupAttemptId;
}

abstract interface class StartupTimingsNativeBridge {
  Future<NativeStartupProcessSegments?> readProcessSegments();
}

class NativeStartupJournalEntries {
  const NativeStartupJournalEntries({
    required this.attemptId,
    required this.events,
  });

  final String attemptId;
  final List<String> events;
}

abstract interface class StartupJournalNativeBridge {
  Future<NativeStartupJournalEntries?> readEntries();

  Future<bool> clearEntries();
}

abstract interface class StartupDeferredPluginsNativeBridge {
  Future<void> ensureStartupPostFirstFrame();

  Future<void> ensureRtc();

  Future<void> ensureContentEntry();

  Future<void> ensureLocation();
}

class MethodChannelStartupTimingsNativeBridge
    implements StartupTimingsNativeBridge {
  const MethodChannelStartupTimingsNativeBridge({
    this.channel = const MethodChannel('quwoquan/startup/timings'),
  });

  final MethodChannel channel;

  @override
  Future<NativeStartupProcessSegments?> readProcessSegments() async {
    try {
      final raw = await channel.invokeMethod<Object?>('readProcessSegments');
      if (raw is! Map) {
        return null;
      }
      return NativeStartupProcessSegments(
        androidActivityOnCreateMs: _asInt(raw['androidActivityOnCreateMs']),
        androidFlutterEngineConfiguredMs: _asInt(
          raw['androidFlutterEngineConfiguredMs'],
        ),
        elapsedSinceProcessStartMs: _asInt(raw['elapsedSinceProcessStartMs']),
        deadlineOrigin: raw['deadlineOrigin']?.toString(),
        startupAttemptId: raw['startupAttemptId']?.toString(),
      );
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  static int? _asInt(Object? value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.round();
    }
    return null;
  }
}

class MethodChannelStartupJournalNativeBridge
    implements StartupJournalNativeBridge {
  const MethodChannelStartupJournalNativeBridge({
    this.channel = const MethodChannel('quwoquan/startup/timings'),
  });

  final MethodChannel channel;

  @override
  Future<NativeStartupJournalEntries?> readEntries() async {
    try {
      final raw = await channel.invokeMethod<Object?>('readStartupJournal');
      if (raw is! Map) {
        return null;
      }
      final rawEvents = raw['events'];
      if (rawEvents is! List) {
        return null;
      }
      return NativeStartupJournalEntries(
        attemptId: raw['attemptId']?.toString() ?? '',
        events: rawEvents
            .map((event) => event.toString())
            .toList(growable: false),
      );
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  @override
  Future<bool> clearEntries() async {
    try {
      await channel.invokeMethod<void>('clearStartupJournal');
      return true;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }
}

class MethodChannelStartupDeferredPluginsNativeBridge
    implements StartupDeferredPluginsNativeBridge {
  const MethodChannelStartupDeferredPluginsNativeBridge({
    this.channel = const MethodChannel('quwoquan/startup/deferred_plugins'),
  });

  final MethodChannel channel;

  @override
  Future<void> ensureStartupPostFirstFrame() =>
      _ensurePlatformPlugin('ensureStartupPostFirstFrame');

  @override
  Future<void> ensureRtc() => _ensureAndroidPlugin('ensureRtc');

  @override
  Future<void> ensureContentEntry() =>
      _ensureAndroidPlugin('ensureContentEntry');

  @override
  Future<void> ensureLocation() => _ensureAndroidPlugin('ensureLocation');

  Future<void> _ensureAndroidPlugin(String method) =>
      _ensurePlatformPlugin(method, androidOnly: true);

  Future<void> _ensurePlatformPlugin(
    String method, {
    bool androidOnly = false,
  }) async {
    if (androidOnly && currentAppPlatform != AppPlatform.android) {
      return;
    }
    try {
      await channel.invokeMethod<void>(method);
    } on MissingPluginException {
      return;
    } on PlatformException {
      return;
    }
  }
}
