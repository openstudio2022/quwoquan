// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-002.t1
//
// 会话页整页 widget 证据：
// 1. 历史分页的可视位置保持（GWT-002 前半句）：滚动到顶部触发加载更早
//    历史后，原本可见的消息在屏幕上的位置不跳变（offset 补偿）。
// 2. 文件消息消费动作：交付 URL 缺失时点击给出结构化不可用提示。
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_message_command_writer_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

const _conversationId = 'conv_paging_anchor';
const _totalSeq = 70;
const _pageSize = 50;

ChatMessageViewData _message(int seq) => ChatMessageViewData(
  id: 'anchor_msg_$seq',
  conversationId: _conversationId,
  seq: seq,
  clientMsgId: 'anchor_client_$seq',
  senderId: 'fixture_user_peer',
  senderName: '对方',
  type: 'text',
  content: '锚点消息 $seq',
  status: 'sent',
  timestamp: DateTime.utc(2026, 8, 13, 8, seq % 60),
);

/// 单页仅一条文件消息（交付 URL 缺失）的最小 repo。
final class _FileMessageRepository extends Fake
    implements ChatMessageRepository {
  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = _pageSize,
  }) async {
    return <ChatMessageViewData>[
      ChatMessageViewData(
        id: 'file_msg_1',
        conversationId: _conversationId,
        seq: 1,
        clientMsgId: 'file_client_1',
        senderId: 'fixture_user_peer',
        senderName: '对方',
        type: 'file',
        content: '活动报名表.pdf',
        status: 'sent',
        timestamp: DateTime.utc(2026, 8, 13, 8),
      ),
    ];
  }
}

/// 首屏加载带 200ms 延迟的最小 repo（制造骨架屏可观测窗口）。
final class _SlowFirstPageRepository extends Fake
    implements ChatMessageRepository {
  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = _pageSize,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 200));
    return <ChatMessageViewData>[_message(1)];
  }
}

/// 单页仅一条图片消息（带交付 URL）的最小 repo。
final class _ImageMessageRepository extends Fake
    implements ChatMessageRepository {
  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = _pageSize,
  }) async {
    return <ChatMessageViewData>[
      ChatMessageViewData(
        id: 'image_msg_1',
        conversationId: _conversationId,
        seq: 1,
        clientMsgId: 'image_client_1',
        senderId: 'fixture_user_peer',
        senderName: '对方',
        type: 'image',
        content: '',
        mediaDeliveryUrl: 'https://image.example.test/media/image/photo.jpg',
        mediaType: 'image',
        status: 'sent',
        timestamp: DateTime.utc(2026, 8, 13, 8),
      ),
    ];
  }
}

/// 两页历史：首屏返回 seq 21..40，翻页返回 seq 1..20。
/// 翻页带人为延迟：留出「用户已滚到顶、历史尚未插入」的位置观测窗口。
final class _TwoPageMessageRepository extends Fake
    implements ChatMessageRepository {
  int listCallCount = 0;

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = _pageSize,
  }) async {
    listCallCount += 1;
    final beforeSeq = int.tryParse(before ?? '') ?? (_totalSeq + 1);
    final floor = beforeSeq > 21 ? 21 : 1;
    if (floor == 1) {
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    final page = <ChatMessageViewData>[];
    for (var seq = beforeSeq - 1; seq >= floor && page.length < limit; seq--) {
      page.add(_message(seq));
    }
    return page;
  }
}

final class _NoopRealtimeDelegate implements RealtimeConnectionDelegate {
  @override
  TransportState get state => TransportState.disconnected;

  @override
  void onAppForeground() {}

  @override
  void onAppBackground() {}

  @override
  void onEnterConversation(String conversationId) {}

  @override
  void onLeaveConversation() {}

  @override
  void dispose() {}
}

