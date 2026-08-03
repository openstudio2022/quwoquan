import 'user_operation_contracts.g.dart';

abstract interface class PublicProfileQueryFacet {
  Future<PersonaProfileView> getMeProfile(GetMeProfileQuery query);
  Future<PersonaProfileView> getPersonaProfile(GetPersonaProfileQuery query);
  Future<ProfileQrCardWire> getProfileQrCard(GetProfileQrCardQuery query);
  Future<ProfileQrResolveWire> resolveProfileQrToken(
    ResolveProfileQrTokenQuery query,
  );
  Future<SearchSocialRelationsResult> searchSocialRelations(
    SearchSocialRelationsQuery query,
  );
}
