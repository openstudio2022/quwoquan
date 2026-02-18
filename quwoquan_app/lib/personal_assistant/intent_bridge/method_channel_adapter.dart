import 'package:flutter/services.dart';

class MethodChannelAdapter {
  MethodChannelAdapter({
    MethodChannel? channel,
  }) : _channel = channel ?? const MethodChannel('personal_assistant/native_api');

  final MethodChannel _channel;

  Future<Map<String, dynamic>> invoke(
    String method,
    Map<String, dynamic> arguments,
  ) async {
    try {
      final result = await _channel.invokeMethod<dynamic>(method, arguments);
      if (result is Map) {
        return Map<String, dynamic>.from(result);
      }
      return <String, dynamic>{'result': result};
    } catch (error) {
      return <String, dynamic>{
        'error': error.toString(),
      };
    }
  }
}
