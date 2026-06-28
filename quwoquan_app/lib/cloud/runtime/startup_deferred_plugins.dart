import 'dart:async';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

/// Android 冷启动延后注册的重 native 插件（RTC / 创作入口）。
final class StartupDeferredPlugins {
  StartupDeferredPlugins._();

  static const MethodChannel _channel = MethodChannel(
    'quwoquan/startup/deferred_plugins',
  );

  static bool _rtcEnsured = false;
  static bool _contentEntryEnsured = false;

  static Future<void> ensureRtcPlugins() async {
    if (_rtcEnsured || currentAppPlatform != AppPlatform.android) {
      _rtcEnsured = true;
      return;
    }
    try {
      await _channel.invokeMethod<void>('ensureRtc');
      _rtcEnsured = true;
    } on MissingPluginException {
      _rtcEnsured = true;
    } on PlatformException {
      _rtcEnsured = true;
    }
  }

  static Future<void> ensureContentEntryPlugins() async {
    if (_contentEntryEnsured || currentAppPlatform != AppPlatform.android) {
      _contentEntryEnsured = true;
      return;
    }
    try {
      await _channel.invokeMethod<void>('ensureContentEntry');
      _contentEntryEnsured = true;
    } on MissingPluginException {
      _contentEntryEnsured = true;
    } on PlatformException {
      _contentEntryEnsured = true;
    }
  }
}
