import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_edit_query.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Persona ProfileEditQuery 的 production Remote adapter。
final class RemoteProfileEditQuery implements ProfileEditQuery {
  const RemoteProfileEditQuery({
    required this.editSnapshotQuery,
    required this.publicProfileQuery,
  });

  final ProfileEditSnapshotQueryFacet editSnapshotQuery;
  final PublicProfileQueryFacet publicProfileQuery;

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    final projection = await editSnapshotQuery.getProfileEditSnapshot(
      GetProfileEditSnapshotQuery(),
    );
    return ProfileEditSnapshotData.fromWire(projection);
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    final projection = await publicProfileQuery.getProfileQrCard(
      GetProfileQrCardQuery(),
    );
    return ProfileQrCardData.fromWire(projection);
  }
}
