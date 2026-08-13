// readiness_case: conversation_ime_input_app_uat
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/spec.md#sit-001
/// Patrol UAT：真实物理设备 IME 在 production Remote 会话发送中文与 Emoji。
///
/// 执行方必须注入当前 candidate 上当前 actor 可访问的 Conversation 与其中一条已知
/// Remote 消息；runner 不读取 Provider/port，也不创建 fixture 或测试业务数据。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';

import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _conversationId = String.fromEnvironment('QWQ_CHAT_IME_CONVERSATION_ID');
const _expectedRemoteMessage = String.fromEnvironment(
  'QWQ_CHAT_IME_EXPECTED_MESSAGE',
);
const _physicalDeviceConfirmed = bool.fromEnvironment(
  'QWQ_CHAT_IME_PHYSICAL_DEVICE_ACK',
);

void main() {
  patrolTest(
    'chat_remote_conversation_accepts_physical_ime_chinese_and_emoji',
    tags: const ['user-acceptance', 'chat', 'ime', 'physical-device'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);
      await _openConversation($);

      final input = find.byKey(TestKeys.chatInputTextField);
      await $(input).waitUntilVisible(timeout: const Duration(seconds: 20));
      await $.tester.tap(input);
      await $.pump();

      final message = '真实输入法消息 ${DateTime.now().microsecondsSinceEpoch} 😊🎉';
      await $.platform.mobile.enterText(
        Selector(text: ChatText.inputHint),
        text: message,
      );
      await $.pump();
      expect(find.text(message), findsOneWidget);

      await $(find.byKey(TestKeys.chatInputSendButton)).tap();
      await $(
        find.text(message),
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      await patrolGoTo($, AppRoutePaths.home);
      await $.pump(const Duration(seconds: 2));
      await _openConversation($);
      await $(
        find.text(message),
      ).waitUntilVisible(timeout: const Duration(seconds: 20));
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Chat IME UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'Chat IME UAT requires an injected authenticated actor; anonymous '
      'Patrol sessions are not evidence',
    );
  }
  final gateway = Uri.tryParse(_gatewayBaseUrl);
  if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
    throw StateError('Chat IME UAT requires an absolute HTTPS gateway');
  }
  if (!_physicalDeviceConfirmed ||
      kIsWeb ||
      (defaultTargetPlatform != TargetPlatform.android &&
          defaultTargetPlatform != TargetPlatform.iOS)) {
    throw StateError(
      'Chat IME UAT requires an acknowledged Android or iPhone physical '
      'device',
    );
  }
  if (_conversationId.trim().isEmpty || _expectedRemoteMessage.trim().isEmpty) {
    throw StateError(
      'Chat IME UAT requires a candidate-bound conversationId and expected '
      'Remote message',
    );
  }
}

Future<void> _openConversation(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.chatDetail(id: _conversationId.trim()));
  await $(
    find.byType(ChatConversationPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  await $(
    find.textContaining(_expectedRemoteMessage.trim()),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
}
