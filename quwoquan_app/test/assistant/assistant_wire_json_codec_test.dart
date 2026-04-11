import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_wire_json_codec.dart';

void main() {
  test('assistantDecodeJsonObjectBody maps object root', () {
    expect(
      assistantDecodeJsonObjectBody('  { "a": 1 } '),
      equals(<String, dynamic>{'a': 1}),
    );
  });

  test('assistantDecodeJsonObjectBody rejects non-object', () {
    expect(assistantDecodeJsonObjectBody('"x"'), isEmpty);
    expect(assistantDecodeJsonObjectBody('[1]'), isEmpty);
    expect(assistantDecodeJsonObjectBody(''), isEmpty);
  });
}
