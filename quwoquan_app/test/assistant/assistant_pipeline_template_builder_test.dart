import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_prompt_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_precomputed_contracts.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_synthesis_template_bundle.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_builder.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_variables_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_session_history_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantPipelineTemplateBuilder', () {
    test('buildPlannerTemplateVariables only emits planner contract keys', () {
      final vars = buildPlannerTemplateVariables(
        userQuery: '深圳明天有雨吗',
        skillCatalog: 'weather',
        conversationSpineJson: '{"topic":"weather"}',
        sharedContextJson: '{"context":1}',
        currentRuntimeStateJson: '{"runtime":2}',
        dialogueContinuityJson: '{"continuity":"fresh_topic"}',
        recentDialogueRoundsJson: '[{"turn":1}]',
        searchIterationStateJson: '{"round":1}',
      );

      expect(
        vars.keys.toSet(),
        equals(
          <String>{
            AssistantPipelinePromptKeys.userQuery,
            AssistantPipelinePromptKeys.conversationSpine,
            AssistantPipelinePromptKeys.skillCatalog,
            AssistantPipelinePromptKeys.sharedContext,
            AssistantPipelinePromptKeys.currentRuntimeState,
            AssistantPipelinePromptKeys.dialogueContinuity,
            AssistantPipelinePromptKeys.recentDialogueRounds,
            AssistantPipelinePromptKeys.searchIterationState,
            AssistantPipelinePromptKeys.continuityMode,
            AssistantPipelineStateKeys.problemClass,
          },
        ),
      );
      expect(vars[AssistantPipelinePromptKeys.recentDialogueRounds], contains('turn'));
      expect(vars.containsKey('availableTools'), isFalse);
      expect(vars.containsKey('toolInvocationGuidelines'), isFalse);
      expect(vars.containsKey('skillPersona'), isFalse);
    });

    test('template variables view parses recent dialogue rounds canonically', () {
      final view = AssistantPipelineTemplateVariablesView.fromMap(
        <String, dynamic>{
          AssistantPipelinePromptKeys.recentDialogueRounds:
              '[{"turnId":"turn_3","userQuery":"第三问"}]',
        },
      );

      expect(view.recentDialogueRounds, hasLength(1));
      expect(view.recentDialogueRounds.first['turnId'], 'turn_3');
      expect(view.recentDialogueRounds.first['userQuery'], '第三问');
    });

    test('buildSynthesisTemplateVariables serializes bundle fields', () {
      final bundle = AssistantPipelineSynthesisTemplateBundle(
        templateVariables: <String, dynamic>{'base': 'value'},
        conversationSpine: <String, dynamic>{'topic': 'weather'},
        userGoal: '查天气',
        understandingSnapshot: <String, dynamic>{'ok': true},
        retrievalProcessing: <String, dynamic>{'summary': 'done'},
        sharedContext: <String, dynamic>{'context': 1},
        currentRuntimeState: <String, dynamic>{'runtime': 2},
        dialogueContinuity: <String, dynamic>{'continuity': 3},
        evidenceContext: <String, dynamic>{'evidence': 4},
        searchIterationState: <String, dynamic>{'round': 1},
        intentGraphJson: '{"goal":"weather"}',
        queryTasksJson: <Map<String, dynamic>>[
          <String, dynamic>{'id': 'q1'},
        ],
        entityAnchors: const <String>['深圳'],
        queryTasks: <Map<String, dynamic>>[
          <String, dynamic>{'id': 'q1'},
        ],
        answerShape: 'general',
        recentDialogueRounds: <Map<String, dynamic>>[
          <String, dynamic>{'turn': 1},
        ],
      );

      final vars = buildSynthesisTemplateVariables(bundle: bundle);

      expect(vars['base'], 'value');
      expect(vars[AssistantPipelineStateKeys.userGoal], '查天气');
      expect(vars['conversationSpine'], contains('weather'));
      expect(
        vars[AssistantPipelinePromptKeys.recentDialogueRounds],
        contains('turn'),
      );
    });

    test('buildFusionTemplateVariables layers fusion payloads', () {
      final bundle = AssistantPipelineSynthesisTemplateBundle(
        templateVariables: <String, dynamic>{'base': 'value'},
        conversationSpine: <String, dynamic>{},
        userGoal: 'goal',
        understandingSnapshot: const <String, dynamic>{},
        retrievalProcessing: const <String, dynamic>{},
        sharedContext: const <String, dynamic>{},
        currentRuntimeState: const <String, dynamic>{},
        dialogueContinuity: const <String, dynamic>{},
        evidenceContext: const <String, dynamic>{},
        searchIterationState: const <String, dynamic>{},
        intentGraphJson: '{}',
        queryTasksJson: const <Map<String, dynamic>>[],
        entityAnchors: const <String>[],
        queryTasks: const <Map<String, dynamic>>[],
        answerShape: 'general',
        recentDialogueRounds: const <Map<String, dynamic>>[],
      );

      final vars = buildFusionTemplateVariables(
        bundle: bundle,
        skillRuns: <Map<String, dynamic>>[
          <String, dynamic>{'skill': 's1'},
        ],
        aggregationState: <String, dynamic>{'state': 'ok'},
        subagentRuns: <Map<String, dynamic>>[
          <String, dynamic>{'run': 'r1'},
        ],
        skillSynthesis: <String, dynamic>{
          'input': <String, dynamic>{'userQuery': 'goal'},
          'output': <String, dynamic>{'answerMarkdown': 'answer'},
        },
      );

      expect(vars['base'], 'value');
      expect(vars[AssistantPipelinePromptKeys.skillRuns], contains('s1'));
      expect(
        vars[AssistantPipelinePromptKeys.aggregationState],
        contains('state'),
      );
      expect(vars[AssistantPipelinePromptKeys.subagentRuns], contains('r1'));
      expect(vars[AssistantPipelinePromptKeys.skillSynthesis], contains('answer'));
    });

    test('compatibility context preserves session history state', () {
      final request = AssistantRunRequest(
        sessionId: 'history_state_session',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '我想继续上次的问题'),
        ],
      );
      final state = AgentExecutionState(
        bootstrapContext: AssistantBootstrapContext(
          sessionId: 'history_state_session',
          latestUserQuery: '我想继续上次的问题',
          sessionHistoryState: const AssistantSessionHistoryState(
            sessionSummary: '上次已经完成了天气结论。',
            completedSkillSummaries: <AssistantSkillHistorySummary>[
              AssistantSkillHistorySummary(
                skillId: 'weather',
                role: 'primary',
                summary: '已确认深圳天气适合出行。',
                answerReady: true,
                acceptedEvidenceCount: 2,
              ),
            ],
          ),
        ),
      );

      final context = buildCompatibilityContextScopeHint(
        request: request,
        state: state,
      );
      final recovered = recoverPrecomputedBootstrap(context);

      expect(recovered, isNotNull);
      expect(recovered!.sessionHistoryState.sessionSummary, '上次已经完成了天气结论。');
      expect(
        recovered.sessionHistoryState.completedSkillSummaries,
        hasLength(1),
      );
      expect(
        recovered.sessionHistoryState.completedSkillSummaries.single.skillId,
        'weather',
      );
    });

    test('sanitizeModelTemplateContext strips ui-only fields', () {
      final sanitized = sanitizeModelTemplateContext(
        <String, dynamic>{
          AssistantPipelineStateKeys.runArtifacts: <String, dynamic>{'bad': true},
          AssistantPipelineStateKeys.previousRunArtifacts:
              <String, dynamic>{'older': true},
          AssistantPipelineStateKeys.machineEnvelope: <String, dynamic>{'ui': true},
          AssistantPipelineStateKeys.displayMarkdown: 'render me',
          AssistantPipelineStateKeys.journey: <String, dynamic>{'stage': 'answer'},
          AssistantPipelineStateKeys.dialogueState:
              <String, dynamic>{'step': 'keep?'},
          AssistantPipelineStateKeys.currentStateId: 'answering',
          'domain': 'assistant',
        },
        continuationActive: false,
      );

      expect(sanitized.containsKey(AssistantPipelineStateKeys.runArtifacts), isFalse);
      expect(
        sanitized.containsKey(AssistantPipelineStateKeys.previousRunArtifacts),
        isFalse,
      );
      expect(sanitized.containsKey(AssistantPipelineStateKeys.machineEnvelope), isFalse);
      expect(sanitized.containsKey(AssistantPipelineStateKeys.displayMarkdown), isFalse);
      expect(sanitized.containsKey(AssistantPipelineStateKeys.journey), isFalse);
      expect(sanitized.containsKey(AssistantPipelineStateKeys.dialogueState), isFalse);
      expect(
        sanitized.containsKey(AssistantPipelineStateKeys.currentStateId),
        isFalse,
      );
      expect(sanitized['domain'], 'assistant');
    });

    test('AssistantBootstrapContext prefers recent dialogue rounds summary', () {
      final bootstrap = AssistantBootstrapContext(
        historySummary: 'old summary',
        recentDialogueRounds: <Map<String, dynamic>>[
          <String, dynamic>{
            'userQuery': '第一轮问题',
            'assistantSummary': '第一轮回答',
            'understandingSnapshot': <String, dynamic>{
              'userFacingSummary': '第一轮理解',
            },
          },
        ],
      );

      expect(bootstrap.compactHistorySummary, contains('第一轮问题'));
      expect(bootstrap.compactHistorySummary, isNot(contains('old summary')));
    });
  });
}
