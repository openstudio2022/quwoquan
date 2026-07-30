import '../operation_request_payload.dart';
import 'persona_relationship_contracts.dart';
import 'user_contract_codec.dart';
part '../generated/requests/user/public_profile_query_contracts.requests.g.dart';

abstract interface class PublicProfileQueryFacet {
  Future<PersonaProfileProjection> getMeProfile(GetMeProfileQuery query);

  Future<PersonaProfileProjection> getPersonaProfile(
    GetPersonaProfileQuery query,
  );

  Future<ProfileQrCardProjection> getProfileQrCard(GetProfileQrCardQuery query);

  Future<ProfileQrResolveProjection> resolveProfileQrToken(
    ResolveProfileQrTokenQuery query,
  );

  Future<SearchSocialRelationsResult> searchSocialRelations(
    SearchSocialRelationsQuery query,
  );
}

final class PersonaProfileProjection {
  const PersonaProfileProjection({
    required this.personaId,
    required this.ownerUserId,
    required this.userHandle,
    required this.nickname,
    required this.displayName,
    required this.username,
    required this.subjectType,
    required this.nicknameCustomized,
    required this.avatarUrl,
    required this.avatarVersion,
    required this.backgroundUrl,
    required this.bio,
    required this.identityTags,
    required this.verified,
    required this.followerCount,
    required this.followingCount,
    required this.postCount,
    required this.circleCount,
    required this.likeCount,
    required this.profileCompleteness,
    required this.profileCompletenessMissingItems,
    required this.profileVisibility,
    required this.isolationLevel,
    required this.inheritsFromOwner,
    this.overriddenFields,
    this.updatedAt,
  });

  final String personaId;
  final String ownerUserId;
  final String userHandle;
  final String nickname;
  final String displayName;
  final String username;
  final String subjectType;
  final bool nicknameCustomized;
  final String avatarUrl;
  final int avatarVersion;
  final String backgroundUrl;
  final String bio;
  final List<String> identityTags;
  final bool verified;
  final int followerCount;
  final int followingCount;
  final int postCount;
  final int circleCount;
  final int likeCount;
  final int profileCompleteness;
  final List<String> profileCompletenessMissingItems;
  final String profileVisibility;
  final String isolationLevel;
  final bool inheritsFromOwner;
  final List<String>? overriddenFields;
  final DateTime? updatedAt;

  static PersonaProfileProjection fromJson(Object? value) {
    final source = UserContractCodec.object(value, 'PersonaProfileProjection');
    return PersonaProfileProjection(
      personaId: UserContractCodec.requiredText(source, 'personaId'),
      ownerUserId: UserContractCodec.textOr(source, 'ownerUserId', ''),
      userHandle: UserContractCodec.textOr(source, 'userHandle', ''),
      nickname: UserContractCodec.textOr(source, 'nickname', ''),
      displayName: UserContractCodec.textOr(source, 'displayName', ''),
      username: UserContractCodec.textOr(source, 'username', ''),
      subjectType: UserContractCodec.textOr(source, 'subjectType', 'persona'),
      nicknameCustomized: UserContractCodec.booleanOr(
        source,
        'nicknameCustomized',
        false,
      ),
      avatarUrl: UserContractCodec.textOr(source, 'avatarUrl', ''),
      avatarVersion: UserContractCodec.integerOr(source, 'avatarVersion', 0),
      backgroundUrl: UserContractCodec.textOr(source, 'backgroundUrl', ''),
      bio: UserContractCodec.textOr(source, 'bio', ''),
      identityTags: UserContractCodec.stringList(
        source['identityTags'],
        'identityTags',
      ),
      verified: UserContractCodec.booleanOr(source, 'verified', false),
      followerCount: UserContractCodec.integerOr(source, 'followerCount', 0),
      followingCount: UserContractCodec.integerOr(source, 'followingCount', 0),
      postCount: UserContractCodec.integerOr(source, 'postCount', 0),
      circleCount: UserContractCodec.integerOr(source, 'circleCount', 0),
      likeCount: UserContractCodec.integerOr(source, 'likeCount', 0),
      profileCompleteness: UserContractCodec.integerOr(
        source,
        'profileCompleteness',
        100,
      ),
      profileCompletenessMissingItems: UserContractCodec.stringList(
        source['profileCompletenessMissingItems'],
        'profileCompletenessMissingItems',
      ),
      profileVisibility: UserContractCodec.textOr(
        source,
        'profileVisibility',
        'public',
      ),
      isolationLevel: UserContractCodec.textOr(
        source,
        'isolationLevel',
        'open',
      ),
      inheritsFromOwner: UserContractCodec.booleanOr(
        source,
        'inheritsFromOwner',
        false,
      ),
      overriddenFields: source['overriddenFields'] == null
          ? null
          : UserContractCodec.stringList(
              source['overriddenFields'],
              'overriddenFields',
            ),
      updatedAt: UserContractCodec.optionalTimestamp(source, 'updatedAt'),
    );
  }
}

