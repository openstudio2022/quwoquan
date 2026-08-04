import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class ContactProfileQueryFake implements ProfileQuery {
  ContactProfileQueryFake({
    this.profile,
    this.searchItems = const <SocialRelationSearchItemViewData>[],
    this.searchError,
  });

  final PersonaProfileViewData? profile;
  final List<SocialRelationSearchItemViewData> searchItems;
  final Object? searchError;

  @override
  Future<PersonaProfileViewData> getUserProfile(String userId) async {
    final value = profile;
    if (value == null) {
      throw StateError('profile not configured');
    }
    return value;
  }

  @override
  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = 20,
  }) async {
    final error = searchError;
    if (error != null) {
      throw error;
    }
    return searchItems.take(limit).toList(growable: false);
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(String personaId) {
    throw UnimplementedError();
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) {
    throw UnimplementedError();
  }
}

final class ContactProfileEditQueryFake implements ProfileEditQuery {
  ContactProfileEditQueryFake({required this.qrCard, this.resolveResult});

  final ProfileQrCardData qrCard;
  final ProfileQrResolveWire? resolveResult;

  @override
  Future<ProfileQrCardData> getProfileQrCard() async => qrCard;

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() {
    throw UnimplementedError();
  }

  @override
  Future<ProfileQrResolveWire> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    final value = resolveResult;
    if (value == null) {
      throw StateError('QR resolve result not configured');
    }
    return value;
  }
}

final class ContactPersonaQueryFake implements PersonaQuery {
  ContactPersonaQueryFake({required this.profile});

  final PersonaProfileViewData profile;

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) async {
    return profile;
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() {
    throw UnimplementedError();
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) {
    throw UnimplementedError();
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() {
    throw UnimplementedError();
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() {
    throw UnimplementedError();
  }
}
