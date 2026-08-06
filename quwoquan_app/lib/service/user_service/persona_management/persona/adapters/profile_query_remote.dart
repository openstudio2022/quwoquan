import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/social_relation_search_item_view_mapper.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Persona ProfileQuery 的 production Remote adapter。
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
  Future<PersonaProfileViewData> getUserProfile(String userId) async {
    final normalized = userId.trim();
    final projection = normalized == 'me'
        ? await _publicProfileQuery.getMeProfile(GetMeProfileQuery())
        : await _publicProfileQuery.getPersonaProfile(
            GetPersonaProfileQuery(personaId: normalized),
          );
    return personaProfileViewDataFromWire(projection);
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String personaId,
  ) async {
    final projection = await _userHomepageQuery.getUserHomepageBundle(
      GetUserHomepageBundleQuery(personaId: personaId),
    );
    return UserHomepageBundleViewData.fromWire(
      projection,
      profile: personaProfileViewDataFromWire(projection.profile),
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    return UserProfileStatsViewData.fromProfile(await getUserProfile(userId));
  }

  @override
  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = SearchSocialRelationsQuery.defaultLimit,
  }) async {
    final result = await _publicProfileQuery.searchSocialRelations(
      SearchSocialRelationsQuery(query: query, limit: limit),
    );
    return result.items
        .map(SocialRelationSearchItemViewMapper.fromWire)
        .toList(growable: false);
  }
}
