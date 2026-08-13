/// 引用回复端到端契约（长按菜单 → 引用预览 → 强类型 payload → 气泡引用块）。
///
/// 覆盖：长按消息出现「回复」动作；选择后输入栏出现可取消的引用预览；
/// 发送命令携带 contracts `replyToMessageId`；带引用的消息在气泡上方渲染
/// 被引用摘要；取消预览后发送不携带引用。
///
/// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/message-interaction-polish/spec.md#gwt-003
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_bubble.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

const _conversationId = 'fixture_conv_direct';
const _peerMessage = '周六去黄龙五彩池吗';

final class _SeededMessageRepository extends Fake
    implements ChatMessageRepository {
  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async => [
    ChatMessageViewData(
      id: 'msg_peer_1',
      conversationId: conversationId,
      seq: 1,
      clientMsgId: 'client_peer_1',
      senderId: 'fixture_user_peer',
      senderName: '小满',
      senderAvatar: 'https://avatar.example.test/media/avatar/peer.png',
      type: 'text',
      content: _peerMessage,
      status: 'sent',
      timestamp: DateTime.utc(2026, 8, 1, 10),
    ),
  ];

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {}
}

final class _RecordingMessageWriter implements ChatMessageCommandWriter {
  final List<ChatSendMessageCommand> commands = <ChatSendMessageCommand>[];

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    commands.add(command);
    return ChatSendMessageResult(
      messageId: 'message_${command.clientMsgId}',
      seq: commands.length + 1,
      timestamp: DateTime.utc(2026, 8, 1, 11),
    );
  }
}

final class _MutualRelationshipCapability extends Fake
    implements RelationshipCapabilityRepository {
  @override
  Future<RelationshipCapabilityViewData> getCapability(String userId) async =>
      const RelationshipCapabilityViewData(
        viewerPersonaId: 'persona_reply_uat',
        targetPersonaId: 'fixture_user_peer',
        relationState: 'mutual',
        canFollow: false,
        canUnfollow: true,
        canFollowBack: false,
        canGreet: false,
        canCreateDirectConversation: true,
        canSendMessage: true,
        canOpenConversation: true,
        hasPendingGreeting: false,
        hasFormalConversation: true,
        canStartVoiceCall: true,
        canStartVideoCall: true,
        isBlocked: false,
        isBlockedBy: false,
      );
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

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_reply_uat',
    activePersonaId: 'persona_reply_uat',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
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

Widget _scopedPage(_RecordingMessageWriter writer) {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      ...chatTestRepositoryOverrides(message: _SeededMessageRepository()),
      chatMessageCommandWriterProvider.overrideWithValue(writer),
      chatMessageTimelineCacheProvider.overrideWithValue(
        const EmptyChatMessageTimelineCache(),
      ),
      contentConfigRepositoryProvider.overrideWithValue(
        InMemoryContentConfigRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _MutualRelationshipCapability(),
      ),
      realtimeConnectionManagerProvider.overrideWith(
        _NoopRealtimeConnectionNotifier.new,
      ),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData(
          personaId: 'persona_reply_uat',
          ownerUserId: 'user_reply_uat',
          subjectType: 'persona',
          displayName: '引用回复验收用户',
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
          conversationId: _conversationId,
          onBack: () {},
        ),
      ),
    ),
  );
}

void _openActionMenu(WidgetTester tester) {
  final bubble = tester.widget<ChatMessageBubble>(
    find.byType(ChatMessageBubble).first,
  );
  bubble.onLongPressStart(
    LongPressStartDetails(
      globalPosition: tester.getCenter(find.text(_peerMessage)),
    ),
  );
}

Future<void> _pumpLoaded(WidgetTester tester, Widget page) async {
  await tester.pumpWidget(page);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 350));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_reply_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('长按回复后发送命令携带 replyToMessageId 且气泡渲染引用块', (tester) async {
    final writer = _RecordingMessageWriter();
    await _pumpLoaded(tester, _scopedPage(writer));
    expect(find.text(_peerMessage), findsOneWidget);

    // 长按手势在该气泡上的触发已有组件级先例覆盖
    //（chat_message_bubble_widget__local_contract_test.dart）；此处沿用
    // 既有模式直接调用回调，聚焦回复链路契约。
    _openActionMenu(tester);
    await tester.pump();
    expect(find.text(ChatText.messageActionReply), findsOneWidget);

    await tester.tap(find.text(ChatText.messageActionReply));
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('chat-reply-composer-preview')),
      findsOneWidget,
      reason: '选择回复后输入栏上方必须出现引用预览',
    );

    await tester.enterText(
      find.byKey(TestKeys.chatInputTextField),
      '好，周六出发',
    );
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.chatInputSendButton));
    for (var i = 0; i < 6; i += 1) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(writer.commands, hasLength(1));
    expect(
      writer.commands.single.replyToMessageId,
      'msg_peer_1',
      reason: '发送命令必须携带 contracts replyToMessageId',
    );
    expect(
      find.byKey(const ValueKey<String>('chat-reply-composer-preview')),
      findsNothing,
      reason: '发送后引用预览必须清除',
    );
    // 带引用的新消息在气泡上方渲染被引用摘要（发送者+原文单行）。
    expect(find.textContaining('小满: $_peerMessage'), findsWidgets);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('取消引用预览后发送不携带 replyToMessageId', (tester) async {
    final writer = _RecordingMessageWriter();
    await _pumpLoaded(tester, _scopedPage(writer));

    _openActionMenu(tester);
    await tester.pump();
    await tester.tap(find.text(ChatText.messageActionReply));
    await tester.pump();

    await tester.tap(
      find.byKey(const ValueKey<String>('chat-reply-composer-cancel')),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('chat-reply-composer-preview')),
      findsNothing,
    );

    await tester.enterText(find.byKey(TestKeys.chatInputTextField), '普通消息');
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.chatInputSendButton));
    for (var i = 0; i < 6; i += 1) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(writer.commands, hasLength(1));
    expect(writer.commands.single.replyToMessageId, isNull);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}
