import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/features/create/services/publish_settings_services.dart';

class _FakeDataService implements DataService {
  _FakeDataService({required this.circles});

  final List<Map<String, dynamic>> circles;

  @override
  Future<Map<String, dynamic>> createDataItem({
    required String endpoint,
    required Map<String, dynamic> data,
  }) async {
    return <String, dynamic>{};
  }

  @override
  Future<void> deleteDataItem({
    required String endpoint,
    required String id,
  }) async {}

  @override
  Future<Map<String, dynamic>> getDataItem({
    required String endpoint,
    required String id,
    Map<String, dynamic>? params,
  }) async {
    return <String, dynamic>{};
  }

  @override
  Future<List<Map<String, dynamic>>> getDataList({
    required String endpoint,
    Map<String, dynamic>? params,
    int? limit,
    int? offset,
  }) async {
    if (endpoint == '/circles') return circles;
    return <Map<String, dynamic>>[];
  }

  @override
  Future<Map<String, dynamic>> updateDataItem({
    required String endpoint,
    required String id,
    required Map<String, dynamic> data,
  }) async {
    return <String, dynamic>{};
  }
}

void main() {
  group('CreateLocationService', () {
    test('search returns filtered nearby locations', () async {
      const service = CreateLocationService();
      final result = await service.search('太古');
      expect(result.isNotEmpty, isTrue);
      expect(result.first.name.contains('太古'), isTrue);
    });
  });

  group('CreateCircleService', () {
    test('uses remote circles when endpoint has data', () async {
      const service = CreateCircleService();
      final fake = _FakeDataService(
        circles: <Map<String, dynamic>>[
          <String, dynamic>{'id': 'c1', 'name': '测试圈子A'},
          <String, dynamic>{'id': 'c2', 'name': '测试圈子B'},
        ],
      );
      final result = await service.listCircles(fake);
      expect(result.length, 2);
      expect(result.first.id, 'c1');
      expect(result.first.name, '测试圈子A');
    });
  });
}
