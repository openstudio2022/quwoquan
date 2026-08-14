/// 1v1 会话头部交集摘要契约。
///
/// 覆盖：由打招呼升级而来的 1v1 会话头部保留云侧破冰依据（端只透传
/// primaryText 不拼句）；群会话头部不展示交集；无成立交集且无破冰依据时
/// 不占位。
///
/// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-002
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

const _icebreakSentence = '你们都想去黄龙五彩池';

ConversationViewData _conversation({
  required String id,
  required String type,
  GreetingIntersectionSnapshot? snapshot,
  List<ContactIntersectionFact> intersectionFacts =
      const <ContactIntersectionFact>[],
}) => ConversationViewData(
  id: id,
  type: type,
  title: type == 'group' ? '产品共创群' : '小满',
  creatorId: 'user_peer',
  originType: snapshot == null ? 'direct_init' : 'greeting_reply',
  originIntersectionSnapshot: snapshot,
  intersectionFacts: intersectionFacts,
  maxSeq: 0,
  memberCount: type == 'group' ? 5 : 2,
  maxGroupSize: 200,
  receiptEnabled: false,
  lastMessageType: MessageType.text,
  messageCount: 0,
  status: 'active',
  createdAt: DateTime.utc(2026, 8, 1),
  updatedAt: DateTime.utc(2026, 8, 1),
);

final _snapshot = GreetingIntersectionSnapshot(
  intersectionId: 'ix_greeting_1',
  evidenceId: 'ev_greeting_1',
  sourceRef: 'greeting_request/gr_1',
  objectTypeRef: 'entity',
  objectId: 'entity_huanglong',
  primaryText: _icebreakSentence,
  resolvedAt: DateTime.utc(2026, 8, 1),
);

final class _NoopMessageWriter implements ChatMessageCommandWriter {
  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async => ChatSendMessageResult(
    messageId: 'message_${command.clientMsgId}',
    seq: 1,
    timestamp: DateTime.utc(2026, 8, 1),
  );
}

final class _HeaderConversationRepository extends Fake
    implements ChatConversationRepository {
  _HeaderConversationRepository(this.byId);

  final Map<String, ConversationViewData> byId;

  @override
  Future<ConversationViewData> getConversation(String conversationId) async =>
      byId[conversationId]!;
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
    ownerId: 'user_chat_header',
    activePersonaId: 'persona_chat_header',
  );
}

Widget _scopedPage({
  required ChatConversationRepository conversation,
  required String conversationId,
}) {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      ...chatTestRepositoryOverrides(conversation: conversation),
      chatMessageCommandWriterProvider.overrideWithValue(_NoopMessageWriter()),
      chatMessageTimelineCacheProvider.overrideWithValue(
        const EmptyChatMessageTimelineCache(),
      ),
      contentConfigRepositoryProvider.overrideWithValue(
        InMemoryContentConfigRepository(),
      ),
      realtimeConnectionManagerProvider.overrideWith(
        _NoopRealtimeConnectionNotifier.new,
      ),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData(
          personaId: 'persona_chat_header',
          ownerUserId: 'user_chat_header',
          subjectType: 'persona',
          displayName: '会话头验收用户',
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
      home: ChatConversationPage(conversationId: conversationId, onBack: () {}),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_header_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  // spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-002.t1
  // spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-002.t2
  testWidgets('GWT-002 打招呼升级的 1v1 会话头部保留云侧破冰依据原句', (tester) async {
    final repo = _HeaderConversationRepository({
      'conv_direct_greeting': _conversation(
        id: 'conv_direct_greeting',
        type: 'direct',
        snapshot: _snapshot,
      ),
    });
    await tester.pumpWidget(
      _scopedPage(conversation: repo, conversationId: 'conv_direct_greeting'),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('小满'), findsOneWidget);
    // 端只透传云侧 primaryText，不拼接、不改写。
    expect(find.text(_icebreakSentence), findsOneWidget);
  });

  testWidgets('群会话头部不展示交集，即使数据面存在快照', (tester) async {
    final repo = _HeaderConversationRepository({
      'conv_group_defensive': _conversation(
        id: 'conv_group_defensive',
        type: 'group',
        snapshot: _snapshot,
      ),
    });
    await tester.pumpWidget(
      _scopedPage(conversation: repo, conversationId: 'conv_group_defensive'),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('产品共创群'), findsOneWidget);
    expect(find.text(_icebreakSentence), findsNothing);
  });

  // spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-001.t1
  // spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/conversation-intersection-header/spec.md#gwt-001.t2
  testWidgets('GWT-001 非破冰 1v1 会话头展示云侧常驻交集摘要原文', (tester) async {
    final repo = _HeaderConversationRepository({
      'conv_direct_persistent': _conversation(
        id: 'conv_direct_persistent',
        type: 'direct',
        intersectionFacts: <ContactIntersectionFact>[
          ContactIntersectionFact(
            intersectionId: 'ix_persist_1',
            kind: 'coWishlistedEntity',
            dimension: 'entity',
            intersectionClass: 'fact',
            primaryText: '你们都想去五彩池观星营地',
          ),
          ContactIntersectionFact(
            intersectionId: 'ix_persist_2',
            kind: 'coExperiencedGathering',
            dimension: 'gathering',
            intersectionClass: 'fact',
            primaryText: '一起参加过周末观星聚会',
          ),
        ],
      ),
    });
    await tester.pumpWidget(
      _scopedPage(conversation: repo, conversationId: 'conv_direct_persistent'),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('小满'), findsOneWidget);
    // 端只透传云侧聚合的首条 primaryText，不拼句、不改写。
    expect(find.text('你们都想去五彩池观星营地'), findsOneWidget);
  });

  testWidgets('破冰快照优先于常驻交集摘要', (tester) async {
    final repo = _HeaderConversationRepository({
      'conv_direct_both': _conversation(
        id: 'conv_direct_both',
        type: 'direct',
        snapshot: _snapshot,
        intersectionFacts: <ContactIntersectionFact>[
          ContactIntersectionFact(
            intersectionId: 'ix_persist_x',
            kind: 'coWishlistedEntity',
            dimension: 'entity',
            intersectionClass: 'fact',
            primaryText: '常驻摘要不该抢占',
          ),
        ],
      ),
    });
    await tester.pumpWidget(
      _scopedPage(conversation: repo, conversationId: 'conv_direct_both'),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text(_icebreakSentence), findsOneWidget);
    expect(find.text('常驻摘要不该抢占'), findsNothing);
  });

  testWidgets('无成立交集且无破冰依据时头部不占位', (tester) async {
    final repo = _HeaderConversationRepository({
      'conv_direct_plain': _conversation(
        id: 'conv_direct_plain',
        type: 'direct',
      ),
    });
    await tester.pumpWidget(
      _scopedPage(conversation: repo, conversationId: 'conv_direct_plain'),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('小满'), findsOneWidget);
    expect(find.text(_icebreakSentence), findsNothing);
  });
}
