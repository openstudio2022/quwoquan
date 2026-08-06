/// Legacy discovery profile snapshot used by feed composition.
final class User {
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
}
