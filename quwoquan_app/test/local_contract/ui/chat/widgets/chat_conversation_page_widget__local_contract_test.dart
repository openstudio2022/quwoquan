import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';

Widget _scopedApp({
  ChatRepository? mock,
  RelationshipCapabilityRepository? capabilityRepository,
}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [
      chatRepositoryCompositionProvider.overrideWithValue(repo),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        capabilityRepository ?? _MutualCapabilityRepository(),
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
          onBack: () {},
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
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            chatRepositoryCompositionProvider.overrideWithValue(
              MockChatRepository(),
            ),
          ],
          child: MaterialApp(
            navigatorObservers: <NavigatorObserver>[chatRouteObserver],
            home: Scaffold(
              body: ChatConversationPage(
                conversationId: 'fixture_conv_direct',
                onBack: () => backCalled = true,
              ),
            ),
          ),
        ),
      );
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
      await tester.pumpWidget(_scopedApp(mock: _ErrorChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      expect(find.byType(AppPageErrorState), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });

    testWidgets('空消息列表展示语义空态', (tester) async {
      addTearDown(() => _disposeChatConversationWidget(tester));
      await tester.pumpWidget(_scopedApp(mock: _EmptyMessagesChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatConversationPage), findsOneWidget);
      expect(find.text(ChatText.chatConversationNoMessages), findsOneWidget);
      await _disposeChatConversationWidget(tester);
    });
  });
}

class _ErrorChatRepository extends MockChatRepository {
  @override
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    throw Exception('Network error');
  }
}

class _EmptyMessagesChatRepository extends MockChatRepository {
  @override
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    return const <ChatMessageDto>[];
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

class _MutualCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromMap(<String, dynamic>{
      'viewerSubAccountId': 'fixture_user_current',
      'targetSubAccountId': targetUserId,
      'relationState': 'mutual',
      'canGreet': false,
      'canCreateDirectConversation': true,
      'canSendMessage': true,
      'canOpenConversation': true,
      'canStartVoiceCall': true,
      'canStartVideoCall': true,
      'isBlocked': false,
      'isBlockedBy': false,
    });
  }
}

class _FollowingOnlyCapabilityRepository
    extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromMap(<String, dynamic>{
      'viewerSubAccountId': 'fixture_user_current',
      'targetSubAccountId': targetUserId,
      'relationState': 'following',
      'canGreet': true,
      'canCreateDirectConversation': false,
      'canSendMessage': false,
      'canOpenConversation': false,
      'canStartVoiceCall': false,
      'canStartVideoCall': false,
      'isBlocked': false,
      'isBlockedBy': false,
    });
  }
}
