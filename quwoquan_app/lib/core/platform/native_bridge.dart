import 'package:flutter/services.dart';

/// Anti-corruption boundary for app-owned native `MethodChannel` surfaces.
///
/// The app currently owns five native channels:
///  - `quwoquan/auth/one_tap`        -> [OneTapLoginClient]
///                                      (one_tap_login_native_bridge.dart),
///                                      gated by `PlatformCapabilities.oneTapLogin`.
///  - `quwoquan/video_editing`       -> used by `IosVideoEditingService`, gated
///                                      by `PlatformCapabilities.nativeVideoEditing`.
///  - `personal_assistant/native_api`-> abstracted here as
///                                      [AssistantLocalContextBridge].
///  - `quwoquan/share/native_bridge` -> abstracted here as
///                                      [NativeShareBridge].
///  - `quwoquan/network/cellular_generation` -> 由此处的
///                                      [CellularNetworkProbe] 防腐抽象。
///
/// New native surfaces MUST be added behind an interface here (never a raw
/// `MethodChannel` in business code), and unimplemented platforms must return a
/// structured "unavailable" instead of crashing.
enum NativeAuthProvider { wechat, alipay, qq, apple, systemCredential, passkey }

enum NativeAuthAvailability {
  available,
  notConfigured,
  clientNotInstalled,
  probeTimeout,
  sdkUnavailable,
  unsupportedPlatform,
}

enum NativeShareTarget { wechatFriend, wechatMoments }

enum NativeShareAvailability { available, unavailable }

enum NativeShareOutcome { accepted, completed, cancelled, unavailable, failed }

/// 蜂窝接入代际的最小、隐私安全结果。
///
/// 仅用于将已确认的 mobile transport 细分为 telemetry `4g`/`5g`；
/// 无权限、未知或不支持的运行时必须返回 [unknown]，不得推断。
enum CellularNetworkGeneration { g5, g4, unknown }

class NativeShareWebpageCard {
  const NativeShareWebpageCard({
    required this.target,
    required this.requestId,
    required this.title,
    required this.description,
    required this.webpageUrl,
    this.thumbnail = const <int>[],
    this.referralDigest = '',
  });

  static const int maxThumbnailBytes = 32 * 1024;

  final NativeShareTarget target;
  final String requestId;
  final String title;
  final String description;
  final String webpageUrl;
  final List<int> thumbnail;
  final String referralDigest;

  bool get isValid {
    final uri = Uri.tryParse(webpageUrl.trim());
    return requestId.trim().isNotEmpty &&
        title.trim().isNotEmpty &&
        uri != null &&
        uri.scheme == 'https' &&
        uri.host.isNotEmpty &&
        thumbnail.length <= maxThumbnailBytes;
  }

  Map<String, dynamic> toChannelArguments() => <String, dynamic>{
    'target': target.name,
    'requestId': requestId.trim(),
    'title': title.trim(),
    'description': description.trim(),
    'webpageUrl': webpageUrl.trim(),
    'thumbnail': Uint8List.fromList(thumbnail),
    'referralDigest': referralDigest.trim(),
  };
}

class NativeShareCapability {
  const NativeShareCapability({
    required this.target,
    required this.availability,
    this.reason = '',
  });

  final NativeShareTarget target;
  final NativeShareAvailability availability;
  final String reason;

  bool get isAvailable => availability == NativeShareAvailability.available;
}

class NativeShareResult {
  const NativeShareResult({
    required this.target,
    required this.outcome,
    this.requestId = '',
    this.channel = '',
    this.referralDigest = '',
    this.occurredAt,
    this.reason = '',
  });

  final NativeShareTarget target;
  final NativeShareOutcome outcome;
  final String requestId;
  final String channel;
  final String referralDigest;
  final DateTime? occurredAt;
  final String reason;

  bool get isAccepted => outcome == NativeShareOutcome.accepted;
  bool get isCompleted => outcome == NativeShareOutcome.completed;
  bool get isCancelled => outcome == NativeShareOutcome.cancelled;
}

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

  bool get isDiscoverable =>
      availability != NativeAuthAvailability.unsupportedPlatform;
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

  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  });

  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  });
}

