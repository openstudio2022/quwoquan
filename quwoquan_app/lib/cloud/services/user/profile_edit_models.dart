import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_edit_snapshot_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_card_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ProfileCredentialSummaryData {
  const ProfileCredentialSummaryData({
    required this.credentialType,
    required this.displayLabel,
    required this.isBound,
  });

  factory ProfileCredentialSummaryData.fromMap(Map<String, dynamic> map) {
    return ProfileCredentialSummaryData(
      credentialType: map['credentialType']?.toString() ?? '',
      displayLabel: map['displayLabel']?.toString() ?? '',
      isBound: map['isBound'] as bool? ?? false,
    );
  }

  factory ProfileCredentialSummaryData.fromCredentialRow(
    OwnerCredentialRowDto row,
  ) {
    return ProfileCredentialSummaryData(
      credentialType: row.credentialType,
      displayLabel: row.displayLabel,
      isBound: row.isActive,
    );
  }

  factory ProfileCredentialSummaryData.fromProjection(
    ProfileCredentialSummaryProjection projection,
  ) {
    return ProfileCredentialSummaryData(
      credentialType: projection.credentialType,
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

  factory ProfileQrCardData.fromMap(Map<String, dynamic> map) {
    final qrPayload = map['qrPayload']?.toString() ?? '';
    if (qrPayload.isEmpty) {
      throw StateError('Profile QR card qrPayload is required');
    }
    return ProfileQrCardData(
      publicProfileUrl: map['publicProfileUrl']?.toString() ?? '',
      qrPayload: qrPayload,
      qrTokenId: map['qrTokenId']?.toString() ?? '',
      avatarUrl: map['avatarUrl']?.toString() ?? '',
      displayName: map['displayName']?.toString() ?? '',
      region: map['region']?.toString() ?? '',
      shareText: map['shareText']?.toString() ?? '',
      expiresAt: _dateTimeFromAny(map['expiresAt']),
    );
  }

  factory ProfileQrCardData.fromWire(ProfileQrCardWireDto wire) {
    if (wire.qrPayload.isEmpty) {
      throw StateError('Profile QR card qrPayload is required');
    }
    return ProfileQrCardData(
      publicProfileUrl: wire.publicProfileUrl,
      qrPayload: wire.qrPayload,
      qrTokenId: wire.qrTokenId,
      avatarUrl: wire.avatarUrl,
      displayName: wire.displayName,
      region: wire.region,
      shareText: wire.shareText,
      expiresAt: wire.expiresAt,
    );
  }

  factory ProfileQrCardData.fromProjection(ProfileQrCardProjection projection) {
    if (projection.qrPayload.isEmpty) {
      throw StateError('Profile QR card qrPayload is required');
    }
    return ProfileQrCardData(
      publicProfileUrl: projection.publicProfileUrl,
      qrPayload: projection.qrPayload,
      qrTokenId: projection.qrTokenId,
      avatarUrl: projection.avatarUrl,
      displayName: projection.displayName,
      region: projection.region,
      shareText: projection.shareText,
      expiresAt: projection.expiresAt,
    );
  }

  factory ProfileQrCardData.mockFromSnapshot(ProfileEditSnapshotData snapshot) {
    final handle = snapshot.userHandle.isEmpty
        ? snapshot.personaId
        : snapshot.userHandle;
    final encodedHandle = Uri.encodeComponent(handle);
    final url =
        'https://mock.quwoquan.local/u/$encodedHandle?qr=mock_$encodedHandle';
    return ProfileQrCardData(
      publicProfileUrl: 'https://mock.quwoquan.local/u/$encodedHandle',
      qrPayload: url,
      qrTokenId: 'qr_$handle',
      avatarUrl: snapshot.avatarUrl,
      displayName: snapshot.nickname,
      region: snapshot.region,
      shareText: url,
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

  factory ProfileEditSnapshotData.fromMap(Map<String, dynamic> map) {
    final phoneCredential = map['phoneCredential'];
    final qrCard = map['qrCard'];
    return ProfileEditSnapshotData(
      ownerUserId: map['ownerUserId']?.toString() ?? '',
      personaId: map['personaId']?.toString() ?? '',
      avatarUrl: map['avatarUrl']?.toString() ?? '',
      avatarAssetId: map['avatarAssetId']?.toString() ?? '',
      avatarVersion: (map['avatarVersion'] as num?)?.toInt() ?? 0,
      backgroundUrl: map['backgroundUrl']?.toString() ?? '',
      backgroundAssetId: map['backgroundAssetId']?.toString() ?? '',
      nickname: map['nickname']?.toString() ?? '',
      gender: map['gender']?.toString() ?? 'unspecified',
      birthDate: map['birthDate']?.toString() ?? '',
      region: map['region']?.toString() ?? '',
      regionTagRef: map['regionTagRef']?.toString() ?? '',
      userHandle: map['userHandle']?.toString() ?? '',
      bio: map['bio']?.toString() ?? '',
      occupationTagRef: map['occupationTagRef']?.toString() ?? '',
      interestTagRefs: _stringList(map['interestTagRefs']),
      phoneCredential: phoneCredential is Map<String, dynamic>
          ? ProfileCredentialSummaryData.fromMap(phoneCredential)
          : phoneCredential is Map
          ? ProfileCredentialSummaryData.fromMap(
              Map<String, dynamic>.from(phoneCredential),
            )
          : null,
      qrCard: qrCard is Map<String, dynamic>
          ? ProfileQrCardData.fromMap(qrCard)
          : qrCard is Map
          ? ProfileQrCardData.fromMap(Map<String, dynamic>.from(qrCard))
          : null,
    );
  }

  factory ProfileEditSnapshotData.fromWire(ProfileEditSnapshotWireDto wire) {
    return ProfileEditSnapshotData(
      ownerUserId: wire.ownerUserId,
      personaId: wire.personaId,
      avatarUrl: wire.avatarUrl,
      avatarAssetId: wire.avatarAssetId,
      avatarVersion: wire.avatarVersion,
      backgroundUrl: wire.backgroundUrl,
      backgroundAssetId: wire.backgroundAssetId,
      nickname: wire.nickname.isEmpty ? wire.displayName : wire.nickname,
      gender: wire.gender,
      birthDate: wire.birthDate,
      region: wire.region,
      regionTagRef: wire.regionTagRef,
      userHandle: wire.userHandle,
      bio: wire.bio,
      occupationTagRef: wire.occupationTagRef,
      interestTagRefs: wire.interestTagRefs,
      phoneCredential: wire.phoneCredential == null
          ? null
          : ProfileCredentialSummaryData.fromMap(wire.phoneCredential!),
      qrCard: wire.qrCard == null
          ? null
          : ProfileQrCardData.fromMap(wire.qrCard!),
    );
  }

  factory ProfileEditSnapshotData.fromProjection(
    ProfileEditSnapshotProjection projection,
  ) {
    return ProfileEditSnapshotData(
      ownerUserId: projection.ownerUserId,
      personaId: projection.personaId,
      avatarUrl: projection.avatarUrl,
      avatarAssetId: projection.avatarAssetId,
      avatarVersion: projection.avatarVersion,
      backgroundUrl: projection.backgroundUrl,
      backgroundAssetId: projection.backgroundAssetId,
      nickname: projection.nickname.isEmpty
          ? projection.displayName
          : projection.nickname,
      gender: projection.gender,
      birthDate: projection.birthDate,
      region: projection.region,
      regionTagRef: projection.regionTagRef,
      userHandle: projection.userHandle,
      bio: projection.bio,
      occupationTagRef: projection.occupationTagRef,
      interestTagRefs: projection.interestTagRefs,
      phoneCredential: projection.phoneCredential == null
          ? null
          : ProfileCredentialSummaryData.fromProjection(
              projection.phoneCredential!,
            ),
      qrCard: projection.qrCard == null
          ? null
          : ProfileQrCardData.fromProjection(projection.qrCard!),
    );
  }

  factory ProfileEditSnapshotData.fromProfile({
    required PersonaProfileViewData profile,
    List<OwnerCredentialRowDto> credentials = const <OwnerCredentialRowDto>[],
  }) {
    final phoneCredential = credentials
        .where((row) => row.credentialType == 'phone')
        .followedBy(
          credentials.where((row) => row.credentialType == 'carrier_phone'),
        )
        .cast<OwnerCredentialRowDto?>()
        .firstWhere((row) => row != null, orElse: () => null);
    final occupationTagRef = profile.identityTags
        .where((tag) => tag.startsWith('Audience/用户/职业/'))
        .cast<String?>()
        .firstWhere((tag) => tag != null, orElse: () => null);
    final interestTags = profile.identityTags
        .where((tag) => tag.startsWith('Audience/用户/兴趣偏好/'))
        .toList(growable: false);
    return ProfileEditSnapshotData(
      ownerUserId: profile.ownerUserId,
      personaId: profile.personaId,
      avatarUrl: profile.avatarUrl,
      avatarAssetId: '',
      avatarVersion: profile.avatarVersion,
      backgroundUrl: profile.backgroundUrl,
      backgroundAssetId: '',
      nickname: profile.displayName,
      gender: 'unspecified',
      birthDate: '',
      region: '',
      regionTagRef: '',
      userHandle: profile.userHandle.isEmpty
          ? profile.personaId
          : profile.userHandle,
      bio: profile.bio,
      occupationTagRef: occupationTagRef ?? '',
      interestTagRefs: interestTags,
      phoneCredential: phoneCredential == null
          ? null
          : ProfileCredentialSummaryData.fromCredentialRow(phoneCredential),
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

List<String> _stringList(Object? value) {
  if (value is Iterable) {
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
  if (value is String && value.trim().isNotEmpty) {
    return value
        .split(',')
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
  return const <String>[];
}

DateTime? _dateTimeFromAny(Object? value) {
  if (value is DateTime) {
    return value;
  }
  if (value is String && value.trim().isNotEmpty) {
    return DateTime.tryParse(value.trim());
  }
  return null;
}
