import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

void main() {
  group('UnderstandPhase', () {
    test('planner 输入会剥离上一轮 runArtifacts 噪音字段', () {
      final phase = UnderstandPhase();
      const request = AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: 'Shenzhen tian qi'),
        ],
        contextScopeHint: <String, dynamic>{
          'runArtifacts': <String, dynamic>{
            'displayMarkdown': '旧答案',
            'journey': <String, dynamic>{'summary': '旧过程'},
          },
          'previousRunArtifacts': <String, dynamic>{'displayPlainText': '旧纯文本'},
          'displayMarkdown': '旧 markdown',
          'displayPlainText': '旧 plain text',
          'journey': <String, dynamic>{'summary': '旧 journey'},
          'previousUnderstandingSnapshot': <String, dynamic>{
            'intentSummary': '旧理解',
          },
        },
      );

      final envelope = phase.inputSafeContextEnvelope(null, request, null);
      final scopeHint = (envelope['contextScopeHint'] as Map)
          .cast<String, dynamic>();

      expect(scopeHint.containsKey('runArtifacts'), isFalse);
      expect(scopeHint.containsKey('previousRunArtifacts'), isFalse);
      expect(scopeHint.containsKey('displayMarkdown'), isFalse);
      expect(scopeHint.containsKey('displayPlainText'), isFalse);
      expect(scopeHint.containsKey('journey'), isFalse);
      expect(
        scopeHint['previousUnderstandingSnapshot'],
        isA<Map<String, dynamic>>(),
      );
    });
  });
}
