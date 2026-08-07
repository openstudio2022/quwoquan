import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';

const _fixtureConversationId = 'fixture_conv_direct';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_conversation_uat_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('用户进入真实会话页并通过主 CTA 发送强类型消息', (tester) async {
    final writer = _RecordingMessageWriter();
    var backInvoked = false;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          chatMessageTimelineCacheProvider.overrideWithValue(
            const EmptyChatMessageTimelineCache(),
          ),
          contentConfigRepositoryProvider.overrideWithValue(
            MockContentRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _MutualRelationshipCapability(),
          ),
          realtimeConnectionManagerProvider.overrideWith(
            _NoopRealtimeConnectionNotifier.new,
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData(
              personaId: 'persona_chat_uat',
              ownerUserId: 'user_chat_uat',
              subjectType: 'persona',
              displayName: '会话验收用户',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSessionController.new,
          ),
        ],
        child: MaterialApp(
          navigatorObservers: <NavigatorObserver>[chatRouteObserver],
          home: _AuthWarmup(
            child: ChatConversationPage(
              conversationId: _fixtureConversationId,
              onBack: () => backInvoked = true,
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(find.byType(ChatConversationPage), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputTextField), findsOneWidget);

    await tester.enterText(
      find.byKey(TestKeys.chatInputTextField),
      '真实会话页发送验收',
    );
    await tester.pump();
    expect(find.byKey(TestKeys.chatInputSendButton), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.chatInputSendButton));
    await tester.pump(const Duration(milliseconds: 350));

    expect(writer.lastCommand?.conversationId, _fixtureConversationId);
    expect(writer.lastCommand?.type, 'text');
    expect(writer.lastCommand?.content, '真实会话页发送验收');
    final container = ProviderScope.containerOf(
      tester.element(find.byType(ChatConversationPage)),
    );
    expect(
      container
          .read(chatMessageTimelineProvider(_fixtureConversationId))
          .messages
          .any((message) => message.content == '真实会话页发送验收'),
      isTrue,
    );

    final backButton = find.byIcon(Icons.arrow_back_ios_new);
    if (backButton.evaluate().isNotEmpty) {
      await tester.tap(backButton.first);
      await tester.pump();
      expect(backInvoked, isTrue);
    }

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('关系能力拒绝发送时主 CTA 禁用且不产生副作用', (tester) async {
    final writer = _RecordingMessageWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          chatMessageTimelineCacheProvider.overrideWithValue(
            const EmptyChatMessageTimelineCache(),
          ),
          contentConfigRepositoryProvider.overrideWithValue(
            MockContentRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _BlockedRelationshipCapability(),
          ),
          realtimeConnectionManagerProvider.overrideWith(
            _NoopRealtimeConnectionNotifier.new,
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSessionController.new,
          ),
        ],
        child: MaterialApp(
          navigatorObservers: <NavigatorObserver>[chatRouteObserver],
          home: const _AuthWarmup(
            child: ChatConversationPage(
              conversationId: _fixtureConversationId,
              onBack: _noop,
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    final input = tester.widget<TextField>(
      find.byKey(TestKeys.chatInputTextField),
    );
    expect(input.enabled, isFalse);
    expect(writer.lastCommand, isNull);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
  }
}

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_chat_uat',
    activePersonaId: 'persona_chat_uat',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

class _RecordingMessageWriter implements ChatMessageCommandWriter {
  ChatSendMessageCommand? lastCommand;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    lastCommand = command;
    return ChatSendMessageResult(
      messageId: 'message_${command.clientMsgId}',
      seq: 100,
      timestamp: DateTime.utc(2026, 7, 15),
    );
  }
}

class _NoopRealtimeConnectionNotifier extends RealtimeConnectionNotifier {
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

class _MutualRelationshipCapability extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return _relationshipCapability(targetUserId: targetUserId, allowed: true);
  }
}

class _BlockedRelationshipCapability extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return _relationshipCapability(targetUserId: targetUserId, allowed: false);
  }
}

RelationshipCapabilityViewData _relationshipCapability({
  required String targetUserId,
  required bool allowed,
}) {
  return RelationshipCapabilityViewData(
    viewerPersonaId: 'persona_chat_uat',
    targetPersonaId: targetUserId,
    relationState: allowed ? 'mutual' : 'blocked',
    canFollow: false,
    canUnfollow: allowed,
    canFollowBack: false,
    canGreet: false,
    canCreateDirectConversation: allowed,
    canSendMessage: allowed,
    canOpenConversation: allowed,
    hasPendingGreeting: false,
    hasFormalConversation: allowed,
    canStartVoiceCall: allowed,
    canStartVideoCall: allowed,
    isBlocked: !allowed,
    isBlockedBy: false,
  );
}

void _noop() {}
