import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';

void main() {
  group('assistant contracts roundtrip', () {
    test('SystemContextEnvelope round-trips with default injection fields', () {
      const envelope = SystemContextEnvelope(
        time: SystemTimeContext(
          referenceNowIso: '2026-04-21T08:00:00Z',
          timezone: 'Asia/Shanghai',
          locale: 'zh-CN',
        ),
        device: DeviceSummary(
          os: 'ios',
          model: 'iPhone17,1',
          appVersion: '1.0.0',
        ),
        permissions: PermissionSummary(
          locationGranted: true,
          cameraGranted: true,
          notificationsGranted: true,
        ),
        location: SystemLocationContext(
          countryCode: 'CN',
          countryName: 'China',
          adminAreaLevel1: 'Guangdong',
          adminAreaLevel2: 'Shenzhen',
          formattedAddress: 'Guangdong Shenzhen',
          timezone: 'Asia/Shanghai',
          granularity: LocationGranularity.city,
        ),
      );

      final decoded = SystemContextEnvelope.fromJson(envelope.toJson());

      expect(decoded.contractId, 'system_context_envelope');
      expect(decoded.time.referenceNowIso, '2026-04-21T08:00:00Z');
      expect(decoded.time.timezone, 'Asia/Shanghai');
      expect(decoded.time.locale, 'zh-CN');
      expect(decoded.device.model, 'iPhone17,1');
      expect(decoded.permissions.locationGranted, isTrue);
      expect(decoded.location.countryCode, 'CN');
      expect(decoded.location.adminAreaLevel1, 'Guangdong');
      expect(decoded.location.adminAreaLevel2, 'Shenzhen');
      expect(decoded.location.granularity, LocationGranularity.city);
    });

    test('UnderstandingResult round-trips multi-intent payload', () {
      const result = UnderstandingResult(
        intents: <IntentNode>[
          IntentNode(
            intentId: 'intent_weather',
            intentType: 'weather.retrieve',
            goal: '查询今天深圳天气',
            entityRefs: <IntentEntityRef>[
              IntentEntityRef(
                entityType: 'city',
                canonicalKey: 'city:shenzhen',
                displayText: '深圳',
              ),
            ],
            constraints: <IntentConstraint>[
              IntentConstraint(key: 'time', value: 'today'),
            ],
            requiresEvidence: true,
          ),
          IntentNode(
            intentId: 'intent_clothing',
            intentType: 'clothing.recommend',
            goal: '推荐出门穿衣',
            requiresEvidence: false,
          ),
        ],
        dialogueTransitionDecision: DialogueTransitionDecision(
          nextTurnMode: NextTurnMode.continueExecution,
          canAnswerPartially: true,
        ),
      );

      final decoded = UnderstandingResult.fromJson(result.toJson());

      expect(decoded.contractId, 'understanding_result');
      expect(decoded.intents, hasLength(2));
      expect(decoded.intents.first.intentType, 'weather.retrieve');
      expect(
        decoded.dialogueTransitionDecision.nextTurnMode,
        NextTurnMode.continueExecution,
      );
      expect(decoded.dialogueTransitionDecision.canAnswerPartially, isTrue);
    });

    test('TaskGraph round-trips typed task nodes', () {
      const graph = TaskGraph(
        tasks: <TaskNode>[
          TaskNode(
            taskId: 'task_search',
            intentId: 'intent_weather',
            toolName: 'web_search',
            toolArgs: TaskToolArgs(<String, Object?>{'query': '深圳 今天天气'}),
            status: TaskStatus.inProgress,
            output: TaskOutput(<String, Object?>{'provider': 'serpapi'}),
          ),
          TaskNode(
            taskId: 'task_answer',
            intentId: 'intent_weather',
            toolName: 'app_action',
            status: TaskStatus.pending,
          ),
        ],
      );

      final decoded = TaskGraph.fromJson(graph.toJson());

      expect(decoded.contractId, 'task_graph');
      expect(decoded.tasks, hasLength(2));
      expect(decoded.tasks.first.toolName, 'web_search');
      expect(decoded.tasks.first.toolArgs.fields['query'], '深圳 今天天气');
      expect(decoded.tasks.first.status, TaskStatus.inProgress);
      expect(decoded.tasks.first.output.fields['provider'], 'serpapi');
      expect(decoded.tasks.last.toolName, 'app_action');
    });

    test('orchestrator and synthesis states round-trip interaction directive', () {
      const orchestratorState = ConversationOrchestratorState(
        completedTaskIds: <String>['task_bootstrap'],
        currentBatchTaskIds: <String>['task_search', 'task_history'],
        pendingTaskBatches: <List<String>>[
          <String>['task_answer'],
          <String>['task_finalize'],
        ],
        interactionDirective: InteractionDirective(
          kind: InteractionDirectiveKind.clarify,
          intentId: 'intent_missing_city',
          message: '请补充城市信息',
        ),
      );
      const synthesisState = TurnSynthesisState(
        interactionDirective: InteractionDirective(
          kind: InteractionDirectiveKind.partialAnswer,
          intentId: 'intent_weather',
          message: '先给出已确认部分',
        ),
        completedIntentIds: <String>['intent_weather'],
        remainingIntentIds: <String>['intent_clothing'],
        blockedIntentIds: <String>['intent_booking'],
      );

      final decodedOrchestrator = ConversationOrchestratorState.fromJson(
        orchestratorState.toJson(),
      );
      final decodedSynthesis = TurnSynthesisState.fromJson(
        synthesisState.toJson(),
      );

      expect(
        decodedOrchestrator.interactionDirective.kind,
        InteractionDirectiveKind.clarify,
      );
      expect(
        decodedOrchestrator.currentBatchTaskIds,
        <String>['task_search', 'task_history'],
      );
      expect(
        decodedOrchestrator.pendingTaskBatches,
        <List<String>>[
          <String>['task_answer'],
          <String>['task_finalize'],
        ],
      );
      expect(
        decodedSynthesis.interactionDirective.kind,
        InteractionDirectiveKind.partialAnswer,
      );
      expect(decodedSynthesis.completedIntentIds, <String>['intent_weather']);
    });
  });

  group('assistant execution state typed placeholders', () {
    test('AgentExecutionState carries new typed placeholders', () {
      const systemContext = SystemContextEnvelope(
        time: SystemTimeContext(
          referenceNowIso: '2026-04-21T08:00:00Z',
          timezone: 'Asia/Shanghai',
          locale: 'zh-CN',
        ),
        location: SystemLocationContext(adminAreaLevel2: 'Shenzhen'),
      );
      const understandingResult = UnderstandingResult(
        intents: <IntentNode>[
          IntentNode(
            intentId: 'intent_1',
            intentType: 'weather.retrieve',
            goal: '查询天气',
          ),
        ],
      );
      const taskGraph = TaskGraph(
        tasks: <TaskNode>[
          TaskNode(
            taskId: 'task_1',
            intentId: 'intent_1',
          ),
        ],
      );
      const orchestratorState = ConversationOrchestratorState(
        currentBatchTaskIds: <String>['task_1'],
      );
      const synthesisState = TurnSynthesisState(
        completedIntentIds: <String>['intent_1'],
      );

      final bootstrapContext = const AssistantBootstrapContext().copyWith(
        systemContextEnvelope: systemContext,
      );
      final state = const AgentExecutionState().copyWith(
        bootstrapContext: bootstrapContext,
        systemContextEnvelope: systemContext,
        understandingResult: understandingResult,
        taskGraph: taskGraph,
        orchestratorState: orchestratorState,
        turnSynthesisState: synthesisState,
      );

      expect(
        state.bootstrapContext?.systemContextEnvelope.location.adminAreaLevel2,
        'Shenzhen',
      );
      expect(state.systemContextEnvelope.time.timezone, 'Asia/Shanghai');
      expect(state.understandingResult.intents.single.intentId, 'intent_1');
      expect(state.taskGraph.tasks.single.taskId, 'task_1');
      expect(state.orchestratorState.currentBatchTaskIds, <String>['task_1']);
      expect(state.turnSynthesisState.completedIntentIds, <String>['intent_1']);
    });
  });
}
