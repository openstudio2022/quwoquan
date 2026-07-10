import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';

class _FakeCircleRepository extends MockCircleRepository {
  _FakeCircleRepository({required this.circles});

  final List<CircleDto> circles;

  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
    String? subCategory,
  }) async {
    return circles.take(limit).toList(growable: false);
  }
}

class _StubCloudHttpClient extends CloudHttpClient {
  _StubCloudHttpClient(this.handler) : super(client: http.Client());

  final Future<CloudHttpDecodedJson> Function(
    Uri uri,
    Map<String, String> headers,
  ) handler;

  @override
  Future<CloudHttpDecodedJson> getJson(
    Uri uri, {
    required Map<String, String> headers,
  }) {
    return handler(uri, headers);
  }
}

/// L1a 契约测试：content 领域 entry（创作入口）的 CreateLocationService / CreateCircleService 行为
///
/// 规范：specs/ux/error-and-permission-semantics.md
/// 领域：content，实体：entry（创作草稿/入口）
void main() {
  group('RemoteCreateLocationService', () {
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
      final service = RemoteCreateLocationService(
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
      final service = RemoteCreateLocationService(
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
      final service = RemoteCreateLocationService(
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

  // alpha/mock 模式专用：Mock 必须永远可用、永不发 HTTP、永不抛错，
  // 否则会回归「附近地点访问失败」整页断点（specs/ux/error-and-permission-semantics.md）。
  group('MockCreateLocationService', () {
    test('ensureLocationPermission 始终授予并返回位置（不依赖系统定位）', () async {
      final service = MockCreateLocationService();
      final outcome = await service.ensureLocationPermission();
      expect(outcome.result, LocationPermissionResult.granted);
      expect(outcome.position, isNotNull);
    });

    test('openAppSettings 不抛异常并返回 true', () async {
      final service = MockCreateLocationService();
      expect(await service.openAppSettings(), isTrue);
    });

    test('nearby 始终返回非空 canonical POI（杜绝附近地点访问失败断点）', () async {
      final service = MockCreateLocationService();
      final nearby = await service.nearby();
      expect(nearby, isNotEmpty);
      for (final poi in nearby) {
        expect(poi.name.trim(), isNotEmpty);
      }
    });

    test('search 空关键字回退到 nearby（与 Remote 语义一致）', () async {
      final service = MockCreateLocationService();
      final fallback = await service.search('   ');
      final nearby = await service.nearby();
      expect(fallback.length, nearby.length);
    });

    test('search 命中关键字时按名称/地址过滤', () async {
      final service = MockCreateLocationService();
      final matched = await service.search('天府');
      expect(matched, isNotEmpty);
      expect(matched.every((poi) => poi.name.contains('天府') || poi.address.contains('天府')), isTrue);
    });

    test('search 无命中时返回空列表而非抛异常', () async {
      final service = MockCreateLocationService();
      final matched = await service.search('完全不存在的地点XYZ');
      expect(matched, isEmpty);
    });
  });

  group('CreateCircleService', () {
    test('uses remote circles when endpoint has data', () async {
      const service = CreateCircleService();
      final fake = _FakeCircleRepository(
        circles: [
          CircleDto.fromMap({
            'id': 'c1',
            'name': '测试圈子A',
            'ownerId': 'u1',
            'coverUrl': 'https://example.com/c1.jpg',
            'memberCount': 88,
            'postCount': 12,
            'createdAt': '2025-01-01T00:00:00.000Z',
            'updatedAt': '2025-01-01T00:00:00.000Z',
          }),
          CircleDto.fromMap({
            'id': 'c2',
            'name': '测试圈子B',
            'ownerId': 'u1',
            'createdAt': '2025-01-01T00:00:00.000Z',
            'updatedAt': '2025-01-01T00:00:00.000Z',
          }),
        ],
      );
      final result = await service.listCircles(fake);
      expect(result.length, 2);
      expect(result.first.id, 'c1');
      expect(result.first.name, '测试圈子A');
      expect(result.first.coverUrl, 'https://example.com/c1.jpg');
      expect(result.first.memberCount, 88);
      expect(result.first.postCount, 12);
    });
  });
}
