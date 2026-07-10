import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_structured_run_response_read_view.dart';

void main() {
  test('AssistantStructuredRunResponseReadView reads session and UI lists', () {
    final v = AssistantStructuredRunResponseReadView(<String, dynamic>{
      'effectiveSessionId': ' s1 ',
      'activeTopicTitle': ' T ',
      'dialogueRuntime': <String, dynamic>{'k': 1},
      'uiReferences': <dynamic>[
        <String, dynamic>{'url': 'https://a'},
      ],
      'uiActions': <dynamic>[
        <String, dynamic>{'id': 'x'},
      ],
      'uiUsageStats': <String, dynamic>{'tokens': 1},
      'templateVersionUsed': ' v2 ',
      'qualityMetrics': <String, dynamic>{'heuristicFallbackUsed': true},
    });
    expect(v.effectiveSessionIdOrEmpty, 's1');
    expect(v.activeTopicTitleOrNull, 'T');
    expect(v.dialogueRuntime['k'], 1);
    expect(v.uiReferences.length, 1);
    expect(v.uiActions.length, 1);
    expect(v.uiUsageStats['tokens'], 1);
    expect(v.templateVersionUsedOrEmpty, 'v2');
    expect(v.heuristicFallbackUsedFromQualityMetrics, isTrue);
  });
}
