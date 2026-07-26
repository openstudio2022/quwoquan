import 'package:flutter/services.dart';

enum OneTapAvailability {
  available,
  notConfigured,
  sdkUnavailable,
  probeTimeout,
  networkUnsupported,
  unsupportedPlatform,
  invalidProbe,
}

class OneTapLoginResult {
  const OneTapLoginResult({
    required this.vendor,
    required this.carrierToken,
    this.maskedPhone = '',
  });

  final String vendor;
  final String carrierToken;
  final String maskedPhone;
}

class OneTapLoginProbe {
  const OneTapLoginProbe({
    required this.availability,
    this.vendor = '',
    this.maskedPhone = '',
    this.carrierToken = '',
    this.expiresAt,
    this.reason = '',
  });

  final OneTapAvailability availability;
  final String vendor;
  final String maskedPhone;
  final String carrierToken;
  final DateTime? expiresAt;
  final String reason;

  bool get isAvailable => availability == OneTapAvailability.available;

  bool get canOfferLogin {
    final expiry = expiresAt;
    return isAvailable &&
        vendor.trim().isNotEmpty &&
        carrierToken.trim().isNotEmpty &&
        (expiry == null || expiry.isAfter(DateTime.now()));
  }
}

abstract interface class OneTapLoginClient {
  Future<bool> isAvailable();

  Future<OneTapLoginProbe> probe();

  Future<OneTapLoginResult> requestLoginToken();
}

/// `quwoquan/auth/one_tap` 的唯一业务侧原生通道防腐实现。
class MethodChannelOneTapLoginClient implements OneTapLoginClient {
  MethodChannelOneTapLoginClient({
    this._channel = const MethodChannel('quwoquan/auth/one_tap'),
  });

  final MethodChannel _channel;

  @override
  Future<bool> isAvailable() async {
    return (await probe()).canOfferLogin;
  }

  @override
  Future<OneTapLoginProbe> probe() async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>('probe');
      if (result == null) {
        return const OneTapLoginProbe(
          availability: OneTapAvailability.invalidProbe,
          reason: 'empty_probe',
        );
      }
      final expiresAtEpochMs = (result['expiresAtEpochMs'] as num?)?.toInt();
      final availability = _availabilityFromWire(
        result['availability']?.toString(),
      );
      return OneTapLoginProbe(
        availability: availability,
        vendor: result['vendor']?.toString().trim() ?? '',
        maskedPhone: result['maskedPhone']?.toString().trim() ?? '',
        carrierToken: result['carrierToken']?.toString().trim() ?? '',
        expiresAt: expiresAtEpochMs == null || expiresAtEpochMs <= 0
            ? null
            : DateTime.fromMillisecondsSinceEpoch(expiresAtEpochMs),
        reason: result['reason']?.toString().trim() ?? '',
      );
    } on MissingPluginException {
      return const OneTapLoginProbe(
        availability: OneTapAvailability.unsupportedPlatform,
        reason: 'missing_plugin',
      );
    } on PlatformException catch (error) {
      return OneTapLoginProbe(
        availability: _availabilityFromPlatformError(error.code),
        reason: error.code,
      );
    } on Object {
      return const OneTapLoginProbe(
        availability: OneTapAvailability.invalidProbe,
        reason: 'runtime_failure',
      );
    }
  }

  @override
  Future<OneTapLoginResult> requestLoginToken() async {
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'requestLoginToken',
    );
    final carrierToken = result?['carrierToken']?.toString().trim() ?? '';
    if (carrierToken.isEmpty) {
      throw StateError('one tap carrier token is empty');
    }
    return OneTapLoginResult(
      vendor: result?['vendor']?.toString().trim() ?? 'carrier',
      carrierToken: carrierToken,
      maskedPhone: result?['maskedPhone']?.toString().trim() ?? '',
    );
  }
}

OneTapAvailability _availabilityFromWire(String? raw) {
  final normalized = raw?.trim().toLowerCase() ?? '';
  for (final value in OneTapAvailability.values) {
    if (value.name.toLowerCase() == normalized) return value;
  }
  return OneTapAvailability.invalidProbe;
}

OneTapAvailability _availabilityFromPlatformError(String raw) {
  final code = raw.toLowerCase();
  if (code.contains('not_configured')) {
    return OneTapAvailability.notConfigured;
  }
  if (code.contains('timeout')) return OneTapAvailability.probeTimeout;
  if (code.contains('network')) return OneTapAvailability.networkUnsupported;
  if (code.contains('unsupported')) {
    return OneTapAvailability.unsupportedPlatform;
  }
  return OneTapAvailability.sdkUnavailable;
}
