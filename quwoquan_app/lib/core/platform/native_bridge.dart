import 'package:flutter/services.dart';

/// Anti-corruption boundary for app-owned native `MethodChannel` surfaces.
///
/// The app currently owns four native channels:
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
enum NativeAuthProvider { wechat, alipay, qq, apple, systemCredential, passkey }

enum NativeAuthAvailability { available, unavailable }

class NativeAuthCapability {
  const NativeAuthCapability({
    required this.provider,
    required this.availability,
    this.reason = '',
  });

  final NativeAuthProvider provider;
  final NativeAuthAvailability availability;
  final String reason;

  bool get isAvailable => availability == NativeAuthAvailability.available;
}

class NativeAuthResult {
  const NativeAuthResult({
    required this.provider,
    required this.ticket,
    this.maskedAccount = '',
    this.displayLabel = '',
    this.rawPayload = const <String, dynamic>{},
  });

  final NativeAuthProvider provider;
  final String ticket;
  final String maskedAccount;
  final String displayLabel;
  final Map<String, dynamic> rawPayload;
}

abstract interface class NativeAuthBridge {
  Future<NativeAuthCapability> getCapability(NativeAuthProvider provider);

  Future<NativeAuthResult> signIn(NativeAuthProvider provider);

  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  });
}

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
  }) async => const <String, dynamic>{};
}

class MethodChannelNativeAuthBridge implements NativeAuthBridge {
  MethodChannelNativeAuthBridge({
    this.channel = const MethodChannel('quwoquan/auth/native_bridge'),
  });

  final MethodChannel channel;

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    try {
      final result = await channel.invokeMapMethod<String, dynamic>(
        'getCapability',
        <String, dynamic>{'provider': provider.name},
      );
      final available = result?['available'] == true;
      return NativeAuthCapability(
        provider: provider,
        availability: available
            ? NativeAuthAvailability.available
            : NativeAuthAvailability.unavailable,
        reason: result?['reason']?.toString() ?? '',
      );
    } on MissingPluginException {
      return NativeAuthCapability(
        provider: provider,
        availability: NativeAuthAvailability.unavailable,
        reason: 'missing_plugin',
      );
    } on PlatformException catch (error) {
      return NativeAuthCapability(
        provider: provider,
        availability: NativeAuthAvailability.unavailable,
        reason: error.code,
      );
    }
  }

  @override
  Future<NativeAuthResult> signIn(NativeAuthProvider provider) async {
    final result = await channel.invokeMapMethod<String, dynamic>(
      'signIn',
      <String, dynamic>{'provider': provider.name},
    );
    return _resultFromMap(provider, result);
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) async {
    final result = await channel.invokeMapMethod<String, dynamic>(
      'signInWithPasskey',
      <String, dynamic>{
        if (relyingPartyId != null && relyingPartyId.isNotEmpty)
          'relyingPartyId': relyingPartyId,
        if (challenge != null && challenge.isNotEmpty) 'challenge': challenge,
      },
    );
    return _resultFromMap(NativeAuthProvider.passkey, result);
  }

  NativeAuthResult _resultFromMap(
    NativeAuthProvider provider,
    Map<String, dynamic>? result,
  ) {
    final ticket = result?['ticket']?.toString().trim() ?? '';
    if (ticket.isEmpty) {
      throw StateError('${provider.name} ticket is empty');
    }
    return NativeAuthResult(
      provider: provider,
      ticket: ticket,
      maskedAccount: result?['maskedAccount']?.toString().trim() ?? '',
      displayLabel: result?['displayLabel']?.toString().trim() ?? '',
      rawPayload: result == null
          ? const <String, dynamic>{}
          : Map<String, dynamic>.from(result),
    );
  }
}

/// Release-safe sandbox bridge for non-production environments (alpha/beta/gamma).
///
/// It is the端侧 counterpart of the server's mock/sandbox social provider client:
/// instead of invoking a real vendor SDK, it returns a short-lived sandbox
/// authorization ticket. The ticket is prefixed `sandbox-<provider>-` so the
/// gamma server-side controlled pass-through allowlist can recognize it; in
/// alpha/beta the server uses the mock provider client and accepts any ticket.
///
/// This is NOT test code: it is selected by runtime environment in
/// [nativeAuthBridgeProvider] and never wired in production.
class SandboxNativeAuthBridge implements NativeAuthBridge {
  SandboxNativeAuthBridge({Set<NativeAuthProvider>? socialProviders})
    : _socialProviders =
          socialProviders ??
          const <NativeAuthProvider>{
            NativeAuthProvider.wechat,
            NativeAuthProvider.alipay,
            NativeAuthProvider.qq,
          };

  final Set<NativeAuthProvider> _socialProviders;

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    final available = _socialProviders.contains(provider);
    return NativeAuthCapability(
      provider: provider,
      availability: available
          ? NativeAuthAvailability.available
          : NativeAuthAvailability.unavailable,
      reason: available ? 'sandbox' : 'unsupported_in_sandbox',
    );
  }

  @override
  Future<NativeAuthResult> signIn(NativeAuthProvider provider) async {
    if (!_socialProviders.contains(provider)) {
      throw StateError('${provider.name} sandbox auth is unavailable');
    }
    final entropy = DateTime.now().microsecondsSinceEpoch.toRadixString(36);
    return NativeAuthResult(
      provider: provider,
      ticket: 'sandbox-${provider.name}-$entropy',
      displayLabel: 'sandbox-${provider.name}',
    );
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) async {
    throw StateError('passkey sandbox auth is unavailable');
  }
}

class UnsupportedNativeAuthBridge implements NativeAuthBridge {
  const UnsupportedNativeAuthBridge();

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    return NativeAuthCapability(
      provider: provider,
      availability: NativeAuthAvailability.unavailable,
      reason: 'unsupported_platform',
    );
  }

  @override
  Future<NativeAuthResult> signIn(NativeAuthProvider provider) async {
    throw StateError('${provider.name} native auth is unavailable');
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) async {
    throw StateError('passkey native auth is unavailable');
  }
}
