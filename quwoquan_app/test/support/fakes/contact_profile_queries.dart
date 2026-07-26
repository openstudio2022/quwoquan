import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

final class ContactProfileQueryFake implements ProfileQuery {
  ContactProfileQueryFake({
    this.profile,
    this.searchItems = const <SocialRelationSearchItemView>[],
    this.searchError,
  });

  final SubAccountProfileViewData? profile;
  final List<SocialRelationSearchItemView> searchItems;
  final Object? searchError;

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    final value = profile;
    if (value == null) {
      throw StateError('profile not configured');
    }
    return value;
  }

  @override
  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
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
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) {
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
  final ProfileQrResolveWireDto? resolveResult;

  @override
  Future<ProfileQrCardData> getProfileQrCard() async => qrCard;

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() {
    throw UnimplementedError();
  }

  @override
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
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

  final SubAccountProfileViewData profile;

  @override
  Future<SubAccountProfileViewData> getSubAccountProfile(
    String subAccountId,
  ) async {
    return profile;
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() {
    throw UnimplementedError();
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String subAccountId,
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
