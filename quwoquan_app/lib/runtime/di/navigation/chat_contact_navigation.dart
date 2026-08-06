import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';

void openChatContactsRow(BuildContext context, ChatContactsRow row) {
  switch (row.kind) {
    case ChatContactsRowKind.circle:
      context.push(
        AppRoutePaths.circleDetail(id: row.circleId ?? row.id),
        extra: const CircleDetailPageRouteExtra(
          referralSource: ReferralSource.chatLink,
        ),
      );
      break;
    case ChatContactsRowKind.group:
      context.push(AppRoutePaths.chatDetail(id: row.conversationId ?? row.id));
      break;
    case ChatContactsRowKind.user:
      final handle = row.userHandle?.trim() ?? '';
      if (handle.isEmpty) {
        return;
      }
      context.push(
        AppRoutePaths.userProfile(userHandle: handle),
        extra: UserProfileRouteExtra(
          personaId: row.personaId,
          avatarUrl: row.avatarUrl,
          displayName: row.displayName,
        ),
      );
      break;
  }
}
