import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

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
    int limit = CloudApiDefaults.pageLimit,
  });
}
