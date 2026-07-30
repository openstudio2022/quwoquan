import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ProfileEditQuery 的 production Remote adapter。
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
    return ProfileEditSnapshotData.fromProjection(projection);
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    final projection = await publicProfileQuery.getProfileQrCard(
      GetProfileQrCardQuery(),
    );
    return ProfileQrCardData.fromProjection(projection);
  }

  @override
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    final normalizedToken = token.trim();
    if (normalizedToken.isEmpty) {
      throw ArgumentError.value(token, 'token', 'qr token required');
    }
    final normalizedHandle = handle.trim();
    final projection = await publicProfileQuery.resolveProfileQrToken(
      ResolveProfileQrTokenQuery(
        qr: normalizedToken,
        handle: normalizedHandle.isEmpty ? null : normalizedHandle,
      ),
    );
    return ProfileQrResolveWireDto(
      personaId: projection.personaId,
      userHandle: projection.userHandle,
      publicProfileUrl: projection.publicProfileUrl,
      scanStatus: projection.scanStatus,
    );
  }
}
