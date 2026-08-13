/// user_acceptance Patrol: 群头像同步旅程
///
/// create-then-readback：disposable actor 经公开 Chat command 建群并发消息，
/// production App 打开会话列表断言该群行（含头像区）真实渲染——群行渲染
/// 即群头像组件走通了真实数据路径，空列表不是合法终态。
///
/// 分工声明：**成员头像变化的跨端传播正确性**由
/// `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/ci/run_chat_avatar_device_matrix.py`
/// 绑定的 probe 断言；本用例负责 App 侧「真实群会话在列表中可见」的
/// readback 基线，二者合并构成该旅程的完整验收。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';

import '../../../support/runtime/api_contract/chat_api_contract_harness.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    '群头像同步旅程渲染真实群会话行',
    tags: ['user-acceptance', 'chat', 'avatar'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      ChatApiContractHarness? harness;
      try {
        harness = await ChatApiContractHarness.create();
        final session = harness.session;
        final personaId = session.activePersona?.personaId.trim() ?? '';
        expect(personaId, isNotEmpty, reason: 'disposable actor needs persona');

        final title = '群头像同步验收 $suffix';
        final created = await harness.repository.createConversation(
          type: 'group',
          title: title,
          maxGroupSize: 500,
          idempotencyKey: 'group-avatar-sync-$suffix',
        );
        final conversationId = created.conversationId.trim();
        expect(conversationId, isNotEmpty, reason: 'group must have identity');
        await harness.sendMessage(conversationId, 'group-avatar-msg-$suffix');

        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await patrolGoTo($, AppRoutePaths.chat);
        await $(find.byType(ChatPage)).waitUntilVisible();
        final rowKey = ValueKey<String>('chat-inbox-row-$conversationId');
        final rendered = await _waitForGroupRow($, rowKey, title);
        expect(
          rendered,
          isTrue,
          reason:
              'chat home must render the created group row (with its avatar '
              'region); an empty inbox is not a legal terminal here',
        );
      } finally {
        await harness?.close();
      }
    },
  );
}

Future<bool> _waitForGroupRow(
  PatrolIntegrationTester $,
  ValueKey<String> rowKey,
  String title,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 25));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production Chat home entered an error terminal');
    }
    if (find.byKey(rowKey).evaluate().isNotEmpty &&
        find.text(title).evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}
