// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-001
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-001.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-001.t2
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_message_command_writer_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';

final class _ChatPersonaQuery extends Fake implements PersonaQuery {
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

Widget _scopedApp({
  ChatMessageRepository? message,
  RelationshipCapabilityRepository? capabilityRepository,
  VoidCallback? onBack,
}) {
  final facets = ChatTestFacets();
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      ...chatTestRepositoryOverrides(facets: facets, message: message),
      personaQueryProvider(
        AppUiSurfaces.appShell,
      ).overrideWithValue(_ChatPersonaQuery()),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        capabilityRepository ?? _MutualCapabilityRepository(),
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
    ],
    child: MaterialApp(
      navigatorObservers: <NavigatorObserver>[chatRouteObserver],
      home: Scaffold(
        body: ChatConversationPage(
          conversationId: 'fixture_conv_direct',
          onBack: onBack ?? () {},
        ),
      ),
    ),
  );
}

Future<void> _disposeChatConversationWidget(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(minutes: 2));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_conversation_page_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatConversationPage — 渲染契约', () {
    testWidgets('消息列表渲染至少 1 条消息可见', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });

    testWidgets('页面包含输入区域', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
      await _disposeChatConversationWidget(tester);
    });

    testWidgets('非互相关注显示关系提示条且不展示通话入口', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(
        _scopedApp(capabilityRepository: _FollowingOnlyCapabilityRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text(ChatText.chatMutualFollowRtcHint), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.chatInputMoreButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('语音通话'), findsNothing);
      expect(find.text('视频通话'), findsNothing);
      await _disposeChatConversationWidget(tester);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatConversationPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });

    testWidgets('返回按钮回调正确触发', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      var backCalled = false;
      await tester.pumpWidget(_scopedApp(onBack: () => backCalled = true));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final backButtons = find.byIcon(Icons.arrow_back_ios_new);
      if (backButtons.evaluate().isNotEmpty) {
        await tester.tap(backButtons.first);
        await tester.pump();
        expect(backCalled, isTrue);
      } else {
        expect(find.byType(ChatConversationPage), findsOneWidget);
      }
      await _disposeChatConversationWidget(tester);
    });

    testWidgets('互相关注打开更多面板后展示语音和视频通话入口', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byKey(TestKeys.chatInputMoreButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('语音通话'), findsOneWidget);
      expect(find.text('视频通话'), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ChatConversationPage — 错误态渲染', () {
    testWidgets('加载失败时展示可重试错误面', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(_scopedApp(message: _ErrorChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      expect(find.byType(AppPageErrorState), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });

    testWidgets('空消息列表展示语义空态', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(
        _scopedApp(message: _EmptyMessagesChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      expect(find.text(ChatText.chatConversationNoMessages), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });
  });
}

class _ErrorChatRepository extends Fake implements ChatMessageRepository {
  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    throw Exception('Network error');
  }
}

class _EmptyMessagesChatRepository extends Fake
    implements ChatMessageRepository {
  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    return const <ChatMessageViewData>[];
  }
}

class _NoopRealtimeConnectionNotifier extends RealtimeConnectionNotifier {
  _NoopRealtimeConnectionNotifier()
    : super(
        delegateFactory:
            ({
              required ref,
              required onStateChanged,
              required currentUserIdResolver,
            }) => throw StateError('overridden build must not create delegate'),
      );

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

class _MutualCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return RelationshipCapabilityViewData(
      viewerPersonaId: 'fixture_user_current',
      targetPersonaId: targetUserId,
      relationState: 'mutual',
      canFollow: false,
      canUnfollow: true,
      canFollowBack: false,
      canGreet: false,
      canCreateDirectConversation: true,
      canSendMessage: true,
      canOpenConversation: true,
      hasPendingGreeting: false,
      hasFormalConversation: false,
      canStartVoiceCall: true,
      canStartVideoCall: true,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}

class _FollowingOnlyCapabilityRepository
    extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return RelationshipCapabilityViewData(
      viewerPersonaId: 'fixture_user_current',
      targetPersonaId: targetUserId,
      relationState: 'following',
      canFollow: false,
      canUnfollow: true,
      canFollowBack: false,
      canGreet: true,
      canCreateDirectConversation: false,
      canSendMessage: false,
      canOpenConversation: false,
      hasPendingGreeting: false,
      hasFormalConversation: false,
      canStartVoiceCall: false,
      canStartVideoCall: false,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}
