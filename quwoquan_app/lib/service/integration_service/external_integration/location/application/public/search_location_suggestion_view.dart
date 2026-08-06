import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show LocationPoi;

/// 搜索页使用的 Integration location POI 建议投影。
///
/// Integration POI 与 Search place 投影在调用侧汇合，不伪造经纬度把
/// `location.place` 冒充 Cloud [LocationPoi]。
final class SearchLocationSuggestionViewData {
  const SearchLocationSuggestionViewData({
    required this.id,
    required this.name,
    this.address,
  });

  factory SearchLocationSuggestionViewData.fromWire(LocationPoi wire) =>
      SearchLocationSuggestionViewData(
        id: wire.id,
        name: wire.name,
        address: wire.address,
      );

  final String id;
  final String name;
  final String? address;
}
