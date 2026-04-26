import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/app_action_contract.dart';
import 'package:quwoquan_app/assistant/contracts/app_search_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/intent_task_compiler.dart';
import 'package:quwoquan_app/assistant/orchestration/skill_match_policy.dart';

void main() {
  group('IntentTaskCompiler', () {
    const compiler = IntentTaskCompiler();

    test('compiles app search and app action tasks', () {
      final graph = compiler.compile(
        const UnderstandingResult(
          intents: <IntentNode>[
            IntentNode(
              intentId: 'intent_chat',
              intentType: 'chat.search',
              goal: '查我和张三昨天聊过什么',
              constraints: <IntentConstraint>[
                IntentConstraint(key: 'username', value: '张三'),
              ],
            ),
            IntentNode(
              intentId: 'intent_open_chat',
              intentType: 'chat.open',
              goal: '打开和张三的聊天',
              constraints: <IntentConstraint>[
                IntentConstraint(
                  key: 'conversationId',
                  value: 'conversation_1',
                ),
              ],
            ),
          ],
        ),
      );

      expect(graph.tasks, hasLength(2));
      expect(graph.tasks.first.taskId, 'task_chat');
      expect(graph.tasks.first.toolName, SkillMatchPolicy.appSearchToolName);
      final searchRequest = AppSearchRequest.fromJson(
        graph.tasks.first.toolArgs.toJson(),
      );
      expect(searchRequest.filters.username, '张三');

      expect(graph.tasks.last.taskId, 'task_open_chat');
      expect(graph.tasks.last.toolName, SkillMatchPolicy.appActionToolName);
      final actionRequest = AppActionRequest.fromJson(
        graph.tasks.last.toolArgs.toJson(),
      );
      expect(actionRequest.actionType, AppActionType.openConversation);
    });

    test(
      'skips unavailable intents that produce interaction directive only',
      () {
        final graph = compiler.compile(
          const UnderstandingResult(
            intents: <IntentNode>[
              IntentNode(
                intentId: 'intent_order',
                intentType: 'ticket.order',
                goal: '帮我订票',
              ),
            ],
          ),
        );

        expect(graph.tasks, isEmpty);
      },
    );
  });
}