abstract interface class NativeShareBridge {
  Future<NativeShareCapability> getCapability(NativeShareTarget target);

  Future<NativeShareResult> shareWebpageCard(NativeShareWebpageCard card);

  Future<List<NativeShareResult>> consumePendingOutcomes();
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

/// App-owned native cellular generation bridge.
///
/// 该桥接层负责平台 API、权限和缺失插件的差异；业务与遥测代码只能消费
/// [CellularNetworkGeneration]，不能直接使用 MethodChannel 或平台判断。
abstract interface class CellularNetworkProbe {
  Future<CellularNetworkGeneration> readGeneration();
}

/// 上一次启动发生原生未捕获异常时的最小持久化标记。
///
/// 它刻意不携带异常消息或堆栈。
class NativeCrashMarker {
  const NativeCrashMarker({required this.kind});

  final String kind;
}

/// 读取并原子确认 App 自有的原生异常标记。
///
/// 原生未捕获异常无法投递给存活的 Dart isolate，因此 Android/iOS 在继续终止
/// 流程前持久化脱敏标记；下次启动再把它转换为标准运行时异常。
/// 信号级崩溃仍由获批准的平台崩溃报告器负责。
abstract interface class NativeCrashMarkerBridge {
  Future<NativeCrashMarker?> consumePreviousCrash();
}

class MethodChannelNativeCrashMarkerBridge implements NativeCrashMarkerBridge {
  const MethodChannelNativeCrashMarkerBridge({
    this.channel = const MethodChannel('quwoquan/runtime/native_crash_marker'),
  });

  final MethodChannel channel;

  @override
  Future<NativeCrashMarker?> consumePreviousCrash() async {
    try {
      final raw = await channel.invokeMethod<Object?>('consumePreviousCrash');
      if (raw is! Map) {
        return null;
      }
      final kind = raw['kind']?.toString().trim() ?? '';
      if (kind.isEmpty) {
        return null;
      }
      return NativeCrashMarker(kind: kind);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }
}

/// 上一次进程由平台判定的 ANR/hang 最小事实。
///
/// 平台只返回来源、发生时间和可选时长；不返回线程栈、异常文本或用户数据。
class NativeAnrMarker {
  const NativeAnrMarker({
    required this.source,
    required this.occurredAt,
    this.durationMs,
  });

  final String source;
  final DateTime occurredAt;
  final int? durationMs;
}

abstract interface class NativeAnrMarkerBridge {
  /// 读取但不删除上一进程的 ANR；只有产品遥测可靠入队后才允许确认。
  Future<NativeAnrMarker?> readPreviousAnr();

  /// 确认已可靠转存的原生事实。返回 false 时原生标记必须保留供下次启动重试。
  Future<bool> acknowledgePreviousAnr(NativeAnrMarker marker);
}

class MethodChannelNativeAnrMarkerBridge implements NativeAnrMarkerBridge {
  const MethodChannelNativeAnrMarkerBridge({
    this.channel = const MethodChannel('quwoquan/runtime/native_crash_marker'),
  });

  final MethodChannel channel;

