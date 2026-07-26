import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

/// Persona 关注关系的 set/unset 命令面。
abstract interface class PersonaRelationshipCommandWriter {
  Future<void> follow(
    String targetSubAccountId, {
    required String sourceSurfaceId,
  });

  Future<void> unfollow(String targetSubAccountId);
}

/// Persona 关注关系的公开列表读面。
abstract interface class PersonaRelationshipQuery {
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String subAccountId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String subAccountId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}
