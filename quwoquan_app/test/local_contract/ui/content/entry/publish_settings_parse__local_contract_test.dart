import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/location_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class _StubOperationExecutor implements CloudOperationExecutor {
  _StubOperationExecutor(this.response);

  final Object? response;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    requestEncoder();
    return responseDecoder(response);
  }
}

RemoteLocationQueryAdapter _adapter(Object? response) {
  return RemoteLocationQueryAdapter(
    client: GeneratedCloudOperationClient(_StubOperationExecutor(response)),
    invocationContext: (clientPageId) => CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.createWorkspace.id,
      routeId: AppUiSurfaces.createWorkspace.routeId,
      clientPageId: clientPageId,
      actor: const CloudOperationActorContext(deviceActorId: 'test-device'),
    ),
  );
}

void main() {
  group('RemoteLocationQueryAdapter response codec', () {
    test('合法 items 解析为 typed LocationPoiListSlice', () async {
      final adapter = _adapter(<String, dynamic>{
        'items': <Map<String, Object?>>[
          <String, Object?>{
            'id': 'p1',
            'name': '测试 POI',
            'latitude': 39.9,
            'longitude': 116.4,
          },
        ],
      });

      final slice = await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(),
      );

      expect(slice.items, hasLength(1));
      expect(slice.items.single.name, '测试 POI');
    });

    test('name 为空的条目被 strict decoder 整体拒绝', () async {
      final adapter = _adapter(<String, dynamic>{
        'items': <Object?>[
          <String, dynamic>{'name': '', 'latitude': 0, 'longitude': 0},
          <String, dynamic>{
            'id': 'p2',
            'name': '保留',
            'latitude': 1,
            'longitude': 2,
          },
        ],
      });

      await expectLater(
        adapter.searchLocations(const LocationSearchQueryParams(query: '保留')),
        throwsFormatException,
      );
    });

    test('响应根缺失 items 时 strict decoder 拒绝', () async {
      final adapter = _adapter(<String, dynamic>{});

      await expectLater(
        adapter.getNearbyLocations(const NearbyLocationQueryParams()),
        throwsFormatException,
      );
    });
  });
}
