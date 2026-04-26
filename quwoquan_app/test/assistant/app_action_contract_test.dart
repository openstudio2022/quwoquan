import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/app_action_contract.dart';

void main() {
  group('AppAction contract', () {
    test('request round-trips app action arguments', () {
      const request = AppActionRequest(
        actionType: AppActionType.sendMessage,
        args: AppActionArgs(<String, Object?>{
          'conversationId': 'conversation_1',
          'recipientUserId': 'user_zhangsan',
          'draftText': '我晚点到',
        }),
        requiresConfirmation: true,
      );

      final decoded = AppActionRequest.fromJson(request.toJson());

      expect(decoded.contractId, 'app_action_request');
      expect(decoded.actionType, AppActionType.sendMessage);
      expect(decoded.args.fields['conversationId'], 'conversation_1');
      expect(decoded.args.fields['draftText'], '我晚点到');
      expect(decoded.requiresConfirmation, isTrue);
    });

    test('request falls back to navigation for unknown action', () {
      final decoded = AppActionRequest.fromJson(<String, dynamic>{
        'actionType': 'unknown_action',
      });

      expect(decoded.actionType, AppActionType.navigateToPage);
    });

    test('result round-trips executable outcome', () {
      const result = AppActionResult(
        assessment: AppActionAssessment.canExecuteWithTools,
        executed: true,
        result: AppActionArgs(<String, Object?>{
          'route': '/chat/conversation_1',
        }),
      );

      final decoded = AppActionResult.fromJson(result.toJson());

      expect(decoded.contractId, 'app_action_result');
      expect(decoded.assessment, AppActionAssessment.canExecuteWithTools);
      expect(decoded.isExecutable, isTrue);
      expect(decoded.executed, isTrue);
      expect(decoded.result.fields['route'], '/chat/conversation_1');
    });

    test('result round-trips unavailable action as structured state', () {
      const result = AppActionResult(
        assessment: AppActionAssessment.requiresUserAction,
        executed: false,
        missingTool: 'camera',
        missingPermission: 'camera',
        suggestedAlternative: '请先授权相机，或手动拍照后继续。',
      );

      final decoded = AppActionResult.fromJson(result.toJson());

      expect(decoded.assessment, AppActionAssessment.requiresUserAction);
      expect(decoded.isExecutable, isFalse);
      expect(decoded.executed, isFalse);
      expect(decoded.missingTool, 'camera');
      expect(decoded.missingPermission, 'camera');
      expect(decoded.suggestedAlternative, contains('授权相机'));
    });
  });
}
