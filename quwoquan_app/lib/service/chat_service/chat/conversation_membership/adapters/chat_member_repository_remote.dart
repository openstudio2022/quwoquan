// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

final class RemoteChatMemberRepository implements ChatMemberRepository {
  RemoteChatMemberRepository({
    required ChatConversationMembershipQuery membershipQuery,
    required ChatConversationMembershipCommandWriter membershipCommandWriter,
    ChatConversationMembershipQuery? memberSearchQuery,
    String Function()? idempotencyKeyFactory,
  }) : _membershipQuery = membershipQuery,
       _memberSearchQuery = memberSearchQuery ?? membershipQuery,
       _membershipCommandWriter = membershipCommandWriter,
       _idempotencyKeyFactory = idempotencyKeyFactory ?? const Uuid().v4;

  final ChatConversationMembershipQuery _membershipQuery;
  final ChatConversationMembershipQuery _memberSearchQuery;
  final ChatConversationMembershipCommandWriter _membershipCommandWriter;
  final String Function() _idempotencyKeyFactory;
  static const int _maximumMemberPages = 20;

  String _idempotencyKey() {
    final value = _idempotencyKeyFactory().trim();
    if (value.isEmpty) {
      throw ArgumentError.value(value, 'idempotencyKey', 'must not be blank');
    }
    return value;
  }

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = ChatListConversationMembersQuery.defaultLimit,
    String? role,
    String? sort,
  }) async {
    return _listEveryMemberPage(
      query: _membershipQuery,
      conversationId: conversationId,
      cursor: cursor,
      limit: limit,
      role: role,
      sort: sort ?? 'joined_asc',
    );
  }

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    int limit = ChatListConversationMembersQuery.maximumLimit,
  }) async {
    return _listEveryMemberPage(
      query: _memberSearchQuery,
      conversationId: conversationId,
      limit: limit,
      searchQuery: query.trim(),
      sort: 'display_name_asc',
    );
  }

  Future<List<ConversationMemberListRow>> _listEveryMemberPage({
    required ChatConversationMembershipQuery query,
    required String conversationId,
    String? cursor,
    required int limit,
    String? role,
    required String sort,
    String? searchQuery,
  }) async {
    var nextCursor = cursor?.trim() ?? '';
    final seenCursors = <String>{if (nextCursor.isNotEmpty) nextCursor};
    final membersByID = <String, ConversationMemberListRow>{};
    final pageLimit = limit.clamp(
      1,
      ChatListConversationMembersQuery.maximumLimit,
    );
    for (var pageIndex = 0; pageIndex < _maximumMemberPages; pageIndex++) {
      final page = await query.listMembers(
        ChatListConversationMembersQuery(
          conversationId: conversationId,
          cursor: nextCursor.isEmpty ? null : nextCursor,
          limit: pageLimit,
          role: role,
          sort: sort,
          query: searchQuery?.isEmpty == true ? null : searchQuery,
        ),
      );
      for (final member in page.items) {
        final memberID = member.userId.trim();
        if (memberID.isEmpty || membersByID.containsKey(memberID)) {
          throw const FormatException(
            'ListMembers returned an empty or duplicate member identity',
          );
        }
        membersByID[memberID] = member;
      }
      final candidate = page.nextCursor?.trim() ?? '';
      if (candidate.isEmpty) {
        return List<ConversationMemberListRow>.unmodifiable(membersByID.values);
      }
      if (!seenCursors.add(candidate)) {
        throw const FormatException(
          'ListMembers returned a cyclic cursor progression',
        );
      }
      nextCursor = candidate;
    }
    throw const FormatException(
      'ListMembers exceeded the bounded pagination window',
    );
  }

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async {
    await _membershipCommandWriter.addMembers(
      ChatAddConversationMembersCommand(
        conversationId: conversationId,
        userIds: userIds,
      ),
      idempotencyKey: _idempotencyKey(),
    );
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    await _membershipCommandWriter.removeMember(
      ChatRemoveConversationMemberCommand(
        conversationId: conversationId,
        userId: userId,
      ),
      idempotencyKey: _idempotencyKey(),
    );
  }

  @override
  Future<void> leaveConversation(String conversationId) async {
    await _membershipCommandWriter.leaveConversation(
      ChatLeaveConversationCommand(conversationId: conversationId),
      idempotencyKey: _idempotencyKey(),
    );
  }

  @override
  Future<List<String>> listMemberUserIds(String conversationId) async {
    final members = await listMembers(
      conversationId: conversationId,
      limit: 500,
    );
    return members
        .map((member) => member.userId)
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
  }

  @override
  Future<void> inviteAssistant({required String conversationId}) async {
    await _membershipCommandWriter.inviteAssistant(
      ChatInviteConversationAssistantCommand(conversationId: conversationId),
      idempotencyKey: _idempotencyKey(),
    );
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    await _membershipCommandWriter.removeAssistant(
      ChatRemoveConversationAssistantCommand(conversationId: conversationId),
      idempotencyKey: _idempotencyKey(),
    );
  }
}
