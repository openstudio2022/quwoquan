import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Persona 关注关系的 set/unset 命令面。
abstract interface class PersonaRelationshipCommandWriter {
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  });

  Future<void> unfollow(String targetPersonaId);
}

/// Persona 关注关系的公开列表读面。
abstract interface class PersonaRelationshipQuery {
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  });

  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  });
}
