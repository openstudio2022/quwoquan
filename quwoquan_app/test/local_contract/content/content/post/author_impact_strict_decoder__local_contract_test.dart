import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  final valid = <String, dynamic>{
    'helpType': 'decision',
    'action': 'like',
    'intersectionDimension': 'content',
    'tagRef': 'Topic/兴趣/旅行',
    'source': 'behavior',
    'count': 1,
    'primaryText': '有人通过你的内容关注了相关对象',
    'subtitleText': '',
    'impactId': 'impact-1',
    'primarySpans': const <Object?>[],
    'sampleVisuals': const <Object?>[],
    'actionHints': const <Object?>[],
    'evidenceSnapshotId': 'impact-1',
    'countObjectKind': '',
    'iconKey': 'decisionCompass',
    'freshAt': '2026-07-23T00:00:00Z',
    'timeBucket': 'all_time',
    'lifecycleState': 'active',
    // JSON numbers encoded from Go float64 may be integral.
    'previousStrength': 0,
    'strengthDelta': 0,
  };

  test('accepts integral JSON numbers for required doubles', () {
    final item = AuthorImpactItem.fromWire(valid);
    expect(item.previousStrength, 0.0);
    expect(item.strengthDelta, 0.0);
  });

  test(
    'rejects a broken successful response instead of creating an empty row',
    () {
      final malformed = Map<String, dynamic>.from(valid)..remove('primaryText');

      expect(
        () => AuthorImpactItem.fromWire(malformed),
        throwsA(isA<FormatException>()),
      );
    },
  );
}
