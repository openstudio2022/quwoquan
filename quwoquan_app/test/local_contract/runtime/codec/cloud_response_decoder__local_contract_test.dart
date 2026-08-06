import 'package:test/test.dart';
import 'package:quwoquan_app/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';

void main() {
  group('CloudResponseDecoder.mapList', () {
    test('解析 Map 与 Map<String,dynamic> 元素', () {
      final obj = <String, dynamic>{
        'items': <Object?>[
          <String, dynamic>{'a': 1},
          <String, Object?>{'b': 2},
        ],
      };
      final list = CloudResponseDecoder.mapList(obj, 'items');
      expect(list.length, 2);
      expect(list[0]['a'], 1);
      expect(list[1]['b'], 2);
    });

    test('缺 key 返回空列表，但非 List 或坏元素必须失败关闭', () {
      expect(
        CloudResponseDecoder.mapList(<String, dynamic>{}, 'items'),
        isEmpty,
      );
      expect(
        () => CloudResponseDecoder.mapList(<String, dynamic>{
          'items': 'x',
        }, 'items'),
        throwsA(isA<CloudException>()),
      );
      expect(
        () => CloudResponseDecoder.mapList(<String, dynamic>{
          'items': <Object?>[
            <String, dynamic>{'id': 'valid'},
            'bad',
          ],
        }, 'items'),
        throwsA(isA<CloudException>()),
      );
    });
  });

  group('CloudResponseDecoder.asObject', () {
    test('非 Map 时抛出 invalidResponse', () {
      expect(
        () => CloudResponseDecoder.asObject(<dynamic>[]),
        throwsA(
          isA<CloudException>().having(
            (e) => e.type,
            'type',
            CloudErrorType.invalidResponse,
          ),
        ),
      );
    });

    test('Map<dynamic, dynamic> 转为 Map<String, dynamic>', () {
      final m = <dynamic, dynamic>{'a': 1};
      final o = CloudResponseDecoder.asObject(m);
      expect(o['a'], 1);
    });
  });

  group('CloudResponseDecoder.mapList', () {
    test('只读单一 canonical items 键', () {
      final obj = <String, dynamic>{
        'items': <Map<String, dynamic>>[
          <String, dynamic>{'id': 'x'},
        ],
      };
      final list = CloudResponseDecoder.mapList(obj, 'items');
      expect(list.length, 1);
      expect(list.first['id'], 'x');
    });
  });

  test('CursorPage 含坏元素时不得静默裁剪', () {
    expect(
      () => CloudResponseDecoder.asCursorPage(<String, dynamic>{
        'items': <Object?>[
          <String, dynamic>{'id': 'valid'},
          1,
        ],
      }),
      throwsA(isA<CloudException>()),
    );
  });
}
