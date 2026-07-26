import 'public_profile_query_contracts.dart';
import '../operation_request_payload.dart';
import 'user_contract_codec.dart';

abstract interface class UserHomepageQueryFacet {
  Future<UserHomepageBundleProjection> getUserHomepageBundle(
    GetUserHomepageBundleQuery query,
  );
}

final class GetUserHomepageBundleQuery {
  const GetUserHomepageBundleQuery({required this.subAccountId});

  final String subAccountId;

  Map<String, Object?> toJson() => <String, Object?>{
    'subAccountId': subAccountId,
  };
}

CloudOperationRequestPayload encodeGetUserHomepageBundleQuery(
  GetUserHomepageBundleQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'subAccountId': query.subAccountId.trim()},
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

final class HomepageRelationshipCapabilityProjection {
  const HomepageRelationshipCapabilityProjection({
    required this.viewerSubAccountId,
    required this.targetSubAccountId,
    required this.canCreateDirectConversation,
    required this.canSendMessage,
    required this.canGreet,
    required this.hasPendingGreeting,
    required this.hasFormalConversation,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
    required this.isBlocked,
    required this.isBlockedBy,
    this.relationState,
    this.canFollow,
    this.canUnfollow,
    this.canFollowBack,
    this.canOpenConversation,
  });

  final String viewerSubAccountId;
  final String targetSubAccountId;
  final String? relationState;
  final bool? canFollow;
  final bool? canUnfollow;
  final bool canCreateDirectConversation;
  final bool canSendMessage;
  final bool? canFollowBack;
  final bool canGreet;
  final bool? canOpenConversation;
  final bool hasPendingGreeting;
  final bool hasFormalConversation;
  final bool canStartVoiceCall;
  final bool canStartVideoCall;
  final bool isBlocked;
  final bool isBlockedBy;

  static HomepageRelationshipCapabilityProjection? fromJson(Object? value) {
    if (value == null) return null;
    final source = UserContractCodec.object(
      value,
      'HomepageRelationshipCapabilityProjection',
    );
    return HomepageRelationshipCapabilityProjection(
      viewerSubAccountId: UserContractCodec.textOr(
        source,
        'viewerSubAccountId',
        '',
      ),
      targetSubAccountId: UserContractCodec.textOr(
        source,
        'targetSubAccountId',
        '',
      ),
      relationState: UserContractCodec.optionalText(source['relationState']),
      canFollow: UserContractCodec.optionalBoolean(source, 'canFollow'),
      canUnfollow: UserContractCodec.optionalBoolean(source, 'canUnfollow'),
      canCreateDirectConversation: UserContractCodec.booleanOr(
        source,
        'canCreateDirectConversation',
        false,
      ),
      canSendMessage: UserContractCodec.booleanOr(
        source,
        'canSendMessage',
        false,
      ),
      canFollowBack: UserContractCodec.optionalBoolean(source, 'canFollowBack'),
      canGreet: UserContractCodec.booleanOr(source, 'canGreet', false),
      canOpenConversation: UserContractCodec.optionalBoolean(
        source,
        'canOpenConversation',
      ),
      hasPendingGreeting: UserContractCodec.booleanOr(
        source,
        'hasPendingGreeting',
        false,
      ),
      hasFormalConversation: UserContractCodec.booleanOr(
        source,
        'hasFormalConversation',
        false,
      ),
      canStartVoiceCall: UserContractCodec.booleanOr(
        source,
        'canStartVoiceCall',
        false,
      ),
      canStartVideoCall: UserContractCodec.booleanOr(
        source,
        'canStartVideoCall',
        false,
      ),
      isBlocked: UserContractCodec.booleanOr(source, 'isBlocked', false),
      isBlockedBy: UserContractCodec.booleanOr(source, 'isBlockedBy', false),
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
    required this.viewerSubAccountId,
    required this.isOwner,
    required this.isGuest,
    required this.relationToTarget,
    required this.canViewFullProfile,
  });

  final String viewerSubAccountId;
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
      viewerSubAccountId: UserContractCodec.textOr(
        source,
        'viewerSubAccountId',
        '',
      ),
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

  final SubAccountProfileProjection? profile;
  final UserProfileStatsProjection? stats;
  final HomepageRelationshipCapabilityProjection? relationshipCapability;
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
          : SubAccountProfileProjection.fromJson(source['profile']),
      stats: UserProfileStatsProjection.fromJson(source['stats']),
      relationshipCapability: HomepageRelationshipCapabilityProjection.fromJson(
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
