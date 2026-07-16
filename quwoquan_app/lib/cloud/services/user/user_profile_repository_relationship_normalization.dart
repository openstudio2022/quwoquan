part of 'user_profile_repository.dart';

String _normalizeRelationshipState(Map<String, dynamic> map) {
  final state = map['relationState']?.toString() ?? '';
  if (state.isNotEmpty) return state;
  final isFollowing = map['isFollowing'] == true;
  final isFollowedBy = map['isFollowedBy'] == true;
  if (isFollowing && isFollowedBy) return 'mutual';
  if (isFollowing) return 'following';
  if (isFollowedBy) return 'followed_by';
  return 'not_following';
}

Map<String, dynamic> _normalizeRelationshipItem(Map<String, dynamic> raw) {
  final subAccountId =
      raw['subAccountId']?.toString() ??
      raw['targetSubAccountId']?.toString() ??
      raw['userId']?.toString() ??
      '';
  final displayName =
      raw['displayName']?.toString() ??
      raw['nickname']?.toString() ??
      subAccountId;
  final userHandle =
      raw['userHandle']?.toString() ??
      raw['username']?.toString() ??
      subAccountId;
  final username =
      raw['username']?.toString() ??
      raw['userHandle']?.toString() ??
      subAccountId;
  final avatarUrl =
      raw['avatarUrl']?.toString() ??
      raw['avatarUrlSnapshot']?.toString() ??
      '';
  final relationState = _normalizeRelationshipState(raw);
  final capability = raw['relationshipCapability'];
  final relationshipCapability = capability is Map
      ? Map<String, dynamic>.from(capability)
      : <String, dynamic>{
          'targetSubAccountId': subAccountId,
          'relationState': relationState,
          'canFollow':
              relationState == 'not_following' ||
              relationState == 'followed_by',
          'canUnfollow':
              relationState == 'following' || relationState == 'mutual',
          'canFollowBack': relationState == 'followed_by',
        };
  return <String, dynamic>{
    ...raw,
    'subAccountId': subAccountId,
    'userId': subAccountId,
    'username': username,
    'userHandle': userHandle,
    'displayName': displayName,
    'nickname': displayName,
    'avatarUrl': avatarUrl,
    'profileVisibility': raw['profileVisibility']?.toString() ?? 'public',
    'relationState': relationState,
    'relationshipCapability': relationshipCapability,
  };
}

RelationshipNormalizedWireDto _relationshipNormalizedFromRaw(
  Map<String, dynamic> raw,
) {
  final relationState = _normalizeRelationshipState(raw);
  final isMutual = relationState == 'mutual';
  final isFollowing = relationState == 'following' || isMutual;
  final isFollowedBy = relationState == 'followed_by' || isMutual;
  return RelationshipNormalizedWireDto(
    relationState: relationState,
    isFollowing: raw['isFollowing'] == true || isFollowing,
    isFollowedBy: raw['isFollowedBy'] == true || isFollowedBy,
    isMutual: raw['isMutual'] == true || isMutual,
  );
}
