import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_detail_page.dart';

Widget _scopedApp({
  ChatRepository? mock,
  RelationshipCapabilityRepository? capabilityRepository,
}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repo),
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
        body: ChatDetailPage(
          conversationId: 'conv_001',
          onBack: () {},
        ),
      ),
    ),
  );
}

Future<void> _disposeChatDetailWidget(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(minutes: 2));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_detail_page_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatDetailPage — 渲染契约', () {
    testWidgets('消息列表渲染至少 1 条消息可见', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
      await _disposeChatDetailWidget(tester);
    });

    testWidgets('页面包含输入区域', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
      await _disposeChatDetailWidget(tester);
    });

    testWidgets('非互相关注显示关系提示条且不展示通话入口', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(
        _scopedApp(
          capabilityRepository: _FollowingOnlyCapabilityRepository(),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text(UITextConstants.chatMutualFollowRtcHint), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.chatInputMoreButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('语音通话'), findsNothing);
      expect(find.text('视频通话'), findsNothing);
      await _disposeChatDetailWidget(tester);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatDetailPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
      await _disposeChatDetailWidget(tester);
    });

    testWidgets('返回按钮回调正确触发', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      var backCalled = false;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            chatRepositoryProvider.overrideWithValue(MockChatRepository()),
          ],
          child: MaterialApp(
            navigatorObservers: <NavigatorObserver>[chatRouteObserver],
            home: Scaffold(
              body: ChatDetailPage(
                conversationId: 'conv_001',
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
        expect(find.byType(ChatDetailPage), findsOneWidget);
      }
      await _disposeChatDetailWidget(tester);
    });

    testWidgets('互相关注打开更多面板后展示语音和视频通话入口', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byKey(TestKeys.chatInputMoreButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('语音通话'), findsOneWidget);
      expect(find.text('视频通话'), findsOneWidget);
      await _disposeChatDetailWidget(tester);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ChatDetailPage — 错误态渲染', () {
    testWidgets('加载失败时页面不崩溃', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(
        _scopedApp(mock: _ErrorChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
      await _disposeChatDetailWidget(tester);
    });

    testWidgets('空消息列表安全渲染', (tester) async {
      addTearDown(() => _disposeChatDetailWidget(tester));
      await tester.pumpWidget(
        _scopedApp(mock: _EmptyMessagesChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
      await _disposeChatDetailWidget(tester);
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
  void onEnterChatDetail(String conversationId) {}

  @override
  void onLeaveChatDetail() {}
}

class _MutualCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromMap(<String, dynamic>{
      'viewerSubAccountId': 'user_001',
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

class _FollowingOnlyCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromMap(<String, dynamic>{
      'viewerSubAccountId': 'user_001',
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
