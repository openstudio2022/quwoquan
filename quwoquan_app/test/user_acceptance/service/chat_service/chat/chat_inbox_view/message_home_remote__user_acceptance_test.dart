// readiness_case: chat_inbox_view_source_switch_app_uat
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001
/// stackctl TestDataSession 只经公开 Chat command 创建会话与消息；
/// runner 把这些 opaque identity 交给 Patrol test host，production App 再在离页重入后
/// 从 Remote 读回同一 conversation/message identity，禁止 fixture、seed、二次创建
/// 或本地 cache 伪成功。
///
/// 当前 Gamma 尚无受治理的四分区 selective failure、另一真实参与者与同一 candidate
/// Android+iPhone ResultBundle，因此本 source runner 不登记 readiness_case。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';

import '../../../../../support/runtime/patrol/patrol_core_readback_support.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');

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
      final runnerSession = patrolRunnerInstalledAcceptanceSession;
      if (runnerSession == null) {
        throw StateError(
          'Message Home UAT requires a runner-installed actor session',
        );
      }
      final conversation = requirePatrolTestDataConversationForRunner();

      await launchPatrolAppOnce($);
      final mountedSession = patrolAuthenticatedSession(
        patrolMountedContainer(),
      );
      if (mountedSession.ownerId != runnerSession.ownerId ||
          mountedSession.activePersonaId != runnerSession.activePersonaId) {
        throw StateError(
          'Message Home UAT mounted a different runner actor identity',
        );
      }

      await _openChatAndWaitForConversation($, conversation);
      await patrolGoTo($, AppRoutePaths.home);
      await _openChatAndWaitForConversation($, conversation);
    },
  );
}

Future<void> _openChatAndWaitForConversation(
  PatrolIntegrationTester $,
  PatrolTestDataConversation conversation,
) async {
  await patrolGoTo($, AppRoutePaths.chat);
  await $(find.byType(ChatPage)).waitUntilVisible();
  final rowKey = ValueKey<String>(
    'chat-inbox-row-${conversation.conversationId}',
  );
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production Chat home entered an error terminal');
    }
    if (find.byKey(rowKey).evaluate().isNotEmpty) {
      await $.tap(find.byKey(rowKey));
      await $.pump();
      await $(find.byType(ChatConversationPage)).waitUntilVisible();
      await _waitForRunnerMessages($, conversation);
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('production Chat home did not render the canonical MessageHome row');
}

Future<void> _waitForRunnerMessages(
  PatrolIntegrationTester $,
  PatrolTestDataConversation conversation,
) async {
  final container = patrolMountedContainer();
  final expectedMessageIds = conversation.initialMessageIds.toSet();
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    final timeline = container.read(
      chatMessageTimelineProvider(conversation.conversationId),
    );
    final actualMessageIds = timeline.messages
        .map((message) => message.id)
        .toSet();
    if (expectedMessageIds.every(actualMessageIds.contains)) {
      return;
    }
    if (timeline.error != null &&
        !timeline.isLoading &&
        !timeline.isRefreshing) {
      fail('production Chat timeline entered an error terminal');
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail(
    'production Chat timeline did not load every runner-provisioned message',
  );
}

void _validateRuntimeInputs() {
  if (!const {'alpha', 'beta', 'gamma'}.contains(_apiContractEnv) ||
      _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Chat inbox UAT requires matching non-production APP_RUNTIME_ENV and '
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
