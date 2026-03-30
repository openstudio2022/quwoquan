import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';

enum ChatContactsRowKind { user, circle, group }

/// 联系人 Tab 一行展示（用户 / 圈子 / 群），避免页面持有 Map。
class ChatContactsRow {
  const ChatContactsRow({
    required this.kind,
    required this.id,
    required this.displayName,
    required this.avatarUrl,
    required this.subtitle,
    this.isFriend = true,
    this.isStarred = false,
    this.circleId,
    this.conversationId,
  });

  final ChatContactsRowKind kind;
  final String id;
  final String displayName;
  final String avatarUrl;
  final String subtitle;
  final bool isFriend;
  final bool isStarred;
  final String? circleId;
  final String? conversationId;

  factory ChatContactsRow.fromContactDto(ChatContactRowDto dto) {
    var sub = '';
    for (final raw in [dto.bio, dto.metFrom, dto.lastInteraction]) {
      final t = raw.trim();
      if (t.isNotEmpty) {
        sub = t;
        break;
      }
    }
    return ChatContactsRow(
      kind: ChatContactsRowKind.user,
      id: dto.userId,
      displayName: dto.displayName,
      avatarUrl: dto.avatarUrl,
      subtitle: sub,
      isFriend: dto.isFriend,
      isStarred: dto.isStarred,
    );
  }

  factory ChatContactsRow.fromContactTabCircleMap(Map<String, dynamic> m) {
    final circleId = (m['circleId'] ?? m['id'] ?? '').toString();
    return ChatContactsRow(
      kind: ChatContactsRowKind.circle,
      id: circleId,
      displayName: (m['displayName'] ?? '').toString(),
      avatarUrl: (m['avatarUrl'] ?? '').toString(),
      subtitle: (m['subtitle'] ?? '').toString(),
      circleId: circleId.isNotEmpty ? circleId : null,
    );
  }

  factory ChatContactsRow.fromContactTabFunGroupMap(Map<String, dynamic> m) {
    final convId = (m['conversationId'] ?? m['id'] ?? '').toString();
    return ChatContactsRow(
      kind: ChatContactsRowKind.group,
      id: convId,
      displayName: (m['displayName'] ?? '').toString(),
      avatarUrl: (m['avatarUrl'] ?? '').toString(),
      subtitle: (m['subtitle'] ?? '').toString(),
      conversationId: convId.isNotEmpty ? convId : null,
    );
  }

  void open(BuildContext context) {
    switch (kind) {
      case ChatContactsRowKind.circle:
        context.push(AppRoutePaths.circleDetail(id: circleId ?? id));
        break;
      case ChatContactsRowKind.group:
        context.push(AppRoutePaths.chatDetail(id: conversationId ?? id));
        break;
      case ChatContactsRowKind.user:
        context.push(
          AppRoutePaths.userProfile(username: id),
          extra: UserProfileRouteExtra(
            profileSubjectId: id,
            avatar: avatarUrl,
            displayName: displayName,
          ),
        );
        break;
    }
  }
}
