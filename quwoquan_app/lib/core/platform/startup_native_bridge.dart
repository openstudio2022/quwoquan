import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

class NativeStartupProcessSegments {
  const NativeStartupProcessSegments({
    this.androidActivityOnCreateMs,
    this.androidFlutterEngineConfiguredMs,
    this.elapsedSinceProcessStartMs,
    this.deadlineOrigin,
  });

  final int? androidActivityOnCreateMs;
  final int? androidFlutterEngineConfiguredMs;
  final int? elapsedSinceProcessStartMs;
  final String? deadlineOrigin;
}

abstract interface class StartupTimingsNativeBridge {
  Future<NativeStartupProcessSegments?> readProcessSegments();
}

abstract interface class StartupDeferredPluginsNativeBridge {
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

class MethodChannelStartupDeferredPluginsNativeBridge
    implements StartupDeferredPluginsNativeBridge {
  const MethodChannelStartupDeferredPluginsNativeBridge({
    this.channel = const MethodChannel('quwoquan/startup/deferred_plugins'),
  });

  final MethodChannel channel;

  @override
  Future<void> ensureRtc() => _ensureAndroidPlugin('ensureRtc');

  @override
  Future<void> ensureContentEntry() =>
      _ensureAndroidPlugin('ensureContentEntry');

  @override
  Future<void> ensureLocation() => _ensureAndroidPlugin('ensureLocation');

  Future<void> _ensureAndroidPlugin(String method) async {
    if (currentAppPlatform != AppPlatform.android) {
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
