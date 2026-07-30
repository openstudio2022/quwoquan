part of '../alpha_user_profile_repository.dart';

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

RelationshipViewWireDto _relationshipViewFromRaw(Map<String, dynamic> raw) {
  return RelationshipViewWireDto(
    viewerPersonaId: raw['viewerPersonaId']?.toString() ?? '',
    targetPersonaId: raw['targetPersonaId']?.toString() ?? '',
    relationState: _normalizeRelationshipState(raw),
    isBlocked: raw['isBlocked'] == true,
    isBlockedBy: raw['isBlockedBy'] == true,
  );
}
