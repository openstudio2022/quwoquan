import 'package:test/test.dart';

/// 锁定 [local_phase_execution_owner] 等处对 `answerDecision` / `diagnostics`
/// 的 spread 合并语义：后写覆盖同键，且保留先写独有键。
void main() {
  test('decision map spread: later map wins on key collision', () {
    const existing = <String, dynamic>{'a': 1, 'b': 2};
    const incoming = <String, dynamic>{'b': 3, 'c': 4};
    final merged = <String, dynamic>{
      ...existing,
      ...incoming,
      'synthesisReady': true,
    };
    expect(merged['a'], 1);
    expect(merged['b'], 3);
    expect(merged['c'], 4);
    expect(merged['synthesisReady'], isTrue);
  });

  test('diagnostics spread: base diagnostics plus gated overlays', () {
    const diagnostics = <String, dynamic>{'base': 1, 'qualityGates': 'q0'};
    final merged = <String, dynamic>{
      ...diagnostics,
      'qualityGates': <String, dynamic>{'x': 1},
      'evidencePassed': true,
      'finalAnswerMode': 'full',
    };
    expect(merged['base'], 1);
    expect(merged['qualityGates'], isA<Map>());
    expect((merged['qualityGates'] as Map)['x'], 1);
    expect(merged['evidencePassed'], isTrue);
  });
}
