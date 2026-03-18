import 'package:flutter/foundation.dart';

@immutable
class ProfileSubjectViewData {
  const ProfileSubjectViewData({
    required this.profileSubjectId,
    required this.ownerUserId,
    required this.subjectType,
    required this.subAccountId,
    required this.username,
    required this.displayName,
    required this.avatarUrl,
    required this.backgroundUrl,
    required this.bio,
    required this.followerCount,
    required this.followingCount,
    required this.postCount,
    required this.circleCount,
    required this.likeCount,
    required this.profileVisibility,
    required this.inheritsFromOwner,
    required this.overriddenFields,
    required this.updatedAt,
  });

  final String profileSubjectId;
  final String ownerUserId;
  final String subjectType;
  final String subAccountId;
  final String username;
  final String displayName;
  final String avatarUrl;
  final String backgroundUrl;
  final String bio;
  final int followerCount;
  final int followingCount;
  final int postCount;
  final int circleCount;
  final int likeCount;
  final String profileVisibility;
  final bool inheritsFromOwner;
  final List<String> overriddenFields;
  final DateTime? updatedAt;

  factory ProfileSubjectViewData.fromMap(Map<String, dynamic> map) {
    final subjectId =
        _string(map['profileSubjectId']) ??
        _string(map['subAccountId']) ??
        _string(map['userId']) ??
        '';
    final ownerUserId = _string(map['ownerUserId']) ?? _string(map['userId']) ?? '';
    final subAccountId = _string(map['subAccountId']) ?? '';
    final nickname = _string(map['nickname']) ?? '';
    final displayName =
        _string(map['displayName']) ??
        (nickname.isNotEmpty ? nickname : null) ??
        subjectId;
    return ProfileSubjectViewData(
      profileSubjectId: subjectId,
      ownerUserId: ownerUserId,
      subjectType:
          _string(map['subjectType']) ??
          (subAccountId.isNotEmpty ? 'sub_account' : 'owner'),
      subAccountId: subAccountId,
      username:
          _string(map['username']) ??
          (nickname.isNotEmpty ? nickname : subjectId),
      displayName: displayName,
      avatarUrl: _string(map['avatarUrl']) ?? '',
      backgroundUrl:
          _string(map['backgroundUrl']) ??
          _string(map['backgroundImage']) ??
          '',
      bio: _string(map['bio']) ?? '',
      followerCount: _int(map['followerCount']),
      followingCount: _int(map['followingCount']),
      postCount: _int(map['postCount']),
      circleCount: _int(map['circleCount']),
      likeCount: _int(map['likeCount']),
      profileVisibility: _string(map['profileVisibility']) ?? 'public',
      inheritsFromOwner: _bool(map['inheritsFromOwner']),
      overriddenFields: _stringList(map['overriddenFields']),
      updatedAt: _dateTime(map['updatedAt']),
    );
  }

  ProfileSubjectViewData mergeStats(Map<String, dynamic> stats) {
    return ProfileSubjectViewData(
      profileSubjectId: profileSubjectId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      subAccountId: subAccountId,
      username: username,
      displayName: displayName,
      avatarUrl: avatarUrl,
      backgroundUrl: backgroundUrl,
      bio: bio,
      followerCount: _int(stats['followerCount'], fallback: followerCount),
      followingCount: _int(stats['followingCount'], fallback: followingCount),
      postCount: _int(stats['postCount'], fallback: postCount),
      circleCount: _int(stats['circleCount'], fallback: circleCount),
      likeCount: _int(stats['likeCount'], fallback: likeCount),
      profileVisibility: profileVisibility,
      inheritsFromOwner: inheritsFromOwner,
      overriddenFields: overriddenFields,
      updatedAt: updatedAt,
    );
  }
}

@immutable
class ProfileCircleViewData {
  const ProfileCircleViewData({
    required this.id,
    required this.name,
    required this.coverUrl,
    required this.memberCount,
    required this.postCount,
  });

  final String id;
  final String name;
  final String coverUrl;
  final int memberCount;
  final int postCount;

  factory ProfileCircleViewData.fromMap(Map<String, dynamic> map) {
    return ProfileCircleViewData(
      id: _string(map['id']) ?? '',
      name: _string(map['name']) ?? '',
      coverUrl: _string(map['coverUrl']) ?? '',
      memberCount: _int(map['memberCount']),
      postCount: _int(map['postCount']),
    );
  }
}

@immutable
class ProfileInteractionActivityViewData {
  const ProfileInteractionActivityViewData({
    required this.activityId,
    required this.activityType,
    required this.direction,
    required this.actorProfileSubjectId,
    required this.actorDisplayName,
    required this.actorAvatarUrl,
    required this.targetProfileSubjectId,
    required this.targetContentId,
    required this.targetContentType,
    required this.targetContentSummary,
    required this.createdAt,
  });

  final String activityId;
  final String activityType;
  final String direction;
  final String actorProfileSubjectId;
  final String actorDisplayName;
  final String actorAvatarUrl;
  final String targetProfileSubjectId;
  final String targetContentId;
  final String targetContentType;
  final String targetContentSummary;
  final DateTime? createdAt;

  factory ProfileInteractionActivityViewData.fromMap(Map<String, dynamic> map) {
    final actorProfileSubjectId =
        _string(map['actorProfileSubjectId']) ?? _string(map['userId']) ?? '';
    final activityType =
        _string(map['activityType']) ?? _string(map['contentType']) ?? '';
    return ProfileInteractionActivityViewData(
      activityId:
          _string(map['activityId']) ??
          _string(map['id']) ??
          '${activityType.isEmpty ? 'activity' : activityType}:$actorProfileSubjectId',
      activityType: activityType,
      direction: _string(map['direction']) ?? 'received',
      actorProfileSubjectId: actorProfileSubjectId,
      actorDisplayName:
          _string(map['actorDisplayName']) ??
          _string(map['nickname']) ??
          _string(map['displayName']) ??
          actorProfileSubjectId,
      actorAvatarUrl:
          _string(map['actorAvatarUrl']) ?? _string(map['avatarUrl']) ?? '',
      targetProfileSubjectId:
          _string(map['targetProfileSubjectId']) ?? _string(map['targetUserId']) ?? '',
      targetContentId:
          _string(map['targetContentId']) ?? _string(map['postId']) ?? '',
      targetContentType:
          _string(map['targetContentType']) ?? _string(map['contentType']) ?? '',
      targetContentSummary:
          _string(map['targetContentSummary']) ??
          _string(map['targetTitle']) ??
          '',
      createdAt: _dateTime(map['createdAt']),
    );
  }
}

String? _string(Object? value) {
  final result = value?.toString().trim();
  if (result == null || result.isEmpty) return null;
  return result;
}

int _int(Object? value, {int fallback = 0}) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

bool _bool(Object? value) {
  if (value is bool) return value;
  if (value is String) return value.toLowerCase() == 'true';
  return false;
}

List<String> _stringList(Object? value) {
  if (value is List) {
    return value.map((item) => item.toString()).where((item) => item.isNotEmpty).toList();
  }
  return const [];
}

DateTime? _dateTime(Object? value) {
  final raw = value?.toString();
  if (raw == null || raw.isEmpty) return null;
  return DateTime.tryParse(raw);
}
