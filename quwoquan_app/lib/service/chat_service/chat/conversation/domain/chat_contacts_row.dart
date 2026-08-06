import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';

export 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';

ChatContactsRow chatContactsRowFromContactDto(
  ChatContactRowViewData dto, {
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

ChatContactsRow chatContactsRowFromContactHomeDto(
  ContactHomeRow dto, {
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
    personaId: (dto.userId?.trim().isEmpty ?? true) ? null : dto.userId!.trim(),
    userHandle: dto.userHandle.trim().isEmpty ? null : dto.userHandle.trim(),
    displayName: dto.title,
    avatarUrl: resolveAvatarImageUrl(
      dto.avatarUrl,
      endpointConfig: mediaEndpointConfig,
    ),
    subtitle: kind == ChatContactsRowKind.user
        ? dto.summaryIntersections.take(2).join(' · ')
        : dto.subtitle.trim(),
    relationState: dto.relationState ?? 'not_following',
    source: dto.kind,
    isStarred: dto.isStarred ?? false,
    circleId: (dto.circleId?.isNotEmpty ?? false) ? dto.circleId : null,
    conversationId: (dto.conversationId?.isNotEmpty ?? false)
        ? dto.conversationId
        : null,
  );
}

extension ChatContactsRowNavigation on ChatContactsRow {
  void open(BuildContext context) {
    switch (kind) {
      case ChatContactsRowKind.circle:
        context.push(
          AppRoutePaths.circleDetail(id: circleId ?? id),
          extra: const CircleDetailPageRouteExtra(
            referralSource: ReferralSource.chatLink,
          ),
        );
      case ChatContactsRowKind.group:
        context.push(AppRoutePaths.chatDetail(id: conversationId ?? id));
      case ChatContactsRowKind.user:
        final handle = userHandle?.trim() ?? '';
        if (handle.isEmpty) {
          return;
        }
        context.push(
          AppRoutePaths.userProfile(userHandle: handle),
          extra: UserProfileRouteExtra(
            personaId: personaId,
            avatarUrl: avatarUrl,
            displayName: displayName,
          ),
        );
    }
  }
}
