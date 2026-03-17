import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart'
    as legacy_agent;
import 'package:quwoquan_app/assistant/orchestration/phases/bootstrap_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/execution_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_orchestrator.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/retrieval_design_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';

class AssistantAgentLoop {
  factory AssistantAgentLoop({
    required ReactRuntime runtime,
    required AssistantSessionManager sessionManager,
    required AssistantMemoryRepository memoryRepository,
    ToolMetadataRegistry? toolMetadataRegistry,
  }) {
    final contextOrchestrator = const PersonalAssistantContextOrchestrator();
    final domainRouter = AssistantDomainRouter();
    final templateCatalogRuntime = TemplateCatalogRuntime();
    final recallCoordinator = RecallCoordinator();
    const skillLoader = PersonalAssistantSkillLoader();
    const skillRouter = PersonalAssistantSkillRouter();
    final delegate = legacy_agent.PersonalAssistantAgentLoop(
      runtime,
      sessionManager: sessionManager,
      memoryRepository: memoryRepository,
      toolMetadataRegistry: toolMetadataRegistry,
      contextOrchestrator: contextOrchestrator,
      domainRouter: domainRouter,
      templateCatalogRuntime: templateCatalogRuntime,
      recallCoordinator: recallCoordinator,
      skillLoader: skillLoader,
      skillRouter: skillRouter,
    );
    final orchestrator = PhaseOrchestrator(
      phases: [
        BootstrapPhase(
          runtime: runtime,
          sessionManager: sessionManager,
          memoryRepository: memoryRepository,
          contextOrchestrator: contextOrchestrator,
          templateCatalogRuntime: templateCatalogRuntime,
          domainRouter: domainRouter,
          recallCoordinator: recallCoordinator,
          toolMetadataRegistry: toolMetadataRegistry,
        ),
        UnderstandPhase(
          runtime: runtime,
          templateCatalogRuntime: templateCatalogRuntime,
        ),
        RetrievalDesignPhase(
          runtime: runtime,
          domainRouter: domainRouter,
          templateCatalogRuntime: templateCatalogRuntime,
          toolMetadataRegistry: toolMetadataRegistry,
          skillLoader: skillLoader,
          skillRouter: skillRouter,
        ),
        ExecutionPhase(delegate),
        SynthesisPhase(delegate),
        FinalizePhase(delegate),
      ],
    );
    return AssistantAgentLoop._(delegate: delegate, orchestrator: orchestrator);
  }

  AssistantAgentLoop._({
    required legacy_agent.PersonalAssistantAgentLoop delegate,
    required PhaseOrchestrator orchestrator,
  }) : _delegate = delegate,
       _orchestrator = orchestrator;

  final legacy_agent.PersonalAssistantAgentLoop _delegate;
  final PhaseOrchestrator _orchestrator;

  /// Unified execution state; owned by this loop. Legacy [PersonalAssistantAgentLoop]
  /// remains the implementation bridge until phases are fully migrated.
  AgentExecutionState get executionState => _executionState;
  AgentExecutionState _executionState = const AgentExecutionState();

  Future<AssistantRunResponse> run(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    _executionState = const AgentExecutionState();
    final runId =
        '${DateTime.now().millisecondsSinceEpoch}_${request.sessionId ?? 'default'}';
    final traceId = request.traceId ?? runId;
    final result = await _orchestrator.run(
      PhaseOrchestratorInput(
        request: request,
        runId: runId,
        traceId: traceId,
        initialState: _executionState,
        onTraceEvent: onTraceEvent == null
            ? null
            : (event) => onTraceEvent(
                AssistantTraceEvent.fromJson((event as dynamic).toJson()),
              ),
      ),
    );
    _executionState = result.state;
    final response = result.response;
    if (response == null) {
      return AssistantRunResponse(
        finalText: '',
        degraded: true,
        traces: const [],
      );
    }
    return AssistantRunResponse.fromJson((response as dynamic).toJson());
  }

  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) {
    return _delegate.classifyDomain(query, contextScopeHint);
  }

  Future<List<Map<String, dynamic>>> listSessions() async {
    final sessions = await _delegate.listSessions();
    return sessions
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    final detail = await _delegate.sessionDetail(sessionId);
    if (detail == null) return null;
    return Map<String, dynamic>.from(detail);
  }

  Future<void> switchSession(String sessionId) {
    return _delegate.switchSession(sessionId);
  }
}
