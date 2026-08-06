import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ProfileCredentialSummaryData {
  const ProfileCredentialSummaryData({
    required this.credentialType,
    required this.displayLabel,
    required this.isBound,
  });

  factory ProfileCredentialSummaryData.fromWire(
    ProfileCredentialSummaryWire projection,
  ) {
    return ProfileCredentialSummaryData(
      credentialType: projection.credentialType.wireName,
      displayLabel: projection.displayLabel,
      isBound: projection.isBound,
    );
  }

  final String credentialType;
  final String displayLabel;
  final bool isBound;

  bool get isPhoneLike =>
      credentialType == 'phone' || credentialType == 'carrier_phone';
}

class ProfileQrCardData {
  const ProfileQrCardData({
    required this.publicProfileUrl,
    required this.qrPayload,
    required this.qrTokenId,
    required this.avatarUrl,
    required this.displayName,
    required this.region,
    required this.shareText,
    this.expiresAt,
  });

  factory ProfileQrCardData.fromWire(ProfileQrCardWire projection) {
    if (projection.qrPayload.isEmpty) {
      throw StateError('Profile QR card qrPayload is required');
    }
    return ProfileQrCardData(
      publicProfileUrl: projection.publicProfileUrl,
      qrPayload: projection.qrPayload,
      qrTokenId: projection.qrTokenId,
      avatarUrl: projection.avatarUrl ?? '',
      displayName: projection.displayName,
      region: projection.region ?? '',
      shareText: projection.shareText ?? '',
      expiresAt: projection.expiresAt,
    );
  }

  final String publicProfileUrl;
  final String qrPayload;
  final String qrTokenId;
  final String avatarUrl;
  final String displayName;
  final String region;
  final String shareText;
  final DateTime? expiresAt;
}

class ProfileEditSnapshotData {
  const ProfileEditSnapshotData({
    required this.ownerUserId,
    required this.personaId,
    required this.avatarUrl,
    required this.avatarAssetId,
    required this.avatarVersion,
    required this.backgroundUrl,
    required this.backgroundAssetId,
    required this.nickname,
    required this.gender,
    required this.birthDate,
    required this.region,
    required this.regionTagRef,
    required this.userHandle,
    required this.bio,
    required this.occupationTagRef,
    required this.interestTagRefs,
    this.phoneCredential,
    this.qrCard,
  });

  factory ProfileEditSnapshotData.fromWire(ProfileEditSnapshotWire projection) {
    return ProfileEditSnapshotData(
      ownerUserId: projection.ownerUserId,
      personaId: projection.personaId,
      avatarUrl: projection.avatarUrl ?? '',
      avatarAssetId: projection.avatarAssetId ?? '',
      avatarVersion: projection.avatarVersion,
      backgroundUrl: projection.backgroundUrl ?? '',
      backgroundAssetId: projection.backgroundAssetId ?? '',
      nickname: projection.nickname.isEmpty
          ? projection.displayName
          : projection.nickname,
      gender: projection.gender?.wireName ?? 'unspecified',
      birthDate: projection.birthDate == null
          ? ''
          : _dateOnly(projection.birthDate!),
      region: projection.region ?? '',
      regionTagRef: projection.regionTagRef ?? '',
      userHandle: projection.userHandle,
      bio: projection.bio ?? '',
      occupationTagRef: projection.occupationTagRef ?? '',
      interestTagRefs: projection.interestTagRefs ?? const <String>[],
      phoneCredential: projection.phoneCredential == null
          ? null
          : ProfileCredentialSummaryData.fromWire(projection.phoneCredential!),
      qrCard: projection.qrCard == null
          ? null
          : ProfileQrCardData.fromWire(projection.qrCard!),
    );
  }

  final String ownerUserId;
  final String personaId;
  final String avatarUrl;
  final String avatarAssetId;
  final int avatarVersion;
  final String backgroundUrl;
  final String backgroundAssetId;
  final String nickname;
  final String gender;
  final String birthDate;
  final String region;
  final String regionTagRef;
  final String userHandle;
  final String bio;
  final String occupationTagRef;
  final List<String> interestTagRefs;
  final ProfileCredentialSummaryData? phoneCredential;
  final ProfileQrCardData? qrCard;

  ProfileQrCardData get effectiveQrCard {
    final card = qrCard;
    if (card == null) {
      throw StateError('Profile QR card is missing from edit snapshot');
    }
    return card;
  }
}

String _dateOnly(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';
