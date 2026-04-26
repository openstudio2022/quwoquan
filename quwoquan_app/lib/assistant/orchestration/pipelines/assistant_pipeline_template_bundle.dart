import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

class AssistantPipelineTemplateBundle {
  const AssistantPipelineTemplateBundle({
    required this.request,
    required this.contextAssembly,
    required this.domainId,
    required this.domainSkillInstruction,
    required this.domainSkillName,
    required this.availableToolNames,
    required this.toolGuidelines,
    required this.conversationSpine,
    required this.searchIterationState,
    required this.temporalReference,
    required this.calendarContext,
    required this.dialogueRoundScript,
    required this.skillExecutionShell,
    required this.skillPersona,
    required this.skillCatalog,
    required this.previousSlotState,
    required this.previousDomainPolicyBundle,
    required this.planView,
    required this.searchPlans,
    required this.answerBoundaryPolicy,
    required this.previousAnswerSummary,
    required this.continuityPolicy,
    required this.continuityOverrideSlots,
  });

  final AssistantRunRequest request;
  final ContextAssemblyResult contextAssembly;
  final String domainId;
  final String domainSkillInstruction;
  final String domainSkillName;
  final List<String> availableToolNames;
  final List<Map<String, dynamic>> toolGuidelines;
  final Map<String, dynamic> conversationSpine;
  final SearchIterationState searchIterationState;
  final TemporalReferenceContext temporalReference;
  final Map<String, dynamic> calendarContext;
  final DialogueRoundScript dialogueRoundScript;
  final SkillExecutionShell skillExecutionShell;
  final String skillPersona;
  final String skillCatalog;
  final SlotStateSnapshot previousSlotState;
  final DomainPolicyBundle? previousDomainPolicyBundle;
  final AssistantPlanView planView;
  final List<SearchPlanItem> searchPlans;
  final AnswerBoundaryPolicy answerBoundaryPolicy;
  final String previousAnswerSummary;
  final ContextContinuityPolicy continuityPolicy;
  final Map<String, dynamic> continuityOverrideSlots;
}
