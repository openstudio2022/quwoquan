/// Canonical Search 实体主页命中的公开 App 投影。
final class SearchEntityHomepageHitView {
  const SearchEntityHomepageHitView({
    required this.homepageId,
    required this.name,
    this.subtitle,
    this.placeName,
    this.address,
    this.followerCount = 0,
    this.contentCount = 0,
  });

  final String homepageId;
  final String name;
  final String? subtitle;
  final String? placeName;
  final String? address;
  final int followerCount;
  final int contentCount;
}
