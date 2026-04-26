import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/app_action_contract.dart';
import 'package:quwoquan_app/assistant/tool/impl/device/app_action_tool.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

void main() {
  test('app_action tool returns structured requiresUserAction for send message', () async {
    final tool = AppActionTool();

    final result = await tool.execute(
      AssistantToolArguments.fromJson(
        const AppActionRequest(
          actionType: AppActionType.sendMessage,
          args: AppActionArgs(<String, Object?>{
            'recipientUserId': 'user_zhangsan',
            'draftText': '我晚点到',
          }),
          requiresConfirmation: true,
        ).toJson(),
      ),
    );

    final actionResult = AppActionResult.fromJson(
      result.data?.toDynamicJson() ?? const <String, dynamic>{},
    );

    expect(result.success, isTrue);
    expect(actionResult.assessment, AppActionAssessment.requiresUserAction);
    expect(actionResult.executed, isFalse);
    expect(actionResult.missingTool, 'message_sender');
    expect(actionResult.result.fields['actionType'], 'send_message');
    expect(actionResult.result.fields['requiresConfirmation'], isTrue);
  });
}
