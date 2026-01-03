/// 用户数据模型
class User {
  final String id;
  final String? username;
  final String? avatarUrl;
  final String? avatar; // 别名，兼容avatarUrl
  final String? bio;
  final String? displayName;
  final bool? isVerified;
  final bool? isFollowing;
  final String? backgroundImage;
  final int? posts;
  final int? following;
  final int? likes;
  final int? bookmarks;
  final Map<String, dynamic>? metadata;
  
  const User({
    required this.id,
    this.username,
    this.avatarUrl,
    this.avatar,
    this.bio,
    this.displayName,
    this.isVerified,
    this.isFollowing,
    this.backgroundImage,
    this.posts,
    this.following,
    this.likes,
    this.bookmarks,
    this.metadata,
  });
  
  // Getter for avatar (兼容avatarUrl)
  String? get avatarUrlOrAvatar => avatarUrl ?? avatar;
  
  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id']?.toString() ?? '',
      username: json['username']?.toString(),
      avatarUrl: json['avatarUrl']?.toString(),
      bio: json['bio']?.toString(),
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'avatarUrl': avatarUrl,
      'bio': bio,
      'metadata': metadata,
    };
  }
}

