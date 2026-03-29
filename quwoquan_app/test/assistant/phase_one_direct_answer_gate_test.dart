import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/orchestration/phase_one_direct_answer_gate.dart';

void main() {
  group('PhaseOneDirectAnswerGate', () {
    const gate = PhaseOneDirectAnswerGate();
    const readiness = SynthesisReadinessResult(ready: true, reason: 'ok');

    test('execution signals 存在时不允许绕过 synthesis', () {
      const envelope = '''
{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","decision":{"nextAction":"answer"},"userMarkdown":"深圳今天晴。","result":{"text":"深圳今天晴。","summary":"深圳天气晴朗"}}
''';

      final decision = gate.evaluate(
        rawFinalText: envelope,
        synthesisReadiness: readiness,
        executionSignalsPresent: true,
      );

      expect(decision.shouldSkipSynthesis, isFalse);
      expect(decision.reason, 'execution_signals_require_synthesis');
    });

    test('契约字段不完整时不允许 direct answer', () {
      const incompleteEnvelope = '''
{"contractId":"assistant_turn","messageKind":"answer","decision":{"nextAction":"answer"},"userMarkdown":"我先帮你理清问题。","result":{"text":"我先帮你理清问题。","summary":"先理清问题"}}
''';

      final decision = gate.evaluate(
        rawFinalText: incompleteEnvelope,
        synthesisReadiness: readiness,
      );

      expect(decision.shouldSkipSynthesis, isFalse);
      expect(decision.reason, 'phase_one_contract_incomplete');
    });

    test('完整 answer contract 且无执行信号时允许 direct answer', () {
      const completeEnvelope = '''
{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","decision":{"nextAction":"answer"},"userMarkdown":"深圳今天晴，约 25°C。","result":{"text":"深圳今天晴，约25°C。","summary":"深圳天气晴朗"}}
''';

      final decision = gate.evaluate(
        rawFinalText: completeEnvelope,
        synthesisReadiness: readiness,
      );

      expect(decision.shouldSkipSynthesis, isTrue);
      expect(decision.reason, 'phase_one_direct_answer');
      expect(decision.normalizedEnvelopeText, isNotEmpty);
    });
  });
}
