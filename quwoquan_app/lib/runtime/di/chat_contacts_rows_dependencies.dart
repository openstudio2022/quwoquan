import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contact_home_filter.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/contact_intersection_subtitle.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

export 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contact_home_filter.dart';

final chatContactsRowsForSubTabProvider =
    FutureProvider.family<List<ChatContactsRow>, ChatContactHomeFilter>((
      ref,
      filter,
    ) async {
      final repo = ref.watch(chatContactRepositoryProvider);
      final rows = await repo.listContactHome(
        filter: filter.wireValue,
        limit: 500,
      );
      return rows.map(chatContactsRowFromContactHome).toList(growable: false);
    });

ChatContactsRow chatContactsRowFromContactView(
  ChatContactRowViewData dto, {
  MediaEndpointConfig? mediaEndpointConfig,
}) {
  var subtitle = '';
  for (final raw in <String>[dto.bio, dto.metFrom, dto.lastInteraction]) {
    final value = raw.trim();
    if (value.isNotEmpty) {
      subtitle = value;
      break;
    }
  }
  final source = dto.source.trim().isNotEmpty
      ? dto.source.trim()
      : switch (dto.relationState) {
          'mutual' => 'mutual',
          'following' || 'followed_by' => 'following',
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
    subtitle: subtitle,
    relationState: dto.relationState,
    source: source,
    isStarred: dto.isStarred,
  );
}

ChatContactsRow chatContactsRowFromContactHome(
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
        ? contactIntersectionFactsSubtitle(dto.intersectionFacts)
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
