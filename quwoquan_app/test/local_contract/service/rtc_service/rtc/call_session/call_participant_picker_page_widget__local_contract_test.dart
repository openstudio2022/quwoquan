// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-001
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-001.t3
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_participant_picker_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/chat_service/chat/chat_inbox_view/chat_inbox_view_fixture_builder.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

final ChatInboxViewData _inbox002 = chatInboxFixture(
  id: 'conv_002',
  type: 'group',
  title: '当前群聊',
  avatarUrl: '',
  lastMessagePreview: '',
  lastMessageType: MessageType.text,
  lastSeq: 0,
  unreadCount: 0,
  mentionUnreadCount: 0,
  muted: false,
  pinned: false,
  circleId: '',
);
final ChatInboxViewData _inbox003 = chatInboxFixture(
  id: 'conv_003',
  type: 'group',
  title: '摄影群',
  avatarUrl: '',
  lastMessagePreview: '',
  lastMessageType: MessageType.text,
  lastSeq: 0,
  unreadCount: 0,
  mentionUnreadCount: 0,
  muted: false,
  pinned: false,
  circleId: '',
);

class _PickerInboxRepository implements ChatInboxRepository {
  @override
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = 20,
  }) async {
    return <ChatInboxViewData>[_inbox002, _inbox003];
  }
}

class _PickerConversationRepository implements ChatConversationRepository {
  _PickerConversationRepository(this._delegate);

  final ChatConversationRepository _delegate;

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => _delegate.listMessageHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return <ChatInboxViewData>[_inbox002, _inbox003];
  }

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) => _delegate.createConversation(
    type: type,
    title: title,
    maxGroupSize: maxGroupSize,
    initialMemberIds: initialMemberIds,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<ConversationViewData> getConversation(String conversationId) =>
      _delegate.getConversation(conversationId);

  @override
  Future<void> updateConversationTitle(String conversationId, String title) =>
      _delegate.updateConversationTitle(conversationId, title);

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) => _delegate.updateConversationSettings(
    conversationId: conversationId,
    muted: muted,
    pinned: pinned,
  );

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() =>
      _delegate.getConversationTimestamps();

  @override
  Future<List<ConversationViewData>> batchGetConversations(List<String> ids) =>
      _delegate.batchGetConversations(ids);
}

class _PickerMemberRepository implements ChatMemberRepository {
  _PickerMemberRepository(this._delegate);

  final ChatMemberRepository _delegate;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    if (conversationId == 'conv_initial_large') {
      return List<ConversationMemberListRow>.generate(
        35,
        (index) => ConversationMemberListRow(
          userId: 'initial-user-$index',
          userHandle: 'initial-user-$index',
          displayName: '初始成员 $index',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
      );
    }
    if (conversationId == 'conv_002') {
      return [
        ConversationMemberListRow(
          userId: 'user_002',
          userHandle: 'user_002',
          displayName: '当前群成员 A',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
        ConversationMemberListRow(
          userId: 'user_003',
          userHandle: 'user_003',
          displayName: '当前群成员 B',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
        ConversationMemberListRow(
          userId: 'user_008',
          userHandle: 'user_008',
          displayName: '当前群成员 C',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
      ];
    }
    if (conversationId == 'conv_003') {
      return [
        ConversationMemberListRow(
          userId: 'user_004',
          userHandle: 'user_004',
          displayName: '跨群成员 A',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
        ConversationMemberListRow(
          userId: 'user_005',
          userHandle: 'user_005',
          displayName: '跨群成员 B',
          avatarUrl: '',
          role: 'member',
          memberType: 'user',
          joinedAt: null,
          isCurrentUser: false,
        ),
      ];
    }
    return <ConversationMemberListRow>[];
  }

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    required int limit,
  }) => _delegate.searchMembers(
    conversationId: conversationId,
    query: query,
    limit: limit,
  );

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) => _delegate.addMembers(conversationId: conversationId, userIds: userIds);

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) => _delegate.removeMember(conversationId: conversationId, userId: userId);

  @override
  Future<void> leaveConversation(String conversationId) =>
      _delegate.leaveConversation(conversationId);

  @override
  Future<List<String>> listMemberUserIds(String conversationId) =>
      _delegate.listMemberUserIds(conversationId);

  @override
  Future<void> inviteAssistant({required String conversationId}) =>
      _delegate.inviteAssistant(conversationId: conversationId);

  @override
  Future<void> removeAssistant({required String conversationId}) =>
      _delegate.removeAssistant(conversationId: conversationId);
}

class _PickerContactRepository implements ChatContactRepository {
  _PickerContactRepository(this._delegate);

  final ChatContactRepository _delegate;

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return CursorPage<ChatContactRowViewData>(
      items: [
        ChatContactRowViewData(
          userId: 'user_006',
          userHandle: 'user_006',
          displayName: '联系人小雨',
          avatarUrl: '',
          bio: '',
          metFrom: '',
          lastInteraction: '',
          relationState: 'mutual',
          isStarred: false,
        ),
        ChatContactRowViewData(
          userId: 'user_007',
          userHandle: 'user_007',
          displayName: '联系人阿青',
          avatarUrl: '',
          bio: '',
          metFrom: '',
          lastInteraction: '',
          relationState: 'mutual',
          isStarred: false,
        ),
      ],
    );
  }

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => _delegate.listContactHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  }) => _delegate.listGroupCandidates(
    conversationId: conversationId,
    limit: limit,
  );
}

class _FailingPickerInboxRepository implements ChatInboxRepository {
  @override
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('inbox unavailable');
  }
}

