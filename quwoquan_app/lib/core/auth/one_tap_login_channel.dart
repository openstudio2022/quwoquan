import 'package:flutter/services.dart';

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
    required this.isAvailable,
    this.vendor = '',
    this.maskedPhone = '',
    this.carrierToken = '',
    this.expiresAt,
  });

  final bool isAvailable;
  final String vendor;
  final String maskedPhone;
  final String carrierToken;
  final DateTime? expiresAt;
}

abstract class OneTapLoginClient {
  Future<bool> isAvailable();

  Future<OneTapLoginProbe> probe();

  Future<OneTapLoginResult> requestLoginToken();
}

class MethodChannelOneTapLoginClient implements OneTapLoginClient {
  MethodChannelOneTapLoginClient({
    this._channel = const MethodChannel('quwoquan/auth/one_tap'),
  });

  final MethodChannel _channel;

  @override
  Future<bool> isAvailable() async {
    try {
      return await _channel.invokeMethod<bool>('isAvailable') ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<OneTapLoginProbe> probe() async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>('probe');
      if (result == null) {
        return OneTapLoginProbe(isAvailable: await isAvailable());
      }
      final expiresAtEpochMs = (result['expiresAtEpochMs'] as num?)?.toInt();
      return OneTapLoginProbe(
        isAvailable: result['isAvailable'] as bool? ?? false,
        vendor: result['vendor']?.toString().trim() ?? '',
        maskedPhone: result['maskedPhone']?.toString().trim() ?? '',
        carrierToken: result['carrierToken']?.toString().trim() ?? '',
        expiresAt: expiresAtEpochMs == null || expiresAtEpochMs <= 0
            ? null
            : DateTime.fromMillisecondsSinceEpoch(expiresAtEpochMs),
      );
    } on MissingPluginException {
      return const OneTapLoginProbe(isAvailable: false);
    } on PlatformException {
      return const OneTapLoginProbe(isAvailable: false);
    } catch (_) {
      return const OneTapLoginProbe(isAvailable: false);
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
