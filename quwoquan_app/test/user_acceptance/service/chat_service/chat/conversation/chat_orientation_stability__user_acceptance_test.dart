// spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/spec.md#sit-001
/// Patrol UAT：真实 Remote 会话在物理设备横竖屏切换后保持消息与输入草稿。
///
/// 该 runner 不创建测试业务数据。执行方必须提供与当前 candidate 绑定、当前 actor
/// 有权访问且至少包含一条已知消息的 Conversation；测试只通过 production App 路由
/// 与 UI 消费它。Android 与 iPhone 的独立 ResultBundle 才能形成商业证据。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
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
const _conversationId = String.fromEnvironment(
  'QWQ_CHAT_ORIENTATION_CONVERSATION_ID',
);
const _expectedMessage = String.fromEnvironment(
  'QWQ_CHAT_ORIENTATION_EXPECTED_MESSAGE',
);
const _physicalDeviceConfirmed = bool.fromEnvironment(
  'QWQ_CHAT_ORIENTATION_PHYSICAL_DEVICE_ACK',
);

const _supportedOrientations = <DeviceOrientation>[
  DeviceOrientation.portraitUp,
  DeviceOrientation.portraitDown,
  DeviceOrientation.landscapeLeft,
  DeviceOrientation.landscapeRight,
];

void main() {
  patrolTest(
    'chat_remote_conversation_survives_physical_orientation_changes',
    tags: const ['user-acceptance', 'chat', 'orientation', 'physical-device'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      try {
        await launchPatrolAppOnce($);
        await patrolGoTo(
          $,
          AppRoutePaths.chatDetail(id: _conversationId.trim()),
        );
        await $(
          find.byType(ChatConversationPage),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));
        await $(
          find.textContaining(_expectedMessage.trim()),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));

        final input = find.byKey(TestKeys.chatInputTextField);
        await $(input).waitUntilVisible(timeout: const Duration(seconds: 20));
        final draft =
            'orientation-draft-${DateTime.now().microsecondsSinceEpoch}';
        await $.tester.enterText(input, draft);
        await $.pump();
        expect(find.text(draft), findsOneWidget);

        await _setAndVerifyOrientation(
          $,
          DeviceOrientation.landscapeLeft,
          Orientation.landscape,
          draft,
        );
        await _setAndVerifyOrientation(
          $,
          DeviceOrientation.portraitUp,
          Orientation.portrait,
          draft,
        );
        await _setAndVerifyOrientation(
          $,
          DeviceOrientation.landscapeRight,
          Orientation.landscape,
          draft,
        );
        await _setAndVerifyOrientation(
          $,
          DeviceOrientation.portraitUp,
          Orientation.portrait,
          draft,
        );
      } finally {
        await SystemChrome.setPreferredOrientations(_supportedOrientations);
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Chat orientation UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'Chat orientation UAT requires an injected authenticated actor; '
      'anonymous Patrol sessions are not evidence',
    );
  }
  final gateway = Uri.tryParse(_gatewayBaseUrl);
  if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
    throw StateError('Chat orientation UAT requires an absolute HTTPS gateway');
  }
  if (!_physicalDeviceConfirmed ||
      kIsWeb ||
      (defaultTargetPlatform != TargetPlatform.android &&
          defaultTargetPlatform != TargetPlatform.iOS)) {
    throw StateError(
      'Chat orientation UAT requires an acknowledged Android or iPhone '
      'physical device',
    );
  }
  if (_conversationId.trim().isEmpty || _expectedMessage.trim().isEmpty) {
    throw StateError(
      'Chat orientation UAT requires a candidate-bound conversationId and '
      'expected Remote message',
    );
  }
}

Future<void> _setAndVerifyOrientation(
  PatrolIntegrationTester $,
  DeviceOrientation deviceOrientation,
  Orientation expectedOrientation,
  String draft,
) async {
  await SystemChrome.setPreferredOrientations(<DeviceOrientation>[
    deviceOrientation,
  ]);
  final deadline = DateTime.now().add(const Duration(seconds: 10));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump(const Duration(milliseconds: 250));
    final page = find.byType(ChatConversationPage);
    if (page.evaluate().isNotEmpty &&
        MediaQuery.orientationOf(page.evaluate().first) ==
            expectedOrientation) {
      expect(find.textContaining(_expectedMessage.trim()), findsWidgets);
      expect(find.byKey(TestKeys.chatInputTextField), findsOneWidget);
      expect(find.text(draft), findsOneWidget);
      return;
    }
  }
  fail('Physical device did not reach $expectedOrientation before timeout');
}
