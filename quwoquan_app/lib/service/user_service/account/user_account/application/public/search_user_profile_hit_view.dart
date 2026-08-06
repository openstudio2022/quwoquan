import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CanonicalSearchIntersectionReason;

/// Canonical Search 用户命中的公开资料摘要。
final class SearchUserProfileHitView {
  const SearchUserProfileHitView({
    required this.userId,
    required this.displayName,
    this.bio,
    this.connectionState = 'unconnected',
    this.intersectionReason,
  });

  final String userId;
  final String displayName;
  final String? bio;
  final String connectionState;
  final CanonicalSearchIntersectionReason? intersectionReason;
}
