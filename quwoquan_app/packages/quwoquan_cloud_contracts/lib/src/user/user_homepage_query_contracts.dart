import 'public_profile_query_contracts.dart';
import '../operation_request_payload.dart';
import 'persona_relationship_contracts.dart';
import 'user_contract_codec.dart';
part '../generated/requests/user/user_homepage_query_contracts.requests.g.dart';

abstract interface class UserHomepageQueryFacet {
  Future<UserHomepageBundleProjection> getUserHomepageBundle(
    GetUserHomepageBundleQuery query,
  );
}





final class UserProfileStatsProjection {
  const UserProfileStatsProjection({
    required this.followingCount,
    required this.circleCount,
    required this.followerCount,
    required this.likeCount,
    required this.postCount,
  });

  final int followingCount;
  final int circleCount;
  final int followerCount;
  final int likeCount;
  final int postCount;

  static UserProfileStatsProjection? fromJson(Object? value) {
    if (value == null) return null;
    final source = UserContractCodec.object(
      value,
      'UserProfileStatsProjection',
    );
    return UserProfileStatsProjection(
      followingCount: UserContractCodec.integerOr(source, 'followingCount', 0),
      circleCount: UserContractCodec.integerOr(source, 'circleCount', 0),
      followerCount: UserContractCodec.integerOr(source, 'followerCount', 0),
      likeCount: UserContractCodec.integerOr(source, 'likeCount', 0),
      postCount: UserContractCodec.integerOr(source, 'postCount', 0),
    );
  }
}

final class UserHomepageTabCountsProjection {
  const UserHomepageTabCountsProjection({
    required this.worksCount,
    required this.likesCount,
    required this.circlesCount,
    required this.collectionsCount,
  });

  final int worksCount;
  final int likesCount;
  final int circlesCount;
  final int collectionsCount;

  static UserHomepageTabCountsProjection? fromJson(Object? value) {
    if (value == null) return null;
    final source = UserContractCodec.object(
      value,
      'UserHomepageTabCountsProjection',
    );
    return UserHomepageTabCountsProjection(
      worksCount: UserContractCodec.integerOr(source, 'worksCount', 0),
      likesCount: UserContractCodec.integerOr(source, 'likesCount', 0),
      circlesCount: UserContractCodec.integerOr(source, 'circlesCount', 0),
      collectionsCount: UserContractCodec.integerOr(
        source,
        'collectionsCount',
        0,
      ),
    );
  }
}

final class UserHomepageViewerContextProjection {
  const UserHomepageViewerContextProjection({
    required this.viewerPersonaId,
    required this.isOwner,
    required this.isGuest,
    required this.relationToTarget,
    required this.canViewFullProfile,
  });

  final String viewerPersonaId;
  final bool isOwner;
  final bool isGuest;
  final String relationToTarget;
  final bool canViewFullProfile;

  static UserHomepageViewerContextProjection? fromJson(Object? value) {
    if (value == null) return null;
    final source = UserContractCodec.object(
      value,
      'UserHomepageViewerContextProjection',
    );
    return UserHomepageViewerContextProjection(
      viewerPersonaId: UserContractCodec.textOr(source, 'viewerPersonaId', ''),
      isOwner: UserContractCodec.booleanOr(source, 'isOwner', false),
      isGuest: UserContractCodec.booleanOr(source, 'isGuest', false),
      relationToTarget: UserContractCodec.textOr(
        source,
        'relationToTarget',
        'not_following',
      ),
      canViewFullProfile: UserContractCodec.booleanOr(
        source,
        'canViewFullProfile',
        true,
      ),
    );
  }
}

final class UserHomepageBundleProjection {
  const UserHomepageBundleProjection({
    required this.cacheVersion,
    this.profile,
    this.stats,
    this.relationshipCapability,
    this.tabCounts,
    this.viewerContext,
  });

  final PersonaProfileProjection? profile;
  final UserProfileStatsProjection? stats;
  final RelationshipCapabilityResult? relationshipCapability;
  final UserHomepageTabCountsProjection? tabCounts;
  final UserHomepageViewerContextProjection? viewerContext;
  final String cacheVersion;

  static UserHomepageBundleProjection fromJson(Object? value) {
    final source = UserContractCodec.object(
      value,
      'UserHomepageBundleProjection',
    );
    return UserHomepageBundleProjection(
      profile: source['profile'] == null
          ? null
          : PersonaProfileProjection.fromJson(source['profile']),
      stats: UserProfileStatsProjection.fromJson(source['stats']),
      relationshipCapability: source['relationshipCapability'] == null
          ? null
          : decodeRelationshipCapabilityResult(
              source['relationshipCapability'],
            ),
      tabCounts: UserHomepageTabCountsProjection.fromJson(source['tabCounts']),
      viewerContext: UserHomepageViewerContextProjection.fromJson(
        source['viewerContext'],
      ),
      cacheVersion: UserContractCodec.textOr(source, 'cacheVersion', ''),
    );
  }
}

UserHomepageBundleProjection decodeUserHomepageBundleProjection(Object? value) {
  return UserHomepageBundleProjection.fromJson(value);
}
