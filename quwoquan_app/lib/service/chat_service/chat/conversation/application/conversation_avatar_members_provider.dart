import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'dart:async';
import 'dart:collection';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_avatar_prefetch.dart';

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
    extends Notifier<Map<String, List<ConversationMemberListRow>>>
    implements ConversationAvatarPrefetchCapability {
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

  @override
  Future<void> prefetchInbox(
    List<ConversationAvatarPrefetchItem> items, {
    int offset = 0,
    int limit = kConversationAvatarInitialPrefetchLimit,
  }) async {
    final ids = items
        .where(
          (item) => conversationAvatarNeedsMembers(
            conversationId: item.conversationId,
            conversationType: item.conversationType,
            avatarUrl: resolveAvatarImageUrl(item.avatarUrl),
            groupAvatarVersion: item.groupAvatarVersion,
          ),
        )
        .skip(offset)
        .take(limit)
        .map((item) => item.conversationId.trim())
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
    if (ids.isEmpty) {
      return;
    }
    // `_loadMembers` 已经把失败收敛成「留痕 + 空成员」，`ensureLoaded` 不会抛，
    // 所以这里不再吞一次：多余的 catchError 只会把将来真出现的异常也一起藏掉。
    await Future.wait<void>(
      ids.map((id) => ensureLoaded(id).then((_) {})),
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
        sort: MemberListSort.joinedAsc,
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
    } catch (error, stackTrace) {
      // 取不到成员时群头像会画成空的，这跟「这个会话真的没有别人」在界面上完全
      // 一样，用户和运维都看不出发生了故障，所以降级本身必须可观测。
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'chat.conversation_avatar.load_members',
              error: error,
              stackTrace: stackTrace,
            ),
      );
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
