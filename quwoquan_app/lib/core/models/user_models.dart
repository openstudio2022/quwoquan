/// 用户数据模型
class User {
  final String id;
  final String? userHandle;
  final String? avatarUrl;
  final String? bio;
  final String? displayName;
  final bool? isVerified;
  final bool? isFollowing;
  final String? backgroundImage;
  final int? posts;
  final int? following;
  final int? likes;
  final Map<String, dynamic>? metadata;
  
  const User({
    required this.id,
    this.userHandle,
    this.avatarUrl,
    this.bio,
    this.displayName,
    this.isVerified,
    this.isFollowing,
    this.backgroundImage,
    this.posts,
    this.following,
    this.likes,
    this.metadata,
  });
  
  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id']?.toString() ?? '',
      userHandle: json['userHandle']?.toString(),
      avatarUrl: json['avatarUrl']?.toString(),
      bio: json['bio']?.toString(),
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'userHandle': userHandle,
      'avatarUrl': avatarUrl,
      'bio': bio,
      'metadata': metadata,
    };
  }
}
