import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';

import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_message_command_writer_typed_double.dart';
import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';
import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

const _testPersonaContext = ActivePersonaContextViewData(
  personaId: 'fixture_persona_daily',
  ownerUserId: 'fixture_user_current',
  subjectType: 'person',
  displayName: '测试用户',
  avatarUrl: '',
  isPrimary: true,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // 本地会话搜索索引是真实 SQLite 投影，不是替身；VM 单测用 FFI 提供真实实现。
  setUpAll(ensureSqfliteFfiInitialized);

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_realtime_journey_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('会话页进入后 contract fixture realtime 追加新消息', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          // 被测行为是 realtime 事件如何落到会话页；出站 HTTP 边界保持封死，
          // 会话/身份/关系只以对象级 typed port 形式提供。
          ...sealedCloudBoundaryOverrides(),
          activePersonaContextProvider.overrideWith(
            (ref) async => _testPersonaContext,
          ),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => _testPersonaContext,
          ),
          authSessionControllerProvider.overrideWith(
            TestAuthenticatedSessionController.new,
          ),
          realtimeConnectionManagerProvider.overrideWith(
            () => RealtimeConnectionNotifier(
              delegateFactory:
                  ({
                    required ref,
                    required onStateChanged,
                    required currentUserIdResolver,
                  }) => FixtureRealtimeConnectionDelegate(
                    read: ref.read,
                    invalidate: ref.invalidate,
                    onStateChanged: onStateChanged,
                  ),
            ),
          ),
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            mutualRelationshipCapabilityRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(
            InMemoryChatMessageCommandWriter(),
          ),
          voiceQueuedSenderProvider.overrideWithValue(
            (_, _) async => VoiceSendStatus.completed,
          ),
        ],
        child: MaterialApp(
          navigatorObservers: <NavigatorObserver>[chatRouteObserver],
          home: ChatConversationPage(conversationId: 'conv_001', onBack: _noop),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    final beforeCount = tester
        .container()
        .read(chatMessageProvider('conv_001'))
        .messages
        .length;

    await tester.pump(const Duration(milliseconds: 400));

    final afterMessages = tester
        .container()
        .read(chatMessageProvider('conv_001'))
        .messages;
    expect(afterMessages.length, greaterThan(beforeCount));
    expect(
      afterMessages.any(
        (message) =>
            message.content?.contains('Fixture Realtime 新消息：咖啡馆门口见。') ?? false,
      ),
      isTrue,
    );

    tester
        .container()
        .read(realtimeConnectionManagerProvider.notifier)
        .onAppBackground();
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

void _noop() {}