final class _NoopRealtimeConnectionNotifier extends RealtimeConnectionNotifier {
  _NoopRealtimeConnectionNotifier()
    : super(
        delegateFactory:
            ({
              required ref,
              required onStateChanged,
              required currentUserIdResolver,
            }) => _NoopRealtimeDelegate(),
      );
}

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'anchor-token',
    refreshToken: 'anchor-refresh',
    ownerId: 'user_anchor',
    activePersonaId: 'persona_anchor',
    accountState: 'active',
    installId: 'anchor-install',
  );
}

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_paging_anchor_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  Future<void> pumpConversationPageFirstFrame(
    WidgetTester tester,
    ChatMessageRepository repo,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(message: repo),
          chatMessageCommandWriterProvider.overrideWithValue(
            InMemoryChatMessageCommandWriter(),
          ),
          chatMessageTimelineCacheProvider.overrideWithValue(
            const EmptyChatMessageTimelineCache(),
          ),
          contentConfigRepositoryProvider.overrideWithValue(
            InMemoryContentConfigRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            mutualRelationshipCapabilityRepository(),
          ),
          realtimeConnectionManagerProvider.overrideWith(
            _NoopRealtimeConnectionNotifier.new,
          ),
          voiceQueuedSenderProvider.overrideWithValue(
            (_, _) async => VoiceSendStatus.completed,
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => const ActivePersonaContextViewData(
              personaId: 'persona_anchor',
              ownerUserId: 'user_anchor',
              subjectType: 'persona',
              displayName: '分页锚点用户',
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
          home: ChatConversationPage(
            conversationId: _conversationId,
            onBack: () {},
          ),
        ),
      ),
    );
    await tester.pump();
  }

  Future<void> pumpConversationPage(
    WidgetTester tester,
    ChatMessageRepository repo,
  ) async {
    await pumpConversationPageFirstFrame(tester, repo);
    await tester.pump(const Duration(milliseconds: 400));
  }

  testWidgets('加载更早历史后原可见消息的屏上位置不跳变', (tester) async {
    final repo = _TwoPageMessageRepository();
    await pumpConversationPage(tester, repo);

    // 首屏加载 seq 21..70（满一页，hasMore 保持 true）。
    expect(find.text('锚点消息 70'), findsOneWidget);
    expect(find.text('锚点消息 1'), findsNothing);

    // 滚动到接近顶部（触发历史加载的阈值内），锚定当前最早可见消息。
    final scrollable = find
        .descendant(
          of: find.byType(ChatConversationPage),
          matching: find.byType(Scrollable),
        )
        .first;
    // 一次性滚到列表顶部（进入历史加载阈值触发 loadOlderMessages），
    // 等回弹动画、历史插入与 offset 补偿全部落地。
    await tester.drag(scrollable, const Offset(0, 6000));
    await tester.pumpAndSettle();

    expect(repo.listCallCount, greaterThanOrEqualTo(2), reason: '滚动到顶必须触发历史分页');
    expect(
      find.text('锚点消息 20', skipOffstage: false),
      findsWidgets,
      reason: '更早历史必须已插入列表',
    );

    // 可视位置保持（GWT-002 前半句）：插入 20 条更早消息（合计高度远超
    // 一屏）后，滚到顶时的锚点消息经 offset 补偿必须仍停留在视口内；
    // 若无补偿，它会被新插入内容推出视口约 900px 以上。
    final viewportHeight = tester
        .getSize(find.byType(ChatConversationPage))
        .height;
    final anchorTop = tester.getTopLeft(
      find.text('锚点消息 21', skipOffstage: false),
    );
    expect(
      anchorTop.dy,
      inInclusiveRange(0, viewportHeight),
      reason: '加载历史后原可视锚点消息必须仍在视口内（位置被补偿保持）',
    );
  });

  // spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/spec.md#open-002
  testWidgets('消息初始加载呈现共享骨架屏', (tester) async {
    final repo = _SlowFirstPageRepository();
    await pumpConversationPageFirstFrame(tester, repo);

    expect(
      find.byType(AppSkeletonListRows),
      findsOneWidget,
      reason: '消息初始加载必须使用共享 AppSkeletonListRows 骨架',
    );
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byType(AppSkeletonListRows), findsNothing);
  });

  // spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/rich-media-message/spec.md#gwt-001
  testWidgets('图片消息点击进入全屏大图查看', (tester) async {
    await pumpConversationPage(tester, _ImageMessageRepository());

    final imageBubble = find.byKey(
      const ValueKey<String>('chat_image_open_image_msg_1'),
    );
    expect(imageBubble, findsOneWidget, reason: '图片气泡必须绑定大图查看动作');
    await tester.tap(imageBubble);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('chat_image_viewer_surface')),
      findsOneWidget,
      reason: '点击图片必须进入全屏大图查看',
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('chat_image_viewer_close')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('chat_image_viewer_surface')),
      findsNothing,
      reason: '关闭后回到会话页',
    );
  });

  // spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/list-detail-message-delivery/spec.md
  testWidgets('文件消息交付 URL 缺失时点击给出结构化不可用提示', (tester) async {
    await pumpConversationPage(tester, _FileMessageRepository());

    final fileBubble = find.byKey(
      const ValueKey<String>('chat_file_open_file_msg_1'),
    );
    expect(fileBubble, findsOneWidget, reason: '文件气泡必须绑定打开动作');
    await tester.tap(fileBubble);
    await tester.pump();

    expect(
      find.text(ChatText.chatMediaUnavailable),
      findsOneWidget,
      reason: '交付 URL 缺失时必须给出媒体不可用提示',
    );
    // 消化 toast 自动消失 timer，避免 pending timer 断言失败。
    await tester.pump(const Duration(seconds: 4));
  });
}
