import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';

class AndroidIntentAdapter {
  AndroidIntentAdapter(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  Future<Map<String, dynamic>> invokeIntent({
    required String action,
    Map<String, dynamic> extras = const <String, dynamic>{},
    String? data,
  }) async {
    return _channelAdapter.invoke('invokeAndroidIntent', <String, dynamic>{
      'action': action,
      'extras': extras,
      'data': data,
    });
  }
}
