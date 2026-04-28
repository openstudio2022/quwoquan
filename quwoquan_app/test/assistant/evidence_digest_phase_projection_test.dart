import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/evidence_digest_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:test/test.dart';

void main() {
  test('EvidenceDigestPhase consumes typed execution snapshot', () async {
    final phase = const EvidenceDigestPhase();
    const toolResults = <AssistantToolResultRow>[
      AssistantToolResultRow(
        toolName: 'web_search',
        toolCallId: 'call_search',
        message: 'ok',
        data: <String, dynamic>{
          'summary': 'stale trace-derived summary',
          'candidateCount': 12,
          'totalReferences': 4,
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '最新快讯',
              'url': 'https://example.com/latest',
              'source': 'example.com',
              'snippet': '最新资料显示天气变化。',
            },
          ],
        },
      ),
    ];
    final output = await phase.run(
      PhaseInput(
        request: const AssistantRunRequest(
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '最新天气怎么样'),
          ],
        ),
        state: AgentExecutionState(
          executionPhaseSnapshot: ExecutionPhaseSuccess(
            runId: 'run_digest_projection',
            traceId: 'trace_digest_projection',
            runStartAt: DateTime(2026, 4, 26),
            sessionId: 'digest_projection',
            latestUserQuery: '最新天气怎么样',
            domainId: 'weather',
            contextAssembly: ContextAssemblyResult(),
            understandingResult: UnderstandingResult(),
            taskGraph: TaskGraph(),
            orchestratorState: ConversationOrchestratorState(),
            turnSynthesisState: TurnSynthesisState(),
            dialogueRoundScript: DialogueRoundScript(),
            domainCatalog: <String>[],
            domainCatalogVersion: '',
            allowedToolNames: <String>['web_search'],
            executionShell: SkillExecutionShell(),
            previousSlotState: SlotStateSnapshot(),
            retrievalPolicy: <String, dynamic>{},
            answerBoundaryPolicy: AnswerBoundaryPolicy(
              evidenceRequired: true,
              freshnessHoursMax: 6,
            ),
            understandingSnapshot: <String, dynamic>{},
            templateVariables: <String, dynamic>{},
            messages: <Map<String, dynamic>>[],
            synthTemplateVersion: '',
            fusionSynthTemplateVersion: '',
            phaseOneResult: ReactRuntimeResult(finalText: '', traces: []),
            synthesisReadiness: SynthesisReadinessResult(
              ready: false,
              reason: 'fallback reason',
            ),
            evidenceLedger: <EvidenceLedgerEntry>[],
            evidenceEvaluation: EvidenceEvaluationResult(),
            toolResults: toolResults,
            supplementalTraces: <AssistantTraceEvent>[],
          ),
        ),
        runId: 'run_digest_projection',
        traceId: 'trace_digest_projection',
      ),
    );

    final nextState = output.state;
    expect(nextState, isNotNull);
    expect(nextState!.executionPhaseSnapshot, isA<ExecutionPhaseSuccess>());
    expect(nextState.retrievalProcessing.searchedDocumentCount, 12);
    expect(nextState.retrievalProcessing.processedDocumentCount, 4);
    expect(nextState.retrievalProcessing.acceptedDocumentCount, 1);
    expect(
      nextState.retrievalProcessing.acceptedReferences.single.url,
      'https://example.com/latest',
    );
  });
}
