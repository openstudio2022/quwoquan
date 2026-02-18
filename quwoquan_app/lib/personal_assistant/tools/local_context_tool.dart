import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class LocalContextTool implements AssistantTool {
  LocalContextTool(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  @override
  String get name => 'local_context';

  @override
  String get description => 'Get device context like battery and permissions.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final result = await _channelAdapter.invoke(
      'getLocalContext',
      arguments,
    );
    if (result.containsKey('error')) {
      return AssistantToolResult(
        success: false,
        message: 'Local context failed: ${result['error']}',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
    return AssistantToolResult(
      success: true,
      message: 'Local context fetched',
      data: result,
    );
  }
}
