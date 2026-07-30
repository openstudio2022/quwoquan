import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/circle_detail_page_route_extra.dart';

enum ChatContactsRowKind { user, circle, group }

/// 联系人 Tab 一行展示（用户 / 圈子 / 群），避免页面持有 Map。
class ChatContactsRow {
  const ChatContactsRow({
    required this.kind,
    required this.id,
    required this.displayName,
    required this.avatarUrl,
    required this.subtitle,
    this.personaId,
    this.userHandle,
    this.relationState = 'not_following',
    this.source = '',
    this.isStarred = false,
    this.circleId,
    this.conversationId,
  });

  final ChatContactsRowKind kind;
  final String id;
  final String displayName;
  final String avatarUrl;
  final String subtitle;
  final String? personaId;
  final String? userHandle;
  final String relationState;
  final String source;
  final bool isStarred;
  final String? circleId;
  final String? conversationId;

  bool get isMutualFollow => relationState == 'mutual';

  factory ChatContactsRow.fromContactDto(
    ChatContactRowDto dto, {
    MediaEndpointConfig? mediaEndpointConfig,
  }) {
    var sub = '';
    for (final raw in [dto.bio, dto.metFrom, dto.lastInteraction]) {
      final t = raw.trim();
      if (t.isNotEmpty) {
        sub = t;
        break;
      }
    }
    final source = dto.source.trim().isNotEmpty
        ? dto.source.trim()
        : switch (dto.relationState) {
            'mutual' => 'mutual',
            'following' => 'following',
            'followed_by' => 'following',
            _ => 'conversation',
          };
    return ChatContactsRow(
      kind: ChatContactsRowKind.user,
      id: dto.userId,
      personaId: dto.userId.trim().isEmpty ? null : dto.userId.trim(),
      userHandle: dto.userHandle.trim().isEmpty ? null : dto.userHandle.trim(),
      displayName: dto.displayName,
      avatarUrl: resolveAvatarImageUrl(
        dto.avatarUrl,
        endpointConfig: mediaEndpointConfig,
      ),
      subtitle: sub,
      relationState: dto.relationState,
      source: source,
      isStarred: dto.isStarred,
    );
  }

  factory ChatContactsRow.fromContactHomeDto(
    ContactHomeRowDto dto, {
    MediaEndpointConfig? mediaEndpointConfig,
  }) {
    final kind = switch (dto.kind) {
      'circle' => ChatContactsRowKind.circle,
      'group' => ChatContactsRowKind.group,
      _ => ChatContactsRowKind.user,
    };
    return ChatContactsRow(
      kind: kind,
      id: dto.id.isNotEmpty ? dto.id : dto.objectId,
      personaId: dto.userId.trim().isEmpty ? null : dto.userId.trim(),
      userHandle: dto.userHandle.trim().isEmpty ? null : dto.userHandle.trim(),
      displayName: dto.title,
      avatarUrl: resolveAvatarImageUrl(
        dto.avatarUrl,
        endpointConfig: mediaEndpointConfig,
      ),
      subtitle: dto.subtitle.trim().isNotEmpty
          ? dto.subtitle.trim()
          : dto.summaryIntersections.take(2).join(' · '),
      relationState: dto.relationState,
      source: dto.kind,
      isStarred: dto.isStarred,
      circleId: dto.circleId.isNotEmpty ? dto.circleId : null,
      conversationId: dto.conversationId.isNotEmpty ? dto.conversationId : null,
    );
  }

  factory ChatContactsRow.fromContactTabCircleDto(
    ChatContactTabCircleRowDto d,
  ) {
    return ChatContactsRow(
      kind: ChatContactsRowKind.circle,
      id: d.circleId,
      displayName: d.displayName,
      avatarUrl: resolveAvatarImageUrl(d.avatarUrl),
      subtitle: d.subtitle,
      source: 'circle',
      circleId: d.circleId.isNotEmpty ? d.circleId : null,
    );
  }

  factory ChatContactsRow.fromContactTabFunGroupDto(
    ChatContactTabFunGroupRowDto d,
  ) {
    return ChatContactsRow(
      kind: ChatContactsRowKind.group,
      id: d.conversationId,
      displayName: d.displayName,
      avatarUrl: resolveAvatarImageUrl(d.avatarUrl),
      subtitle: d.subtitle,
      source: 'group',
      conversationId: d.conversationId.isNotEmpty ? d.conversationId : null,
    );
  }

  void open(BuildContext context) {
    switch (kind) {
      case ChatContactsRowKind.circle:
        context.push(
          AppRoutePaths.circleDetail(id: circleId ?? id),
          extra: const CircleDetailPageRouteExtra(
            referralSource: ReferralSource.chatLink,
          ),
        );
        break;
      case ChatContactsRowKind.group:
        context.push(AppRoutePaths.chatDetail(id: conversationId ?? id));
        break;
      case ChatContactsRowKind.user:
        final handle = userHandle?.trim() ?? '';
        if (handle.isEmpty) {
          return;
        }
        context.push(
          AppRoutePaths.userProfile(userHandle: handle),
          extra: UserProfileRouteExtra(
            personaId: personaId,
            avatar: avatarUrl,
            displayName: displayName,
          ),
        );
        break;
    }
  }
}
