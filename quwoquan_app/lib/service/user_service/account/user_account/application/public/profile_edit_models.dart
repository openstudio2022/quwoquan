import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'package:quwoquan_app/service/user_service/account/user_account/domain/qr_payload_parser.dart';

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

  factory ProfileQrCardData.fromWire(
    ProfileQrCardWire projection, {
    DateTime? now,
  }) {
    final publicProfileUrl = projection.publicProfileUrl.trim();
    final qrPayload = projection.qrPayload.trim();
    final qrTokenId = projection.qrTokenId.trim();
    final displayName = projection.displayName.trim();
    if (publicProfileUrl != projection.publicProfileUrl ||
        qrPayload != projection.qrPayload ||
        qrTokenId != projection.qrTokenId ||
        displayName != projection.displayName ||
        publicProfileUrl.isEmpty ||
        qrPayload.isEmpty ||
        qrTokenId.isEmpty ||
        displayName.isEmpty) {
      throw StateError('Profile QR card is not canonical');
    }
    final profileUri = Uri.tryParse(publicProfileUrl);
    if (profileUri == null) {
      throw StateError('Profile QR card publicProfileUrl is invalid');
    }
    final card = ProfileQrCardData(
      publicProfileUrl: publicProfileUrl,
      qrPayload: qrPayload,
      qrTokenId: qrTokenId,
      avatarUrl: projection.avatarUrl ?? '',
      displayName: displayName,
      region: projection.region ?? '',
      shareText: projection.shareText ?? '',
      expiresAt: projection.expiresAt,
    );
    card.requireUsableAt(
      trustedPublicOrigin: Uri(
        scheme: profileUri.scheme,
        host: profileUri.host,
        port: profileUri.hasPort ? profileUri.port : null,
      ),
      now: now ?? DateTime.now(),
    );
    return card;
  }

  final String publicProfileUrl;
  final String qrPayload;
  final String qrTokenId;
  final String avatarUrl;
  final String displayName;
  final String region;
  final String shareText;
  final DateTime? expiresAt;

  /// 校验服务端卡片只能指向当前运行包信任的公开主页 origin，且尚未过期。
  QrPayloadParseResult requireUsableAt({
    required Uri trustedPublicOrigin,
    required DateTime now,
  }) {
    if (publicProfileUrl.trim() != publicProfileUrl ||
        qrPayload.trim() != qrPayload ||
        qrTokenId.trim() != qrTokenId ||
        displayName.trim() != displayName ||
        publicProfileUrl.isEmpty ||
        qrPayload.isEmpty ||
        qrTokenId.isEmpty ||
        displayName.isEmpty) {
      throw StateError('Profile QR card is not canonical');
    }
    final parsed = QrPayloadParser.parse(
      qrPayload,
      trustedPublicOrigin: trustedPublicOrigin,
    );
    if (parsed == null || parsed.publicProfileUrl != publicProfileUrl) {
      throw StateError('Profile QR card payload is not canonical');
    }
    final expiry = expiresAt;
    if (expiry != null && !expiry.toUtc().isAfter(now.toUtc())) {
      throw StateError('Profile QR card has expired');
    }
    return parsed;
  }
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
