import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 仅投影快照许可的公开 creator；不授予账号、关系或私域能力。
final class BundledProfileQuery implements ProfileQuery, PersonaQuery {
  BundledProfileQuery({required this.loadBundle});

  final Future<OfflineContentBundle> Function() loadBundle;
  Future<OfflineContentBundle>? _bundle;

  Future<OfflineContentBundle> _readBundle() =>
      (_bundle ??= loadBundle().catchError((Object error) {
        _bundle = null;
        throw error;
      })).timeout(const Duration(seconds: 6));

  PersonaProfileViewData _profile(OfflineContentBundle bundle, String id) {
    final rows = bundle
        .rows('creators')
        .where(
          (row) =>
              (row['projection']! as Map<String, Object?>)['personaId'] == id,
        );
    if (rows.length != 1) {
      throw const OfflineContentFailure('bundle_creator_not_found');
    }
    return personaProfileViewDataFromWire(
      PersonaProfileView.fromWire(
        rows.single['projection']! as Map<String, Object?>,
      ),
    );
  }

  String _publicId(String id) {
    final normalized = id.trim();
    if (normalized.isEmpty || normalized == 'me') {
      throw contentCapabilityUnavailable('private_profile');
    }
    return normalized;
  }

  @override
  Future<PersonaProfileViewData> getUserProfile(String userId) async {
    final id = _publicId(userId);
    return _profile(await _readBundle(), id);
  }

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) =>
      getUserProfile(personaId);

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String personaId,
  ) async {
    final id = _publicId(personaId);
    final bundle = await _readBundle();
    final profile = _profile(bundle, id);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    return UserHomepageBundleViewData(
      profile: profile,
      stats: stats,
      relationshipCapability: null,
      tabCounts: UserHomepageTabCountsViewData.fromStats(stats),
      viewerContext: const UserHomepageViewerContextViewData.guest(),
      cacheVersion: bundle.digest,
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async =>
      UserProfileStatsViewData.fromProfile(await getUserProfile(userId));

  @override
  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = SearchSocialRelationsQuery.defaultLimit,
  }) async => throw contentCapabilityUnavailable('social_relations');

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async =>
      throw contentCapabilityUnavailable('persona_management');

  @override
  Future<PersonaManagementSummaryViewData>
  getPersonaManagementSummary() async =>
      throw contentCapabilityUnavailable('persona_management');

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async =>
      throw contentCapabilityUnavailable('active_persona');

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async => throw contentCapabilityUnavailable('persona_management');
}
