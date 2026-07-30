import 'public_profile_query_contracts.dart';
import '../operation_request_payload.dart';
import 'user_contract_codec.dart';
part '../generated/requests/user/profile_edit_query_contracts.requests.g.dart';

abstract interface class ProfileEditSnapshotQueryFacet {
  Future<ProfileEditSnapshotProjection> getProfileEditSnapshot(
    GetProfileEditSnapshotQuery query,
  );
}





final class ProfileCredentialSummaryProjection {
  const ProfileCredentialSummaryProjection({
    required this.credentialType,
    required this.displayLabel,
    required this.isBound,
  });

  final String credentialType;
  final String displayLabel;
  final bool isBound;

  static ProfileCredentialSummaryProjection? fromJson(Object? value) {
    if (value == null) return null;
    final source = UserContractCodec.object(
      value,
      'ProfileCredentialSummaryProjection',
    );
    return ProfileCredentialSummaryProjection(
      credentialType: UserContractCodec.textOr(source, 'credentialType', ''),
      displayLabel: UserContractCodec.textOr(source, 'displayLabel', ''),
      isBound: UserContractCodec.booleanOr(source, 'isBound', false),
    );
  }
}

final class ProfileEditSnapshotProjection {
  const ProfileEditSnapshotProjection({
    required this.ownerUserId,
    required this.personaId,
    required this.avatarUrl,
    required this.avatarAssetId,
    required this.avatarVersion,
    required this.backgroundUrl,
    required this.backgroundAssetId,
    required this.nickname,
    required this.displayName,
    required this.gender,
    required this.birthDate,
    required this.region,
    required this.regionTagRef,
    required this.userHandle,
    required this.bio,
    required this.identityTags,
    required this.occupationTagRef,
    required this.interestTagRefs,
    this.phoneCredential,
    this.qrCard,
    this.updatedAt,
  });

  final String ownerUserId;
  final String personaId;
  final String avatarUrl;
  final String avatarAssetId;
  final int avatarVersion;
  final String backgroundUrl;
  final String backgroundAssetId;
  final String nickname;
  final String displayName;
  final String gender;
  final String birthDate;
  final String region;
  final String regionTagRef;
  final String userHandle;
  final String bio;
  final List<String> identityTags;
  final String occupationTagRef;
  final List<String> interestTagRefs;
  final ProfileCredentialSummaryProjection? phoneCredential;
  final ProfileQrCardProjection? qrCard;
  final DateTime? updatedAt;

  static ProfileEditSnapshotProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'ProfileEditSnapshotProjection',
    );
    return ProfileEditSnapshotProjection(
      ownerUserId: UserContractCodec.requiredText(source, 'ownerUserId'),
      personaId: UserContractCodec.requiredText(source, 'personaId'),
      avatarUrl: UserContractCodec.textOr(source, 'avatarUrl', ''),
      avatarAssetId: UserContractCodec.textOr(source, 'avatarAssetId', ''),
      avatarVersion: UserContractCodec.integerOr(source, 'avatarVersion', 0),
      backgroundUrl: UserContractCodec.textOr(source, 'backgroundUrl', ''),
      backgroundAssetId: UserContractCodec.textOr(
        source,
        'backgroundAssetId',
        '',
      ),
      nickname: UserContractCodec.textOr(source, 'nickname', ''),
      displayName: UserContractCodec.textOr(source, 'displayName', ''),
      gender: UserContractCodec.textOr(source, 'gender', 'unspecified'),
      birthDate: UserContractCodec.textOr(source, 'birthDate', ''),
      region: UserContractCodec.textOr(source, 'region', ''),
      regionTagRef: UserContractCodec.textOr(source, 'regionTagRef', ''),
      userHandle: UserContractCodec.textOr(source, 'userHandle', ''),
      bio: UserContractCodec.textOr(source, 'bio', ''),
      identityTags: UserContractCodec.stringList(
        source['identityTags'],
        'identityTags',
      ),
      occupationTagRef: UserContractCodec.textOr(
        source,
        'occupationTagRef',
        '',
      ),
      interestTagRefs: UserContractCodec.stringList(
        source['interestTagRefs'],
        'interestTagRefs',
      ),
      phoneCredential: ProfileCredentialSummaryProjection.fromJson(
        source['phoneCredential'],
      ),
      qrCard: source['qrCard'] == null
          ? null
          : ProfileQrCardProjection.fromJson(source['qrCard']),
      updatedAt: UserContractCodec.optionalTimestamp(source, 'updatedAt'),
    );
  }
}

ProfileEditSnapshotProjection decodeProfileEditSnapshotProjection(
  Object? value,
) {
  return ProfileEditSnapshotProjection.fromJson(value);
}
