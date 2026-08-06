/// Content 等调用对象可写入的最窄作者快照缓存边界。
abstract interface class UserProfileAuthorSnapshotCache {
  void putAuthorSnapshot({
    required String userId,
    String? displayName,
    String? avatarUrl,
    String? backgroundUrl,
    String? updatedAt,
  });
}
