import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/evidence_digest_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:test/test.dart';

void main() {
  test('EvidenceDigestPhase 优先投影 canonical retrieval outcome', () async {
    const canonicalOutcome = RetrievalOutcome(
      status: 'need_more_evidence',
      summary: '资料时效不足，需要补更新来源。',
      evidenceRequired: true,
      freshnessRequired: true,
      retrievalProcessing: RetrievalProcessingSnapshot(
        processedDocumentCount: 4,
        acceptedDocumentCount: 1,
        processingSummary: 'canonical summary should win',
        acceptedReferences: <RetrievalProcessingReference>[
          RetrievalProcessingReference(
            title: '最新快讯',
            url: 'https://example.com/latest',
            source: 'example.com',
            snippet: '最新资料',
          ),
        ],
      ),
    );

    final phase = const EvidenceDigestPhase();
    final output = await phase.run(
      PhaseInput(
        request: const AssistantRunRequest(
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '最新天气怎么样'),
          ],
        ),
        state: const AgentExecutionState(
          executionBridgeSnapshot: <String, dynamic>{
            'phaseOneResult': ReactRuntimeResult(finalText: '', traces: []),
            'synthesisReadiness': SynthesisReadinessResult(
              ready: false,
              reason: 'fallback reason',
            ),
            'answerBoundaryPolicy': AnswerBoundaryPolicy(
              evidenceRequired: true,
              freshnessHoursMax: 6,
            ),
            assistantRetrievalOutcomeField: canonicalOutcome,
            'toolResults': <Map<String, dynamic>>[
              <String, dynamic>{
                'data': <String, dynamic>{
                  'summary': 'stale trace-derived summary',
                  'totalReferences': 99,
                },
              },
            ],
          },
        ),
        runId: 'run_digest_projection',
        traceId: 'trace_digest_projection',
      ),
    );

    final nextState = output.state;
    expect(nextState, isNotNull);
    expect(
      nextState!.retrievalProcessing.processingSummary,
      contains('资料时效不足，需要补更新来源。'),
    );
    final updatedSnapshot = nextState.executionBridgeSnapshot;
    final canonicalJson =
        (updatedSnapshot[assistantRetrievalOutcomeField] as Map?)?.cast<String, dynamic>();
    expect(canonicalJson, isNotNull);
    expect(canonicalJson!['status'], 'need_more_evidence');
    expect(canonicalJson['summary'], '资料时效不足，需要补更新来源。');
  });
}