  @override
  Future<NativeAnrMarker?> readPreviousAnr() async {
    try {
      final raw = await channel.invokeMethod<Object?>('readPreviousAnr');
      if (raw is! Map) {
        return null;
      }
      final source = switch (raw['source']?.toString().trim()) {
        'android_application_exit_info' => 'android_application_exit_info',
        'ios_metric_kit' => 'ios_metric_kit',
        _ => '',
      };
      final occurredAtEpochMs = switch (raw['occurredAtEpochMs']) {
        final int value => value,
        final num value => value.round(),
        _ => 0,
      };
      if (source.isEmpty || occurredAtEpochMs <= 0) {
        return null;
      }
      final rawDuration = raw['durationMs'];
      final durationMs = switch (rawDuration) {
        final int value when value >= 0 => value,
        final num value when value >= 0 => value.round(),
        _ => null,
      };
      return NativeAnrMarker(
        source: source,
        occurredAt: DateTime.fromMillisecondsSinceEpoch(
          occurredAtEpochMs,
          isUtc: true,
        ),
        durationMs: durationMs,
      );
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  @override
  Future<bool> acknowledgePreviousAnr(NativeAnrMarker marker) async {
    try {
      return await channel.invokeMethod<bool>(
            'acknowledgePreviousAnr',
            <String, Object?>{
              'occurredAtEpochMs': marker.occurredAt
                  .toUtc()
                  .millisecondsSinceEpoch,
            },
          ) ??
          false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }
}

class MethodChannelCellularNetworkProbe implements CellularNetworkProbe {
  MethodChannelCellularNetworkProbe({
    this.channel = const MethodChannel('quwoquan/network/cellular_generation'),
  });

  final MethodChannel channel;

  @override
  Future<CellularNetworkGeneration> readGeneration() async {
    try {
      final value = await channel.invokeMethod<String>('readGeneration');
      return switch (value) {
        'g5' => CellularNetworkGeneration.g5,
        'g4' => CellularNetworkGeneration.g4,
        _ => CellularNetworkGeneration.unknown,
      };
    } on MissingPluginException {
      return CellularNetworkGeneration.unknown;
    } on PlatformException {
      return CellularNetworkGeneration.unknown;
    }
  }
}

class UnsupportedCellularNetworkProbe implements CellularNetworkProbe {
  const UnsupportedCellularNetworkProbe();

  @override
  Future<CellularNetworkGeneration> readGeneration() async =>
      CellularNetworkGeneration.unknown;
}

class MethodChannelNativeShareBridge implements NativeShareBridge {
  MethodChannelNativeShareBridge({
    this.channel = const MethodChannel('quwoquan/share/native_bridge'),
  });

  final MethodChannel channel;

  @override
  Future<NativeShareCapability> getCapability(NativeShareTarget target) async {
    try {
      final result = await channel.invokeMapMethod<String, dynamic>(
        'getCapability',
        <String, dynamic>{'target': target.name},
      );
      final available = result?['available'] == true;
      return NativeShareCapability(
        target: target,
        availability: available
            ? NativeShareAvailability.available
            : NativeShareAvailability.unavailable,
        reason: result?['reason']?.toString() ?? '',
      );
    } on MissingPluginException {
      return NativeShareCapability(
        target: target,
        availability: NativeShareAvailability.unavailable,
        reason: 'missing_plugin',
      );
    } on PlatformException catch (error) {
      return NativeShareCapability(
        target: target,
        availability: NativeShareAvailability.unavailable,
        reason: error.code,
      );
    }
  }

  @override
  Future<NativeShareResult> shareWebpageCard(
    NativeShareWebpageCard card,
  ) async {
    if (!card.isValid) {
      return NativeShareResult(
        target: card.target,
        outcome: NativeShareOutcome.failed,
        requestId: card.requestId,
        reason: 'invalid_webpage_card',
      );
    }
    try {
      final result = await channel.invokeMapMethod<String, dynamic>(
        'shareWebpageCard',
        card.toChannelArguments(),
      );
      return _nativeShareResultFromMap(result, fallbackTarget: card.target);
    } on MissingPluginException {
      return NativeShareResult(
        target: card.target,
        outcome: NativeShareOutcome.unavailable,
        requestId: card.requestId,
        reason: 'missing_plugin',
      );
    } on PlatformException catch (error) {
      return NativeShareResult(
        target: card.target,
        outcome: NativeShareOutcome.failed,
        requestId: card.requestId,
        reason: error.code,
      );
    }
  }

  @override
  Future<List<NativeShareResult>> consumePendingOutcomes() async {
    try {
      final results = await channel.invokeListMethod<Map<dynamic, dynamic>>(
        'consumePendingOutcomes',
      );
      return (results ?? const <Map<dynamic, dynamic>>[])
          .map(
            (item) => _nativeShareResultFromMap(
              item.cast<String, dynamic>(),
              fallbackTarget: NativeShareTarget.wechatFriend,
            ),
          )
          .toList(growable: false);
    } on MissingPluginException {
      return const <NativeShareResult>[];
    } on PlatformException {
      return const <NativeShareResult>[];
    }
  }
}

class UnsupportedNativeShareBridge implements NativeShareBridge {
  const UnsupportedNativeShareBridge();

  @override
  Future<NativeShareCapability> getCapability(NativeShareTarget target) async {
    return NativeShareCapability(
      target: target,
      availability: NativeShareAvailability.unavailable,
      reason: 'unsupported_platform',
    );
  }

  @override
  Future<NativeShareResult> shareWebpageCard(
    NativeShareWebpageCard card,
  ) async {
    return NativeShareResult(
      target: card.target,
      outcome: NativeShareOutcome.unavailable,
      requestId: card.requestId,
      reason: 'unsupported_platform',
    );
  }

  @override
  Future<List<NativeShareResult>> consumePendingOutcomes() async =>
      const <NativeShareResult>[];
}

NativeShareResult _nativeShareResultFromMap(
  Map<String, dynamic>? result, {
  required NativeShareTarget fallbackTarget,
}) {
  final target = NativeShareTarget.values.firstWhere(
    (value) => value.name == result?['target']?.toString(),
    orElse: () => fallbackTarget,
  );
  final outcome = NativeShareOutcome.values.firstWhere(
    (value) => value.name == result?['outcome']?.toString(),
    orElse: () => NativeShareOutcome.failed,
  );
  return NativeShareResult(
    target: target,
    outcome: outcome,
    requestId: result?['requestId']?.toString() ?? '',
    channel: result?['channel']?.toString() ?? '',
    referralDigest: result?['referralDigest']?.toString() ?? '',
    occurredAt: _dateTimeFromMilliseconds(result?['occurredAtMillis']),
    reason: result?['reason']?.toString() ?? '',
  );
}

DateTime? _dateTimeFromMilliseconds(Object? raw) {
  final milliseconds = switch (raw) {
    int value => value,
    String value => int.tryParse(value),
    _ => null,
  };
  if (milliseconds == null || milliseconds <= 0) return null;
  return DateTime.fromMillisecondsSinceEpoch(milliseconds, isUtc: true);
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
      final reason = result?['reason']?.toString() ?? '';
      return NativeAuthCapability(
        provider: provider,
        availability: available
            ? NativeAuthAvailability.available
            : nativeAuthAvailabilityFromReason(reason),
        reason: reason,
      );
    } on MissingPluginException {
      return NativeAuthCapability(
        provider: provider,
        availability: NativeAuthAvailability.sdkUnavailable,
        reason: 'missing_plugin',
      );
    } on PlatformException catch (error) {
      return NativeAuthCapability(
        provider: provider,
        availability: nativeAuthAvailabilityFromReason(error.code),
        reason: error.code,
      );
    }
  }

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) async {
    final result = await channel
        .invokeMapMethod<String, dynamic>('signIn', <String, dynamic>{
          'provider': provider.name,
          if (authorizationPayload.isNotEmpty)
            'authorizationPayload': authorizationPayload,
        });
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

class UnsupportedNativeAuthBridge implements NativeAuthBridge {
  const UnsupportedNativeAuthBridge();

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    return NativeAuthCapability(
      provider: provider,
      availability: NativeAuthAvailability.unsupportedPlatform,
      reason: 'unsupported_platform',
    );
  }

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) async {
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

NativeAuthAvailability nativeAuthAvailabilityFromReason(String raw) {
  final reason = raw.trim().toLowerCase();
  if (reason.contains('not_configured') ||
      reason.contains('missing_config') ||
      reason.contains('credential')) {
    return NativeAuthAvailability.notConfigured;
  }
  if (reason.contains('not_installed') || reason.contains('client_missing')) {
    return NativeAuthAvailability.clientNotInstalled;
  }
  if (reason.contains('timeout')) {
    return NativeAuthAvailability.probeTimeout;
  }
  if (reason.contains('unsupported') || reason.contains('platform')) {
    return NativeAuthAvailability.unsupportedPlatform;
  }
  return NativeAuthAvailability.sdkUnavailable;
}
