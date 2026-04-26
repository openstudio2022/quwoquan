import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/app_action_contract.dart';
import 'package:quwoquan_app/assistant/contracts/app_search_contract.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/skill_match_policy.dart';

void main() {
  group('SkillMatchPolicy', () {
    const policy = SkillMatchPolicy();

    test('routes chat search intent to app_search', () {
      final decision = policy.route(
        const IntentNode(
          intentId: 'intent_chat',
          intentType: 'chat.search',
          goal: '查我和张三昨天聊过什么',
          constraints: <IntentConstraint>[
            IntentConstraint(key: 'username', value: '张三'),
            IntentConstraint(key: 'keywords', value: '聚餐,餐厅'),
          ],
        ),
      );

      final request = AppSearchRequest.fromJson(decision.toolArgs.toJson());

      expect(decision.toolName, SkillMatchPolicy.appSearchToolName);
      expect(request.contentTypes, <AppSearchContentType>[
        AppSearchContentType.chatMessage,
      ]);
      expect(request.filters.username, '张三');
      expect(request.filters.keywords, <String>['聚餐', '餐厅']);
    });

    test('routes app action intent to app_action', () {
      final decision = policy.route(
        const IntentNode(
          intentId: 'intent_send',
          intentType: 'message.send',
          goal: '给张三发消息',
          constraints: <IntentConstraint>[
            IntentConstraint(key: 'recipientUserId', value: 'user_zhangsan'),
            IntentConstraint(key: 'draftText', value: '我晚点到'),
          ],
        ),
      );

      final request = AppActionRequest.fromJson(decision.toolArgs.toJson());

      expect(decision.toolName, SkillMatchPolicy.appActionToolName);
      expect(request.actionType, AppActionType.sendMessage);
      expect(request.requiresConfirmation, isTrue);
      expect(request.args.fields['draftText'], '我晚点到');
    });

    test('routes evidence intent to web_search fallback', () {
      final decision = policy.route(
        const IntentNode(
          intentId: 'intent_weather',
          intentType: 'weather.retrieve',
          goal: '深圳今天天气',
          requiresEvidence: true,
        ),
      );

      expect(decision.toolName, SkillMatchPolicy.webSearchToolName);
      expect(decision.toolArgs.fields['query'], '深圳今天天气');
    });

    test('routes unavailable operation to interaction directive', () {
      final decision = policy.route(
        const IntentNode(
          intentId: 'intent_order',
          intentType: 'ticket.order',
          goal: '帮我订票',
        ),
      );

      expect(decision.toolName, isEmpty);
      expect(
        decision.interactionDirective.kind,
        InteractionDirectiveKind.requiresUserAction,
      );
      expect(decision.interactionDirective.intentId, 'intent_order');
    });
  });
}
