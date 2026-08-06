import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 用户资料与主页聚合读面。
///
/// 仅承载 UserProfile 对象的公开资料、主页聚合、统计与社交搜索投影；作者影响
/// 摘要和证据由 content/content/post 的 AuthorImpactQuery 提供。
abstract interface class ProfileQuery {
  Future<PersonaProfileViewData> getUserProfile(String userId);

  Future<UserHomepageBundleViewData> getUserHomepageBundle(String personaId);

  Future<UserProfileStatsViewData> getUserStats(String userId);

  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = SearchSocialRelationsQuery.defaultLimit,
  });
}
