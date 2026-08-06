import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/conversation_avatar_members_provider.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';

/// 会话头像唯一主线：
/// - 单聊优先使用会话级 `avatarUrl`
/// - 群聊只消费云侧预合成 `avatarUrl`，禁止端侧成员九宫格 fallback
/// - 单聊缺失 `avatarUrl` 时回退对方成员头像

class ConversationAvatar extends ConsumerWidget {
  const ConversationAvatar({
    super.key,
    required this.conversationId,
    required this.conversationType,
    required this.title,
    required this.avatarUrl,
    required this.size,
    this.groupAvatarVersion = 0,
    this.backgroundColor,
    this.borderRadius,
    this.groupFallbackIcon = Icons.group,
    this.directFallbackIcon = Icons.person,
  });

  final String conversationId;
  final String conversationType;
  final String title;
  final String avatarUrl;
  final double size;
  final int groupAvatarVersion;
  final Color? backgroundColor;
  final double? borderRadius;
  final IconData groupFallbackIcon;
  final IconData directFallbackIcon;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final normalizedId = conversationId.trim();
    final normalizedType = conversationType.trim().toLowerCase();
    final resolvedAvatarUrl = avatarUrl.trim();
    final isGroup = normalizedType == 'group';
    final shouldLoadMembers =
        !isGroup ||
        conversationAvatarNeedsMembers(
          conversationId: normalizedId,
          conversationType: normalizedType,
          avatarUrl: resolvedAvatarUrl,
          groupAvatarVersion: groupAvatarVersion,
        );
    final members = shouldLoadMembers
        ? ref.watch(
            conversationAvatarMembersProvider.select(
              (state) =>
                  state[normalizedId] ?? const <ConversationMemberListRow>[],
            ),
          )
        : const <ConversationMemberListRow>[];

    if (shouldLoadMembers && members.isEmpty) {
      ref
          .read(conversationAvatarMembersProvider.notifier)
          .ensureLoaded(normalizedId);
    }

    if (isGroup) {
      return _buildSingleAvatar(
        imageUrl: resolvedAvatarUrl,
        fallbackIcon: groupFallbackIcon,
      );
    }

    final fallbackAvatarUrl = _resolveDirectAvatarUrl(members);
    return _buildSingleAvatar(
      imageUrl: fallbackAvatarUrl.isNotEmpty
          ? fallbackAvatarUrl
          : resolvedAvatarUrl,
      fallbackIcon: directFallbackIcon,
    );
  }

  Widget _buildSingleAvatar({
    required String imageUrl,
    required IconData fallbackIcon,
  }) {
    return RoundedSquareAvatar(
      size: size,
      imageUrl: imageUrl.isEmpty ? null : imageUrl,
      name: title,
      borderRadius: borderRadius,
      backgroundColor: backgroundColor,
      fallbackIcon: fallbackIcon,
    );
  }

  static String _resolveDirectAvatarUrl(
    List<ConversationMemberListRow> members,
  ) {
    for (final member in members) {
      final url = member.avatarUrl.trim();
      if (!member.isCurrentUser && url.isNotEmpty) {
        return url;
      }
    }
    for (final member in members) {
      final url = member.avatarUrl.trim();
      if (url.isNotEmpty) {
        return url;
      }
    }
    return '';
  }
}
