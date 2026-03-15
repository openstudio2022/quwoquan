import 'package:quwoquan_app/assistant/internal_legacy/intent_bridge/method_channel_adapter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/tools/tool_schema.dart';

class MediaGalleryTool implements AssistantTool {
  MediaGalleryTool(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  @override
  String get name => 'media_gallery';

  @override
  String get description => 'Access gallery metadata with user permissions.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
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
      data: result,
    );
  }
}
