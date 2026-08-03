import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ContractGraph 生成的 LocationPoi 是唯一 Cloud wire decoder。
void main() {
  const canonical = <String, Object?>{
    'id': 'poi-001',
    'name': '成都·天府广场',
    'latitude': 30.6586,
    'longitude': 104.0648,
    'address': '锦江区',
    'distanceMeters': 120,
  };

  test('generated decoder accepts canonical fields and round-trips', () {
    final slice = decodeLocationPoiListSlice(<String, Object?>{
      'items': <Object?>[canonical],
    });

    expect(slice.items.single.id, 'poi-001');
    expect(slice.items.single.latitude, closeTo(30.6586, 0.0001));
    expect(slice.toWire(), <String, Object?>{
      'items': <Object?>[canonical],
    });
  });

  test(
    'generated decoder rejects aliases, missing identity and unknown fields',
    () {
      expect(
        () => decodeLocationPoiListSlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              '_id': 'poi-001',
              'name': 'alias',
              'lat': 30.0,
              'lng': 104.0,
            },
          ],
        }),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => decodeLocationPoiListSlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{...canonical, 'distance': 120},
          ],
        }),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => decodeLocationPoiListSlice(const <String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'name': 'missing-id',
              'latitude': 30.0,
              'longitude': 104.0,
            },
          ],
        }),
        throwsA(isA<FormatException>()),
      );
    },
  );
}
