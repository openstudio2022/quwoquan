import 'package:quwoquan_app/assistant/intent_bridge/assistant_intent_bridge_runtime.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class MediaGalleryTool implements AssistantTool {
  MediaGalleryTool(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  @override
  String get name => 'media_gallery';

  @override
  String get description => 'Access gallery metadata with user permissions.';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final result = await _channelAdapter.invoke('queryGallery', arguments);
    if (result.containsKey('error')) {
      return AssistantToolResult(
        success: false,
        message: 'Gallery query failed: ${result['error']}',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
    return AssistantToolResult(
      success: true,
      message: 'Gallery query success',
      data: AssistantToolResultData.fromJson(result),
    );
  }
}
