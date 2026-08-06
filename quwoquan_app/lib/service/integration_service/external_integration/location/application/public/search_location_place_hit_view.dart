/// Canonical Search 第一方 `integration.location` 命中的公开 App 投影。
final class SearchLocationPlaceHitView {
  const SearchLocationPlaceHitView({
    required this.placeId,
    required this.name,
    this.address,
  });

  final String placeId;
  final String name;
  final String? address;
}