class _FailingPickerContactRepository implements ChatContactRepository {
  _FailingPickerContactRepository(this._delegate);

  final ChatContactRepository _delegate;

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('contacts unavailable');
  }

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => _delegate.listContactHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  }) => _delegate.listGroupCandidates(
    conversationId: conversationId,
    limit: limit,
  );
}

class _FailingPickerMemberRepository implements ChatMemberRepository {
  _FailingPickerMemberRepository(this._delegate);

  final ChatMemberRepository _delegate;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    throw StateError('members unavailable');
  }

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    required int limit,
  }) => _delegate.searchMembers(
    conversationId: conversationId,
    query: query,
    limit: limit,
  );

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) => _delegate.addMembers(conversationId: conversationId, userIds: userIds);

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) => _delegate.removeMember(conversationId: conversationId, userId: userId);

  @override
  Future<void> leaveConversation(String conversationId) =>
      _delegate.leaveConversation(conversationId);

  @override
  Future<List<String>> listMemberUserIds(String conversationId) =>
      _delegate.listMemberUserIds(conversationId);

  @override
  Future<void> inviteAssistant({required String conversationId}) =>
      _delegate.inviteAssistant(conversationId: conversationId);

  @override
  Future<void> removeAssistant({required String conversationId}) =>
      _delegate.removeAssistant(conversationId: conversationId);
}

List<Override> _pickerOverrides({bool failing = false}) {
  final facets = ChatTestFacets();
  if (failing) {
    return chatTestRepositoryOverrides(
      facets: facets,
      inbox: _FailingPickerInboxRepository(),
      member: _FailingPickerMemberRepository(facets.member),
      contact: _FailingPickerContactRepository(facets.contact),
    );
  }
  return chatTestRepositoryOverrides(
    facets: facets,
    inbox: _PickerInboxRepository(),
    conversation: _PickerConversationRepository(facets.conversation),
    member: _PickerMemberRepository(facets.member),
    contact: _PickerContactRepository(facets.contact),
  );
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('HTTP request failed') ||
        msg.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  group('CallParticipantPickerPage — 渲染契约', () {
    testWidgets('初始通话只显示 canonical 会话成员且默认全选不超过 31 人', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides()],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.initialCall(
                conversationId: 'conv_initial_large',
                maxParticipants: 32,
                defaultSelectAll: true,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(CallText.callSourceMutualFollow), findsNothing);
      expect(find.text(CallText.callSourceOtherGroups), findsNothing);
      expect(
        find.text(UITextConstants.callParticipantLimit(31)),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.callConfirmSelected(31)),
        findsOneWidget,
      );
    });

    testWidgets('群聊场景显示来源切换：当前会话 / 互相关注 / 其他群', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides()],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.existingCallInvite(
                callId: 'call-picker-contract',
                currentParticipantCount: 1,
                conversationId: 'conv_002',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('当前会话'), findsOneWidget);
      expect(find.text(CallText.callSourceMutualFollow), findsOneWidget);
      expect(find.text('其他群'), findsOneWidget);
    });

    testWidgets('切换到其他群后显示可切换的群来源与对应成员', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides()],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.existingCallInvite(
                callId: 'call-picker-contract',
                currentParticipantCount: 1,
                conversationId: 'conv_002',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('其他群'));
      await tester.pumpAndSettle();

      expect(find.text('摄影群'), findsOneWidget);
      await tester.tap(find.text('摄影群'));
      await tester.pumpAndSettle();
      expect(find.text('跨群成员 A'), findsOneWidget);
    });
  });

  group('CallParticipantPickerPage — 交互契约', () {
    testWidgets('已有通话 30/32 人时最多再选择 2 人', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides()],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.existingCallInvite(
                callId: 'call-nearly-full',
                currentParticipantCount: 30,
                maxParticipants: 32,
                conversationId: 'conv_002',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.callParticipantLimit(2)),
        findsOneWidget,
      );
      await tester.tap(find.text('当前群成员 A'));
      await tester.pump();
      await tester.tap(find.text('当前群成员 B'));
      await tester.pump();
      await tester.tap(find.text('当前群成员 C'));
      await tester.pump();

      expect(find.text(UITextConstants.callConfirmSelected(2)), findsOneWidget);
    });

    testWidgets('切换到互相关注来源后展示联系人成员', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides()],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.existingCallInvite(
                callId: 'call-picker-contract',
                currentParticipantCount: 1,
                conversationId: 'conv_002',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(CallText.callSourceMutualFollow));
      await tester.pumpAndSettle();

      expect(find.text('联系人小雨'), findsOneWidget);
      expect(find.text('联系人阿青'), findsOneWidget);
    });
  });

  group('CallParticipantPickerPage — 错误态渲染', () {
    testWidgets('群来源为空时页面仍安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides()],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.existingCallInvite(
                callId: 'call-picker-contract',
                currentParticipantCount: 1,
                conversationId: 'conv_missing',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('邀请参与者'), findsOneWidget);
    });

    testWidgets('主数据加载失败时展示统一页态', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [..._pickerOverrides(failing: true)],
          child: const CupertinoApp(
            home: CallParticipantPickerPage(
              routeExtra: CallParticipantPickerRouteExtra.existingCallInvite(
                callId: 'call-picker-contract',
                currentParticipantCount: 1,
                conversationId: 'conv_002',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(AppPageErrorState), findsOneWidget);
      expect(find.text(SearchText.reload), findsOneWidget);
    });
  });
}