PersonaProfileProjection decodePersonaProfileProjection(Object? value) {
  return PersonaProfileProjection.fromJson(value);
}

final class ProfileQrCardProjection {
  const ProfileQrCardProjection({
    required this.publicProfileUrl,
    required this.qrPayload,
    required this.qrTokenId,
    required this.avatarUrl,
    required this.avatarVersion,
    required this.displayName,
    required this.region,
    required this.shareText,
    this.expiresAt,
  });

  final String publicProfileUrl;
  final String qrPayload;
  final String qrTokenId;
  final String avatarUrl;
  final String avatarVersion;
  final String displayName;
  final String region;
  final String shareText;
  final DateTime? expiresAt;

  static ProfileQrCardProjection fromJson(Object? value) {
    final source = UserContractCodec.object(value, 'ProfileQrCardProjection');
    return ProfileQrCardProjection(
      publicProfileUrl: UserContractCodec.textOr(
        source,
        'publicProfileUrl',
        '',
      ),
      qrPayload: UserContractCodec.requiredText(source, 'qrPayload'),
      qrTokenId: UserContractCodec.textOr(source, 'qrTokenId', ''),
      avatarUrl: UserContractCodec.textOr(source, 'avatarUrl', ''),
      avatarVersion: UserContractCodec.textOr(source, 'avatarVersion', ''),
      displayName: UserContractCodec.textOr(source, 'displayName', ''),
      region: UserContractCodec.textOr(source, 'region', ''),
      shareText: UserContractCodec.textOr(source, 'shareText', ''),
      expiresAt: UserContractCodec.optionalTimestamp(source, 'expiresAt'),
    );
  }
}

ProfileQrCardProjection decodeProfileQrCardProjection(Object? value) {
  return ProfileQrCardProjection.fromJson(value);
}

final class ProfileQrResolveProjection {
  const ProfileQrResolveProjection({
    required this.personaId,
    required this.userHandle,
    required this.publicProfileUrl,
    required this.scanStatus,
  });

  final String personaId;
  final String userHandle;
  final String publicProfileUrl;
  final String scanStatus;

  static ProfileQrResolveProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'ProfileQrResolveProjection',
    );
    return ProfileQrResolveProjection(
      personaId: UserContractCodec.requiredText(source, 'personaId'),
      userHandle: UserContractCodec.textOr(source, 'userHandle', ''),
      publicProfileUrl: UserContractCodec.textOr(
        source,
        'publicProfileUrl',
        '',
      ),
      scanStatus: UserContractCodec.textOr(source, 'scanStatus', 'accepted'),
    );
  }
}

ProfileQrResolveProjection decodeProfileQrResolveProjection(Object? value) {
  return ProfileQrResolveProjection.fromJson(value);
}

final class SocialRelationSearchItemProjection {
  const SocialRelationSearchItemProjection({
    required this.personaId,
    required this.username,
    required this.userHandle,
    required this.displayName,
    required this.avatarVersion,
    required this.chatAvailable,
    required this.relationshipCapability,
    this.avatarUrl,
    this.headline,
  });

  final String personaId;
  final String username;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final String? headline;
  final bool chatAvailable;
  final RelationshipCapabilityResult relationshipCapability;

  static SocialRelationSearchItemProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'SocialRelationSearchItemProjection',
    );
    return SocialRelationSearchItemProjection(
      personaId: UserContractCodec.requiredText(source, 'personaId'),
      username: UserContractCodec.textOr(source, 'username', ''),
      userHandle: UserContractCodec.textOr(source, 'userHandle', ''),
      displayName: UserContractCodec.textOr(source, 'displayName', ''),
      avatarUrl: UserContractCodec.optionalText(source['avatarUrl']),
      avatarVersion: UserContractCodec.integerOr(source, 'avatarVersion', 0),
      headline: UserContractCodec.optionalText(source['headline']),
      chatAvailable: UserContractCodec.booleanOr(
        source,
        'chatAvailable',
        false,
      ),
      relationshipCapability: decodeRelationshipCapabilityResult(
        source['relationshipCapability'],
      ),
    );
  }
}

final class SearchSocialRelationsResult {
  const SearchSocialRelationsResult({
    required this.items,
    required this.cursor,
  });

  final List<SocialRelationSearchItemProjection> items;
  final String cursor;

  static SearchSocialRelationsResult fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'SearchSocialRelationsResult',
    );
    return SearchSocialRelationsResult(
      items: List<SocialRelationSearchItemProjection>.unmodifiable(
        UserContractCodec.objectList(
          source['items'],
          'SearchSocialRelationsResult.items',
        ).map(SocialRelationSearchItemProjection.fromJson),
      ),
      cursor: UserContractCodec.textOr(source, 'cursor', ''),
    );
  }
}

SearchSocialRelationsResult decodeSearchSocialRelationsResult(Object? value) {
  return SearchSocialRelationsResult.fromJson(value);
}
