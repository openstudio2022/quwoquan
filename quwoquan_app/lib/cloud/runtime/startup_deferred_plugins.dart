import 'dart:async';

import 'package:quwoquan_app/core/platform/startup_native_bridge.dart';

/// Android 冷启动延后注册的重 native 插件（RTC / 创作入口）。
final class StartupDeferredPlugins {
  StartupDeferredPlugins._();

  static const StartupDeferredPluginsNativeBridge _bridge =
      MethodChannelStartupDeferredPluginsNativeBridge();

  static bool _rtcEnsured = false;
  static bool _contentEntryEnsured = false;
  static bool _locationEnsured = false;

  static Future<void> ensureRtcPlugins() async {
    if (_rtcEnsured) {
      _rtcEnsured = true;
      return;
    }
    await _bridge.ensureRtc();
    _rtcEnsured = true;
  }

  static Future<void> ensureContentEntryPlugins() async {
    if (_contentEntryEnsured) {
      _contentEntryEnsured = true;
      return;
    }
    await _bridge.ensureContentEntry();
    _contentEntryEnsured = true;
  }

  static Future<void> ensureLocationPlugins() async {
    if (_locationEnsured) {
      _locationEnsured = true;
      return;
    }
    await _bridge.ensureLocation();
    _locationEnsured = true;
  }
}
