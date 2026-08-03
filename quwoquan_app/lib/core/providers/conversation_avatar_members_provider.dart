import "package:quwoquan_app/cloud/services/chat/chat_view_data.dart";
import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'dart:async';
import 'dart:collection';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

const int kConversationAvatarInitialPrefetchLimit = 12;
const int kConversationAvatarBackgroundPrefetchLimit = 24;

bool conversationAvatarUsesAuthoritativeGroupAvatar({
  required String conversationType,
  required String avatarUrl,
  required int groupAvatarVersion,
}) {
  return conversationType.trim().toLowerCase() == 'group' &&
      avatarUrl.trim().isNotEmpty;
}

bool conversationAvatarNeedsMembers({
  required String conversationId,
  required String conversationType,
  required String avatarUrl,
  required int groupAvatarVersion,
}) {
  final normalizedId = conversationId.trim();
  if (normalizedId.isEmpty) {
    return false;
  }
  final normalizedType = conversationType.trim().toLowerCase();
  if (normalizedType == 'group') {
    return false;
  }
  return avatarUrl.trim().isEmpty;
}

class ConversationAvatarMembersNotifier
    extends Notifier<Map<String, List<ConversationMemberListRow>>> {
  static const int _maxCachedConversations = 120;

  final Map<String, Future<List<ConversationMemberListRow>>> _inflight =
      <String, Future<List<ConversationMemberListRow>>>{};

  @override
  Map<String, List<ConversationMemberListRow>> build() {
    ref.watch(chatMemberRepositoryProvider);
    ref.watch(currentUserIdProvider);
    _inflight.clear();
    return const <String, List<ConversationMemberListRow>>{};
  }

  Future<List<ConversationMemberListRow>> ensureLoaded(String conversationId) {
    final id = conversationId.trim();
    if (id.isEmpty) {
      return Future.value(const <ConversationMemberListRow>[]);
    }
    final cached = state[id];
    if (cached != null) {
      return Future.value(cached);
    }
    final pending = _inflight[id];
    if (pending != null) {
      return pending;
    }
    final future = _loadMembers(id);
    _inflight[id] = future;
    return future.whenComplete(() {
      if (identical(_inflight[id], future)) {
        _inflight.remove(id);
      }
    });
  }

  Future<void> prefetchInbox(
    List<ChatInboxViewData> items, {
    int offset = 0,
    int limit = kConversationAvatarInitialPrefetchLimit,
  }) async {
    final ids = items
        .where(
          (item) => conversationAvatarNeedsMembers(
            conversationId: item.id,
            conversationType: item.type,
            avatarUrl: resolveAvatarImageUrl(item.avatarUrl),
            groupAvatarVersion: item.groupAvatarVersion,
          ),
        )
        .skip(offset)
        .take(limit)
        .map((item) => item.id.trim())
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
    if (ids.isEmpty) {
      return;
    }
    await Future.wait<void>(
      ids.map((id) => ensureLoaded(id).then((_) {}).catchError((_, _) => null)),
      eagerError: false,
    );
  }

  Future<List<ConversationMemberListRow>> _loadMembers(
    String conversationId,
  ) async {
    final repo = ref.read(chatMemberRepositoryProvider);
    final currentUserId = ref.read(currentUserIdProvider);
    try {
      final members = await repo.listMembers(
        conversationId: conversationId,
        limit: 9,
        sort: 'joined_asc',
      );
      final normalized = List<ConversationMemberListRow>.unmodifiable(
        members
            .map(
              (member) => ConversationMemberListRow(
                userId: member.userId,
                userHandle: member.userHandle,
                displayName: member.displayName,
                avatarUrl: resolveAvatarImageUrl(member.avatarUrl),
                role: member.role,
                memberType: member.memberType,
                joinedAt: member.joinedAt,
                isCurrentUser:
                    member.isCurrentUser || member.userId == currentUserId,
              ),
            )
            .toList(growable: false),
      );
      _store(conversationId, normalized);
      return normalized;
    } catch (_) {
      _store(conversationId, const <ConversationMemberListRow>[]);
      return const <ConversationMemberListRow>[];
    }
  }

  void _store(String conversationId, List<ConversationMemberListRow> members) {
    final next = LinkedHashMap<String, List<ConversationMemberListRow>>.from(
      state,
    );
    next.remove(conversationId);
    next[conversationId] = members;
    while (next.length > _maxCachedConversations) {
      next.remove(next.keys.first);
    }
    state = Map<String, List<ConversationMemberListRow>>.unmodifiable(next);
  }
}

final conversationAvatarMembersProvider =
    NotifierProvider<
      ConversationAvatarMembersNotifier,
      Map<String, List<ConversationMemberListRow>>
    >(ConversationAvatarMembersNotifier.new);
