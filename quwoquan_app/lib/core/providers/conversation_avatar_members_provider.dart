import 'dart:async';
import 'dart:collection';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
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
    extends Notifier<Map<String, List<ChatConversationMemberDto>>> {
  static const int _maxCachedConversations = 120;

  final Map<String, Future<List<ChatConversationMemberDto>>> _inflight =
      <String, Future<List<ChatConversationMemberDto>>>{};

  @override
  Map<String, List<ChatConversationMemberDto>> build() {
    ref.watch(chatRepositoryProvider);
    ref.watch(currentUserIdProvider);
    _inflight.clear();
    return const <String, List<ChatConversationMemberDto>>{};
  }

  Future<List<ChatConversationMemberDto>> ensureLoaded(String conversationId) {
    final id = conversationId.trim();
    if (id.isEmpty) {
      return Future.value(const <ChatConversationMemberDto>[]);
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
    List<ChatInboxDto> items, {
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

  Future<List<ChatConversationMemberDto>> _loadMembers(
    String conversationId,
  ) async {
    final repo = ref.read(chatRepositoryProvider);
    final currentUserId = ref.read(currentUserIdProvider);
    try {
      final members = await repo.listMembers(
        conversationId: conversationId,
        limit: 9,
        sort: 'joined_asc',
      );
      final normalized = List<ChatConversationMemberDto>.unmodifiable(
        members
            .map(
              (member) => member.copyWith(
                avatarUrl: resolveAvatarImageUrl(member.avatarUrl),
                isCurrentUser:
                    member.isCurrentUser || member.userId == currentUserId,
              ),
            )
            .toList(growable: false),
      );
      _store(conversationId, normalized);
      return normalized;
    } catch (_) {
      _store(conversationId, const <ChatConversationMemberDto>[]);
      return const <ChatConversationMemberDto>[];
    }
  }

  void _store(String conversationId, List<ChatConversationMemberDto> members) {
    final next = LinkedHashMap<String, List<ChatConversationMemberDto>>.from(
      state,
    );
    next.remove(conversationId);
    next[conversationId] = members;
    while (next.length > _maxCachedConversations) {
      next.remove(next.keys.first);
    }
    state = Map<String, List<ChatConversationMemberDto>>.unmodifiable(next);
  }
}

final conversationAvatarMembersProvider =
    NotifierProvider<
      ConversationAvatarMembersNotifier,
      Map<String, List<ChatConversationMemberDto>>
    >(ConversationAvatarMembersNotifier.new);
