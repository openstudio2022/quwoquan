// readiness_case: chat_inbox_view_source_switch_app_uat
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001
/// disposable actor 只经公开 Chat command 创建会话与消息；API 先确认
/// ListMessageHome 已产生对应 typed row，production App 再在离页重入后从 Remote
/// 读回同一 conversation identity，禁止 fixture、seed 或本地 cache 伪成功。
///
/// 当前 Gamma 尚无受治理的四分区 selective failure、另一真实参与者与同一 candidate
/// Android+iPhone ResultBundle，因此本 source runner 不登记 readiness_case。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_CHAT_INBOX_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'chat_home_reloads_the_canonical_remote_message_home_row',
    tags: const ['user-acceptance', 'chat', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      ChatApiContractHarness? harness;

      try {
        harness = await ChatApiContractHarness.create();
        final session = harness.session;
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('Disposable Chat actor requires an active persona');
        }

        final title = '真实会话列表 $suffix';
        final created = await harness.repository.createConversation(
          type: 'group',
          title: title,
          maxGroupSize: 500,
          idempotencyKey: 'chat-inbox-conversation-$suffix',
        );
        final conversationId = created.conversationId.trim();
        if (conversationId.isEmpty) {
          throw StateError('CreateConversation returned an empty identity');
        }
        final message = await harness.sendMessage(
          conversationId,
          'chat-inbox-message-$suffix',
        );
        if (message.messageId.trim().isEmpty) {
          throw StateError('SendMessage returned an empty identity');
        }

        await _waitForRemoteMessageHome(
          harness,
          conversationId: conversationId,
          title: title,
        );
        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openChatAndWaitForConversation(
          $,
          conversationId: conversationId,
          title: title,
        );
        await patrolGoTo($, AppRoutePaths.home);
        await _openChatAndWaitForConversation(
          $,
          conversationId: conversationId,
          title: title,
        );

        final rows = await harness.repository.listMessageHome(
          filter: 'all',
          limit: 100,
        );
        expect(
          rows.where(
            (row) => row.conversationId == conversationId && row.title == title,
          ),
          hasLength(1),
        );
      } finally {
        await harness?.close();
      }
    },
  );
}

Future<void> _waitForRemoteMessageHome(
  ChatApiContractHarness harness, {
  required String conversationId,
  required String title,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    final rows = await harness.repository.listMessageHome(
      filter: 'all',
      limit: 100,
    );
    for (final row in rows) {
      if (row.conversationId == conversationId && row.title == title) {
        return;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('ListMessageHome did not materialize the sent message');
}

Future<void> _openChatAndWaitForConversation(
  PatrolIntegrationTester $, {
  required String conversationId,
  required String title,
}) async {
  await patrolGoTo($, AppRoutePaths.chat);
  await $(find.byType(ChatPage)).waitUntilVisible();
  final rowKey = ValueKey<String>('chat-inbox-row-$conversationId');
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production Chat home entered an error terminal');
    }
    if (find.byKey(rowKey).evaluate().isNotEmpty &&
        find.text(title).evaluate().isNotEmpty) {
      expect(find.byKey(rowKey), findsOneWidget);
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('production Chat home did not render the canonical MessageHome row');
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Chat inbox UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('Chat inbox UAT installs its own disposable session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError('Chat inbox UAT requires absolute HTTPS gateways');
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError('Chat inbox UAT requires one App/API gateway');
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_CHAT_INBOX_DISPOSABLE_ACTOR_ACK=true only when account closure '
      'cleanup is permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null &&
    value.isAbsolute &&
    value.scheme == 'https' &&
    value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}
