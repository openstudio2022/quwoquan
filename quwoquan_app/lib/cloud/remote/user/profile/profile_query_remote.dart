import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ProfileQuery 的 production Remote adapter。
///
/// 仅做 UserProfile projection → App ViewData 映射；请求执行由 generated client Facet
/// 承担，Content/Post 作者影响力由独立 AuthorImpactQuery 提供。
final class RemoteProfileQuery implements ProfileQuery {
  factory RemoteProfileQuery({
    required PublicProfileQueryFacet publicProfileQuery,
    required UserHomepageQueryFacet userHomepageQuery,
  }) {
    return RemoteProfileQuery._(publicProfileQuery, userHomepageQuery);
  }

  const RemoteProfileQuery._(this._publicProfileQuery, this._userHomepageQuery);

  final PublicProfileQueryFacet _publicProfileQuery;
  final UserHomepageQueryFacet _userHomepageQuery;

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    final normalized = userId.trim();
    final projection = normalized == 'me'
        ? await _publicProfileQuery.getMeProfile(const GetMeProfileQuery())
        : await _publicProfileQuery.getSubAccountProfile(
            GetSubAccountProfileQuery(subAccountId: normalized),
          );
    return SubAccountProfileViewData.fromSubAccountProfileProjection(
      projection,
    );
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    final projection = await _userHomepageQuery.getUserHomepageBundle(
      GetUserHomepageBundleQuery(subAccountId: subAccountId),
    );
    return UserHomepageBundleViewData.fromUserHomepageBundleProjection(
      projection,
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    return UserProfileStatsViewData.fromProfile(await getUserProfile(userId));
  }

  @override
  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = 20,
  }) async {
    final result = await _publicProfileQuery.searchSocialRelations(
      SearchSocialRelationsQuery(query: query, limit: limit),
    );
    return result.items
        .map(SocialRelationSearchItemView.fromProjection)
        .toList(growable: false);
  }
}
