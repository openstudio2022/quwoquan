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

abstract class OneTapLoginClient {
  Future<bool> isAvailable();

  Future<OneTapLoginResult> requestLoginToken();
}

class MethodChannelOneTapLoginClient implements OneTapLoginClient {
  MethodChannelOneTapLoginClient({
    MethodChannel channel = const MethodChannel('quwoquan/auth/one_tap'),
  }) : _channel = channel;

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
