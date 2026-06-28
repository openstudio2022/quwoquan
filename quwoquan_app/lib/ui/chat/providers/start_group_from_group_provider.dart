import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';

/// 「从群聊中选择联系人」二级流程的群聊条目（图四）。
///
/// `friendCount` 为该群成员中与当前用户 mutual 联系人的数量，由云侧
/// `ListSelectableGroupConversations` 计算下发（端侧不再逐群拉成员求交集）。
class GroupWithFriendCount {
  const GroupWithFriendCount({
    required this.conversationId,
    required this.title,
    required this.avatarUrl,
    required this.friendCount,
  });

  final String conversationId;
  final String title;

  /// 已做无效/归档头像占位处理（合成群头像置空，交由 UI 走稳定占位图标）。
  final String avatarUrl;
  final int friendCount;
}

/// 合成 / 归档群头像在 alpha/mock 下并无真实媒体文件，直连会 404 刷屏；
/// 一律置空，交由 `RoundedSquareAvatar` 的群占位图标兜底。
String resolveSelectableGroupAvatar(String raw) {
  final lower = raw.trim().toLowerCase();
  if (lower.isEmpty) {
    return '';
  }
  if (lower.contains('archived-avatar/conversation') ||
      lower.contains('/mock/conversation') ||
      lower.contains('s/mock/group')) {
    return '';
  }
  return resolveAvatarImageUrl(raw);
}

/// 图四数据源：消费云侧 `ListSelectableGroupConversations`。
///
/// 云侧已过滤 `friendMemberCount == 0` 的群并完成互关计数，Mock 与 Remote
/// 行为同源；端侧只做展示态映射（头像占位 + 标题兜底）。
final startGroupFromGroupProvider =
    FutureProvider.autoDispose<List<GroupWithFriendCount>>((ref) async {
      final repo = ref.watch(chatRepositoryProvider);
      final rows = await repo.listSelectableGroupConversations(limit: 200);
      return rows
          .where((row) => row.conversationId.isNotEmpty)
          .map(
            (row) => GroupWithFriendCount(
              conversationId: row.conversationId,
              title: row.title.isNotEmpty ? row.title : row.conversationId,
              avatarUrl: resolveSelectableGroupAvatar(row.avatarUrl),
              friendCount: row.friendMemberCount,
            ),
          )
          .toList(growable: false);
    });

/// 图五：取出某个群内与当前用户 mutual 的联系人，映射为可选成员。
///
/// 消费云侧 `ListSelectableGroupContactMembers`；再排除当前 wizard 已锁定
/// 的成员（已在群内 / addMember 模式下已在目标群）。
Future<List<StartGroupPickableMember>> loadGroupContactMembers(
  ChatRepository repo,
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
