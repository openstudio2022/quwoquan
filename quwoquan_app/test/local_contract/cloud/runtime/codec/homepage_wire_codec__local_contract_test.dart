import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/adapters/homepage_wire_codec.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';

void main() {
  group('HomepageWireCodec', () {
    test('缺省可选字段保持空值，但错误 wire 类型必须失败关闭', () {
      expect(HomepageWireCodec.stringKeyMapOrEmpty(null), isEmpty);
      expect(HomepageWireCodec.mapList<Object>(null, (_) => Object()), isEmpty);
      expect(HomepageWireCodec.optionalTrimmedString(null), isNull);
      expect(HomepageWireCodec.optionalDouble(null), isNull);
      expect(HomepageWireCodec.optionalDateTime(null), isNull);

      expect(
        () => HomepageWireCodec.stringKeyMapOrEmpty('not-an-object'),
        throwsA(isA<CloudException>()),
      );
      expect(
        () => HomepageWireCodec.mapList<Object>(<Object?>[
          <String, dynamic>{'id': 'valid'},
          'bad',
        ], (_) => Object()),
        throwsA(isA<CloudException>()),
      );
      expect(
        () => HomepageWireCodec.optionalDouble('1.0'),
        throwsA(isA<CloudException>()),
      );
      expect(
        () => HomepageWireCodec.optionalDateTime('not-a-date'),
        throwsA(isA<CloudException>()),
      );
    });
  });
}
