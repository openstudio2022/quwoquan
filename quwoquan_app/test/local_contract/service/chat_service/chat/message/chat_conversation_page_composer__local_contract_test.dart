import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/presentation/realtime_connection_notifier.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_message_command_writer_typed_double.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';
import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

final class _ComposerPersonaQuery extends Fake implements PersonaQuery {
  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData(
      personaId: 'fixture_user_current',
      ownerUserId: 'fixture_user_current',
      subjectType: 'persona',
      displayName: '会话测试用户',
      avatarUrl: '',
      contextVersion: 1,
    );
  }
}

final class _NoopRealtimeConnectionNotifier extends RealtimeConnectionNotifier {
  @override
  TransportState build() => TransportState.idle;

  @override
  void onAppForeground() {}

  @override
  void onAppBackground() {}

  @override
  void onEnterConversation(String conversationId) {}

  @override
  void onLeaveConversation() {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_composer_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('趣聊页使用微信式 composer：空态显示 emoji 和更多，输入后切发送', (tester) async {
    final repository = MockChatRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          chatInboxRepositoryProvider.overrideWithValue(repository),
          chatConversationRepositoryProvider.overrideWithValue(repository),
          chatMessageRepositoryProvider.overrideWithValue(repository),
          chatMemberRepositoryProvider.overrideWithValue(repository),
          personaQueryProvider(
            AppUiSurfaces.appShell,
          ).overrideWithValue(_ComposerPersonaQuery()),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            mutualRelationshipCapabilityRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(
            InMemoryChatMessageCommandWriter(),
          ),
          chatMessageTimelineCacheProvider.overrideWithValue(
            const EmptyChatMessageTimelineCache(),
          ),
          realtimeConnectionManagerProvider.overrideWith(
            _NoopRealtimeConnectionNotifier.new,
          ),
          voiceQueuedSenderProvider.overrideWithValue(
            (_, _) async => VoiceSendStatus.completed,
          ),
        ],
        child: MaterialApp(
          home: ChatConversationPage(
            conversationId: 'fixture_conv_group',
            onBack: _noop,
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(TestKeys.chatInputVoiceToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputEmojiToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputMoreButton), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, '新的会话输入');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byKey(TestKeys.chatInputEmojiToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputMoreButton), findsNothing);
    expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);
  });
}

void _noop() {}
