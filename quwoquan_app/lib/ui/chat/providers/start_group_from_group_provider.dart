import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';

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

/// 选群列表头像与 inbox 同源：只解析云侧预合成 [avatarUrl]，不做端侧合成或 strip。
String resolveSelectableGroupAvatar(String raw) {
  if (raw.trim().isEmpty) {
    return '';
  }
  return resolveAvatarImageUrl(raw);
}

/// 图四数据源：按服务端 `source` 分页前过滤消费
/// `ListSelectableGroupConversations`，避免端侧过滤造成来源漏项。
///
/// 云侧已过滤 `friendMemberCount == 0` 的群并完成互关计数，Mock 与 Remote
/// 行为同源；端侧只做展示态映射（头像占位 + 标题兜底）。
final _startGroupSourceProvider = FutureProvider.autoDispose
    .family<List<GroupWithFriendCount>, StartGroupSource>((ref, source) async {
      final repo = ref.watch(chatGroupSelectionRepositoryProvider);
      final rows = await repo.listSelectableGroupConversations(
        source: switch (source) {
          StartGroupSource.group => ChatSelectableGroupSource.group,
          StartGroupSource.circle => ChatSelectableGroupSource.circle,
        },
        limit: 200,
      );
      return rows
          .where((row) => row.conversationId.isNotEmpty)
          .map(
            (row) => GroupWithFriendCount(
              conversationId: row.conversationId,
              title: row.title.isNotEmpty ? row.title : row.conversationId,
              avatarUrl: resolveSelectableGroupAvatar(row.avatarUrl),
              circleId: row.circleId,
              friendCount: row.friendMemberCount,
            ),
          )
          .toList(growable: false);
    });

final startGroupFromGroupProvider = _startGroupSourceProvider(
  StartGroupSource.group,
);

final startGroupFromCircleProvider = _startGroupSourceProvider(
  StartGroupSource.circle,
);

/// 图五：取出某个群内与当前用户 mutual 的联系人，映射为可选成员。
///
/// 消费云侧 `ListSelectableGroupContactMembers`；再排除当前 wizard 已锁定
/// 的成员（已在群内 / addMember 模式下已在目标群）。
Future<List<StartGroupPickableMember>> loadGroupContactMembers(
  ChatGroupSelectionRepository repo,
  GroupWithFriendCount group,
  Set<String> lockedMemberIds,
) async {
  final contacts = await repo.listSelectableGroupContactMembers(
    conversationId: group.conversationId,
    limit: 500,
  );
  final members = <StartGroupPickableMember>[];
  final seen = <String>{};
  for (final contact in contacts) {
    final userId = contact.userId.trim();
    if (userId.isEmpty ||
        lockedMemberIds.contains(userId) ||
        !seen.add(userId)) {
      continue;
    }
    members.add(
      StartGroupPickableMember(
        userId: userId,
        displayName: contact.displayName.isNotEmpty
            ? contact.displayName
            : userId,
        avatarUrl: resolveAvatarImageUrl(contact.avatarUrl),
      ),
    );
  }
  members.sort((a, b) => a.displayName.compareTo(b.displayName));
  return members;
}
