import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';

class IOSIntentAdapter {
  IOSIntentAdapter(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  Future<Map<String, dynamic>> invokeIntent({
    required String intentName,
    required Map<String, dynamic> parameters,
  }) async {
    return _channelAdapter.invoke('invokeIosIntent', <String, dynamic>{
      'intentName': intentName,
      'parameters': parameters,
    });
  }
}
