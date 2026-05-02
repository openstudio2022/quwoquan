import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/slot_value_codec.dart';

void main() {
  test('SlotValueCodec normalizes primitives', () {
    expect(SlotValueCodec.asTrimmedString('  a '), 'a');
    expect(SlotValueCodec.asTrimmedString(1), '1');
    expect(SlotValueCodec.asBool(true), isTrue);
    expect(SlotValueCodec.asBool('true'), isTrue);
    expect(SlotValueCodec.asInt('3'), 3);
    expect(SlotValueCodec.asDouble('2.5'), 2.5);
    final m = SlotValueCodec.asStringKeyedMap(<dynamic, dynamic>{1: 'x'});
    expect(m, <String, dynamic>{'1': 'x'});
  });

  test('displayForSlotMerge matches current toString trim', () {
    expect(SlotValueCodec.displayForSlotMerge(null), '');
    expect(SlotValueCodec.displayForSlotMerge('  x '), 'x');
    expect(SlotValueCodec.displayForSlotMerge(42), '42');
  });
}
