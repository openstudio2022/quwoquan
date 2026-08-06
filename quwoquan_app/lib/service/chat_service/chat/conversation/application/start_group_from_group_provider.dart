import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/start_group_pickable_member.dart';

enum StartGroupSource { group, circle }

/// 「从群聊中选择联系人」二级流程的群聊条目（图四）。
///
/// `friendCount` 为该群成员中与当前用户 mutual 联系人的数量，由云侧
/// `ListSelectableGroupConversations` 计算下发（端侧不再逐群拉成员求交集）。
class GroupWithFriendCount {
  const GroupWithFriendCount({
    required this.conversationId,
    required this.title,
    required this.avatarUrl,
    required this.circleId,
    required this.friendCount,
  });

  final String conversationId;
  final String title;

  /// 与 inbox 同源：云侧预合成群头像 [avatarUrl] 经 [resolveAvatarImageUrl] 解析。
  final String avatarUrl;
  final String circleId;
  final int friendCount;
}

class StartGroupSourcePage {
  const StartGroupSourcePage({required this.groups, this.nextCursor});

  final List<GroupWithFriendCount> groups;
  final String? nextCursor;
}

class StartGroupContactMemberPage {
  const StartGroupContactMemberPage({required this.members, this.nextCursor});

  final List<StartGroupPickableMember> members;
  final String? nextCursor;
}

class StartGroupSourcePageRequest {
  const StartGroupSourcePageRequest({
    required this.source,
    this.query,
    this.cursor,
  });

  final StartGroupSource source;
  final String? query;
  final String? cursor;

  @override
  bool operator ==(Object other) {
    return other is StartGroupSourcePageRequest &&
        other.source == source &&
        other.query == query &&
        other.cursor == cursor;
  }

  @override
  int get hashCode => Object.hash(source, query, cursor);
}

/// 选群列表头像与 inbox 同源：只解析云侧预合成 [avatarUrl]，不做端侧合成或 strip。
String resolveSelectableGroupAvatar(String raw, {String? avatarCdnBaseUrl}) {
  if (raw.trim().isEmpty) {
    return '';
  }
  return resolveAvatarImageUrl(raw, avatarCdnBaseUrl: avatarCdnBaseUrl);
}

/// 图四数据源：按服务端 `source` 分页前过滤消费
/// `ListSelectableGroupConversations`，避免端侧过滤造成来源漏项。
///
/// 云侧已过滤 `friendMemberCount == 0` 的群并完成互关计数，Mock 与 Remote
/// 行为同源；端侧只做展示态映射（头像占位 + 标题兜底）。
final startGroupSourcePageProvider = FutureProvider.autoDispose
    .family<StartGroupSourcePage, StartGroupSourcePageRequest>((ref, request) {
      final repo = ref.watch(chatGroupSelectionRepositoryProvider);
      return loadStartGroupSourcePage(
        repo,
        source: request.source,
        query: request.query,
        cursor: request.cursor,
      );
    });

Future<StartGroupSourcePage> loadStartGroupSourcePage(
  ChatGroupSelectionRepository repo, {
  required StartGroupSource source,
  String? query,
  String? cursor,
  String? avatarCdnBaseUrl,
}) async {
  final page = await repo.listSelectableGroupConversations(
    source: switch (source) {
      StartGroupSource.group => ChatSelectableGroupSource.group,
      StartGroupSource.circle => ChatSelectableGroupSource.circle,
    },
    query: query,
    cursor: cursor,
  );
  final groups = <GroupWithFriendCount>[];
  final seenConversationIds = <String>{};
  for (final row in page.items) {
    final conversationId = row.conversationId.trim();
    if (conversationId.isEmpty || !seenConversationIds.add(conversationId)) {
      continue;
    }
    groups.add(
      GroupWithFriendCount(
        conversationId: conversationId,
        title: row.title.isNotEmpty ? row.title : conversationId,
        avatarUrl: resolveSelectableGroupAvatar(
          row.avatarUrl,
          avatarCdnBaseUrl: avatarCdnBaseUrl,
        ),
        circleId: row.circleId,
        friendCount: row.friendMemberCount,
      ),
    );
  }
  return StartGroupSourcePage(
    groups: groups,
    nextCursor: _normalizedCursor(page.nextCursor),
  );
}

List<GroupWithFriendCount> mergeStartGroupSourcePages(
  List<GroupWithFriendCount> existing,
  List<GroupWithFriendCount> incoming,
) {
  final seenConversationIds = existing
      .map((group) => group.conversationId.trim())
      .where((conversationId) => conversationId.isNotEmpty)
      .toSet();
  final merged = List<GroupWithFriendCount>.from(existing);
  for (final group in incoming) {
    final conversationId = group.conversationId.trim();
    if (conversationId.isEmpty || !seenConversationIds.add(conversationId)) {
      continue;
    }
    merged.add(group);
  }
  return merged;
}

/// 图五：取出某个群内与当前用户 mutual 的联系人，映射为可选成员。
///
/// 消费云侧 `ListSelectableGroupContactMembers`；再排除当前 wizard 已锁定
/// 的成员（已在群内 / addMember 模式下已在目标群）。
Future<StartGroupContactMemberPage> loadGroupContactMemberPage(
  ChatGroupSelectionRepository repo, {
  required GroupWithFriendCount group,
  required Set<String> lockedMemberIds,
  String? query,
  String? cursor,
}) async {
  final page = await repo.listSelectableGroupContactMembers(
    conversationId: group.conversationId,
    query: query,
    cursor: cursor,
  );
  final members = <StartGroupPickableMember>[];
  final seen = <String>{};
  for (final contact in page.items) {
    final userId = contact.userId.trim();
    if (userId.isEmpty ||
        lockedMemberIds.contains(userId) ||
        !seen.add(userId)) {
      continue;
    }
    members.add(
      StartGroupPickableMember(
        userId: userId,
        userHandle: contact.userHandle,
        displayName: contact.displayName.isNotEmpty
            ? contact.displayName
            : userId,
        avatarUrl: resolveAvatarImageUrl(contact.avatarUrl),
      ),
    );
  }
  return StartGroupContactMemberPage(
    members: members,
    nextCursor: _normalizedCursor(page.nextCursor),
  );
}

List<StartGroupPickableMember> mergeStartGroupContactMemberPages(
  List<StartGroupPickableMember> existing,
  List<StartGroupPickableMember> incoming,
) {
  final seenUserIds = existing
      .map((member) => member.userId.trim())
      .where((userId) => userId.isNotEmpty)
      .toSet();
  final merged = List<StartGroupPickableMember>.from(existing);
  for (final member in incoming) {
    final userId = member.userId.trim();
    if (userId.isEmpty || !seenUserIds.add(userId)) {
      continue;
    }
    merged.add(member);
  }
  return merged;
}

String? _normalizedCursor(String? cursor) {
  final normalized = cursor?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
