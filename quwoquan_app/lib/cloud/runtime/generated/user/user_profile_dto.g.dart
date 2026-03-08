// Code generated from contracts/metadata/user/user_profile/fields.yaml. DO NOT EDIT.

class UserProfileDto {
  final String userId;
  final String nickname;
  final String? avatarUrl;
  final String? bio;
  final String? gender;
  final String? birthDate;
  final String? region;
  final String status;
  final int profileVersion;
  final int followerCount;
  final int followingCount;
  final int postCount;
  final int circleCount;
  final int likeCount;
  final String createdAt;
  final String updatedAt;

  const UserProfileDto({
    required this.userId,
    required this.nickname,
    this.avatarUrl,
    this.bio,
    this.gender,
    this.birthDate,
    this.region,
    required this.status,
    required this.profileVersion,
    required this.followerCount,
    required this.followingCount,
    required this.postCount,
    required this.circleCount,
    required this.likeCount,
    required this.createdAt,
    required this.updatedAt,
  });

  factory UserProfileDto.fromJson(Map<String, dynamic> json) {
    return UserProfileDto(
      userId: json['userId'] as String,
      nickname: json['nickname'] as String,
      avatarUrl: json['avatarUrl'] as String?,
      bio: json['bio'] as String?,
      gender: json['gender'] as String?,
      birthDate: json['birthDate'] as String?,
      region: json['region'] as String?,
      status: json['status'] as String? ?? 'active',
      profileVersion: (json['profileVersion'] as num?)?.toInt() ?? 1,
      followerCount: (json['followerCount'] as num?)?.toInt() ?? 0,
      followingCount: (json['followingCount'] as num?)?.toInt() ?? 0,
      postCount: (json['postCount'] as num?)?.toInt() ?? 0,
      circleCount: (json['circleCount'] as num?)?.toInt() ?? 0,
      likeCount: (json['likeCount'] as num?)?.toInt() ?? 0,
      createdAt: json['createdAt'] as String? ?? '',
      updatedAt: json['updatedAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'userId': userId,
        'nickname': nickname,
        'avatarUrl': avatarUrl,
        'bio': bio,
        'gender': gender,
        'birthDate': birthDate,
        'region': region,
        'status': status,
        'profileVersion': profileVersion,
        'followerCount': followerCount,
        'followingCount': followingCount,
        'postCount': postCount,
        'circleCount': circleCount,
        'likeCount': likeCount,
        'createdAt': createdAt,
        'updatedAt': updatedAt,
      };
}
