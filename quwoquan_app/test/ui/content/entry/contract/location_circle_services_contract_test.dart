import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/features/create/services/publish_settings_services.dart';

class _FakeDataService implements DataService {
  _FakeDataService({required this.circles});

  final List<Map<String, dynamic>> circles;

  @override
  Future<Map<String, dynamic>> createDataItem({
    required String endpoint,
    required Map<String, dynamic> data,
  }) async => <String, dynamic>{};

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
  }) async => <String, dynamic>{};

  @override
  Future<List<Map<String, dynamic>>> getDataList({
    required String endpoint,
    Map<String, dynamic>? params,
    int? limit,
    int? offset,
  }) async {
    if (endpoint == '/circles') {
      return circles;
    }
    return <Map<String, dynamic>>[];
  }

  @override
  Future<Map<String, dynamic>> updateDataItem({
    required String endpoint,
    required String id,
    required Map<String, dynamic> data,
  }) async => <String, dynamic>{};
}

class _StubCloudHttpClient extends CloudHttpClient {
  _StubCloudHttpClient(this.handler) : super(client: http.Client());

  final Future<dynamic> Function(Uri uri, Map<String, String> headers) handler;

  @override
  Future<dynamic> getJson(Uri uri, {required Map<String, String> headers}) {
    return handler(uri, headers);
  }
}

/// L1a 契约测试：content 领域 entry（创作入口）的 CreateLocationService / CreateCircleService 行为
///
/// 规范：specs/ux/error-and-permission-semantics.md
/// 领域：content，实体：entry（创作草稿/入口）
void main() {
  group('CreateLocationService', () {
    test('nearby parses cloud response', () async {
      final httpClient = _StubCloudHttpClient((_, headers) async {
        expect(headers, isNotNull);
        return jsonDecode(
          jsonEncode({
            IntegrationLocationMetadata.responseItemsKey: [
              {
                'name': '成都·天府广场',
                'latitude': 30.6586,
                'longitude': 104.0648,
                'address': '锦江区',
                'distanceMeters': 120,
              },
            ],
          }),
        );
      });
      final service = CreateLocationService(
        httpClient: httpClient,
        baseUrl: 'http://127.0.0.1:18080',
      );
      final nearby = await service.nearby();
      expect(nearby, isNotEmpty);
      expect(nearby.first.name, '成都·天府广场');
    });

    test('search parses cloud response', () async {
      final httpClient = _StubCloudHttpClient((_, headers) async {
        expect(headers, isNotNull);
        return jsonDecode(
          jsonEncode({
            IntegrationLocationMetadata.responseItemsKey: [
              {'name': '成都·太古里', 'latitude': 30.6548, 'longitude': 104.0839},
            ],
          }),
        );
      });
      final service = CreateLocationService(
        httpClient: httpClient,
        baseUrl: 'http://127.0.0.1:18080',
      );
      final search = await service.search('太古');
      expect(search, isNotEmpty);
      expect(search.first.name, contains('太古'));
    });

    test('rate limit keeps last nearby list', () async {
      var callCount = 0;
      final httpClient = _StubCloudHttpClient((_, headers) async {
        expect(headers, isNotNull);
        callCount++;
        if (callCount == 1) {
          return jsonDecode(
            jsonEncode({
              IntegrationLocationMetadata.responseItemsKey: [
                {'name': 'A', 'latitude': 1.0, 'longitude': 2.0},
              ],
            }),
          );
        }
        throw CloudException(
          type: CloudErrorType.unknown,
          message: 'rate limited',
          statusCode: 429,
        );
      });
      final service = CreateLocationService(
        httpClient: httpClient,
        baseUrl: 'http://127.0.0.1:18080',
      );
      final first = await service.nearby();
      final second = await service.nearby();
      expect(first.length, 1);
      expect(second.length, 1);
      expect(second.first.name, 'A');
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
