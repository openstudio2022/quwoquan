import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';

void main() {
  test('assistantJsonAsStringKeyedMap normalizes Map keys to String', () {
    final m = assistantJsonAsStringKeyedMap(<dynamic, dynamic>{1: 'a'});
    expect(m, <String, dynamic>{'1': 'a'});
    expect(assistantJsonAsStringKeyedMap('x'), isNull);
  });
}
