import 'package:quwoquan_app/assistant/reasoning/planner/aggregation_gate.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/conversation_state_kernel.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/baseline_kernel.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/answer_gate_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

/// Shared dependencies for all pipeline stages.
///
/// Bundles the runtime, infrastructure, and domain services used by
/// [ExecutionPipeline], [SynthesisPipeline], and [ResponseMaterializer].
/// Fields are intentionally public to allow pipeline classes in separate files
/// to access them (Dart private is file-scoped).
class PipelineDeps {
  PipelineDeps({
    required this.runtime,
    required this.sessionManager,
    required this.memoryRepository,
    this.toolMetadataRegistry,
    PersonalAssistantContextOrchestrator? contextOrchestrator,
    DialogueStateRuntime? dialogueStateRuntime,
    AssistantDomainRouter? domainRouter,
    TemplateCatalogRuntime? templateCatalogRuntime,
    PersonalAssistantSkillLoader? skillLoader,
    PersonalAssistantSkillRouter? skillRouter,
    RecallCoordinator? recallCoordinator,
    ModeDecider? modeDecider,
    AggregationGate? aggregationGate,
    BaselineKernel? baselineKernel,
    AnswerBoundaryResolver? answerBoundaryResolver,
    ConversationStateKernel? conversationStateKernel,
  })  : contextOrchestrator =
            contextOrchestrator ?? const PersonalAssistantContextOrchestrator(),
        dialogueStateRuntime =
            dialogueStateRuntime ?? DialogueStateRuntime(),
        domainRouter = domainRouter ?? AssistantDomainRouter(),
        templateCatalogRuntime =
            templateCatalogRuntime ?? TemplateCatalogRuntime(),
        skillLoader = skillLoader ?? const PersonalAssistantSkillLoader(),
        skillRouter = skillRouter ?? const PersonalAssistantSkillRouter(),
        recallCoordinator = recallCoordinator ?? RecallCoordinator(),
        modeDecider = modeDecider ?? const ModeDecider(),
        aggregationGate = aggregationGate ?? const AggregationGate(),
        baselineKernel = baselineKernel ?? const BaselineKernel(),
        answerBoundaryResolver =
            answerBoundaryResolver ?? const AnswerBoundaryResolver(),
        conversationStateKernel =
            conversationStateKernel ?? const ConversationStateKernel();

  final ReactRuntime runtime;
  final AssistantSessionManager sessionManager;
  final AssistantMemoryRepository memoryRepository;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final PersonalAssistantContextOrchestrator contextOrchestrator;
  final DialogueStateRuntime dialogueStateRuntime;
  final AssistantDomainRouter domainRouter;
  final TemplateCatalogRuntime templateCatalogRuntime;
  final PersonalAssistantSkillLoader skillLoader;
  final PersonalAssistantSkillRouter skillRouter;
  final RecallCoordinator recallCoordinator;
  final ModeDecider modeDecider;
  final AggregationGate aggregationGate;
  final BaselineKernel baselineKernel;
  final AnswerBoundaryResolver answerBoundaryResolver;
  final ConversationStateKernel conversationStateKernel;
  final RetrievalOutcomeResolver retrievalOutcomeResolver =
      const RetrievalOutcomeResolver();
  final AnswerGateResolver answerGateResolver = const AnswerGateResolver();
}
