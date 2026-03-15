import 'dart:io';

import 'package:quwoquan_app/assistant/internal_legacy/intent_bridge/android_intent_adapter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/intent_bridge/ios_intent_adapter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/tools/tool_schema.dart';

class IntentBridgeTool implements AssistantTool {
  IntentBridgeTool({
    required IOSIntentAdapter iosAdapter,
    required AndroidIntentAdapter androidAdapter,
  })  : _iosAdapter = iosAdapter,
        _androidAdapter = androidAdapter;

  final IOSIntentAdapter _iosAdapter;
  final AndroidIntentAdapter _androidAdapter;

  @override
  String get name => 'intent_bridge';

  @override
  String get description =>
      'Bridge assistant skill into iOS AppIntent or Android Intent.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final target = (arguments['target'] as String?)?.trim() ?? '';
    try {
      Map<String, dynamic> result;
      if (target == 'ios_intent' || (target.isEmpty && Platform.isIOS)) {
        result = await _iosAdapter.invokeIntent(
          intentName: (arguments['intentName'] as String?)?.trim() ?? '',
          parameters:
              Map<String, dynamic>.from(arguments['parameters'] as Map? ?? const {}),
        );
      } else if (target == 'android_intent' || (target.isEmpty && Platform.isAndroid)) {
        result = await _androidAdapter.invokeIntent(
          action: (arguments['action'] as String?)?.trim() ?? 'android.intent.action.VIEW',
          extras: Map<String, dynamic>.from(arguments['extras'] as Map? ?? const {}),
          data: arguments['data'] as String?,
        );
      } else {
        return const AssistantToolResult(
          success: false,
          message: 'Unsupported intent target',
          errorCode: AssistantErrorCode.unsupportedTarget,
          degraded: true,
        );
      }
      if (result.containsKey('error')) {
        return AssistantToolResult(
          success: false,
          message: 'Intent execution failed: ${result['error']}',
          errorCode: AssistantErrorCode.executionFailed,
          degraded: true,
        );
      }
      return AssistantToolResult(
        success: true,
        message: 'Intent execution success',
        data: result,
      );
    } catch (error) {
      return AssistantToolResult(
        success: false,
        message: 'Intent bridge error: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }
}
