import 'package:flutter/services.dart';

/// Anti-corruption boundary for app-owned native `MethodChannel` surfaces.
///
/// The app currently owns three native channels:
///  - `quwoquan/auth/one_tap`        -> already abstracted by `OneTapLoginClient`
///                                      (core/auth/one_tap_login_channel.dart),
///                                      gated by `PlatformCapabilities.oneTapLogin`.
///  - `quwoquan/video_editing`       -> used by `IosVideoEditingService`, gated
///                                      by `PlatformCapabilities.nativeVideoEditing`.
///  - `personal_assistant/native_api`-> abstracted here as
///                                      [AssistantLocalContextBridge].
///
/// New native surfaces MUST be added behind an interface here (never a raw
/// `MethodChannel` in business code), and unimplemented platforms must return a
/// structured "unavailable" instead of crashing.
abstract interface class AssistantLocalContextBridge {
  /// Whether a native local-context provider is wired on this platform.
  bool get isSupported;

  /// Fetches on-device context (device/locale/permissions/location) for the
  /// assistant. Returns an empty map when unsupported; never throws for a
  /// missing platform implementation.
  Future<Map<String, dynamic>> getLocalContext({
    List<String> requestedFields = const <String>[],
  });
}

/// Default implementation backed by the `personal_assistant/native_api` channel.
/// Returns an empty context (rather than throwing) when the platform has no
/// implementation registered, so the assistant degrades gracefully.
class MethodChannelAssistantLocalContextBridge
    implements AssistantLocalContextBridge {
  MethodChannelAssistantLocalContextBridge({
    this.channel = const MethodChannel('personal_assistant/native_api'),
  });

  final MethodChannel channel;

  @override
  bool get isSupported => true;

  @override
  Future<Map<String, dynamic>> getLocalContext({
    List<String> requestedFields = const <String>[],
  }) async {
    try {
      final result = await channel.invokeMapMethod<String, dynamic>(
        'getLocalContext',
        <String, dynamic>{'requestedFields': requestedFields},
      );
      return result ?? const <String, dynamic>{};
    } on MissingPluginException {
      return const <String, dynamic>{};
    } on PlatformException {
      return const <String, dynamic>{};
    }
  }
}

/// Used on platforms with no native local-context provider (web, ohos initial).
class UnsupportedAssistantLocalContextBridge
    implements AssistantLocalContextBridge {
  const UnsupportedAssistantLocalContextBridge();

  @override
  bool get isSupported => false;

  @override
  Future<Map<String, dynamic>> getLocalContext({
    List<String> requestedFields = const <String>[],
  }) async =>
      const <String, dynamic>{};
}
