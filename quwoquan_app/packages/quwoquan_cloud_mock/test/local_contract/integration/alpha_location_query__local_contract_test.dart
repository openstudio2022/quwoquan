import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/src/integration/alpha_location_query.dart';
import 'package:test/test.dart';

void main() {
  group('AlphaLocationQueryAdapter', () {
    test('只消费构建期 Integration fixture bundle', () async {
      final adapter = AlphaLocationQueryAdapter();

      final nearby = await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(),
      );

      expect(nearby.items, isNotEmpty);
      expect(
        nearby.items.every(
          (item) =>
              item.id.trim().isNotEmpty &&
              item.name.trim().isNotEmpty &&
              item.latitude != 0 &&
              item.longitude != 0,
        ),
        isTrue,
      );
    });

    test('search 与 nearby 共享同一 canonical fixture', () async {
      final adapter = AlphaLocationQueryAdapter();
      final nearby = await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(),
      );
      final target = nearby.items.first;

      final result = await adapter.searchLocations(
        LocationSearchQueryParams(query: target.name),
      );

      expect(result.items.map((item) => item.id), contains(target.id));
    });

    test('limit 在 Mock 与 Remote capability 上语义一致', () async {
      final adapter = AlphaLocationQueryAdapter();

      final nearby = await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(limit: 1),
      );

      expect(nearby.items, hasLength(1));
    });
  });
}
