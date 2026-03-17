import 'dart:math' as math;

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

class ExecutionPreparationResolver {
  const ExecutionPreparationResolver({
    required this.domainRouter,
    required this.templateCatalogRuntime,
    required this.skillLoader,
    required this.skillRouter,
    this.toolMetadataRegistry,
  });

  final AssistantDomainRouter domainRouter;
  final TemplateCatalogRuntime templateCatalogRuntime;
  final PersonalAssistantSkillLoader skillLoader;
  final PersonalAssistantSkillRouter skillRouter;
  final ToolMetadataRegistry? toolMetadataRegistry;

  Future<AssistantExecutionPreparation> resolve({
    required String domainId,
    required AssistantExecutionPreparation base,
    required String userQuery,
    required IntentGraph intentGraph,
    required AssistantRunRequest request,
    DialogueRoundScript? dialogueRoundScript,
    RunArtifacts? previousRunArtifacts,
    List<String> runtimeToolNames = const <String>[],
    bool preferExplicitDomain = false,
  }) async {
    final effectiveDomainId = domainId.trim().isNotEmpty
        ? domainId.trim()
        : (base.domainId.trim().isNotEmpty
              ? base.domainId.trim()
              : domainRouter.fallbackDomainId);
    final skillContext = await resolveSkillContext(
      domainId: effectiveDomainId,
      userQuery: userQuery,
      dialogueRoundScript: dialogueRoundScript,
      preferExplicitDomain: preferExplicitDomain,
    );
    final executionShell = resolveExecutionShellForRun(
      domainId: effectiveDomainId,
      baseShell: skillContext.executionShell,
      intentGraph: intentGraph,
      request: request,
    );
    final plannerTemplateVersion = templateCatalogRuntime.latestVersionFor(
      'planner.global_plan',
      fallback: '',
    );
    final postcheckTemplateVersion = templateCatalogRuntime.latestVersionFor(
      'planner.postcondition_check',
      fallback: plannerTemplateVersion,
    );
    final synthTemplateVersion = templateCatalogRuntime.latestVersionFor(
      'synthesizer.final_answer',
      fallback: plannerTemplateVersion,
    );
    final fusionSynthTemplateVersion = templateCatalogRuntime.latestVersionFor(
      'synthesizer.multi_skill_fusion',
      fallback: synthTemplateVersion,
    );
    final effectiveToolNames = resolveAvailableTools(
      domainId: effectiveDomainId,
      runtimeToolNames: runtimeToolNames,
      skillAllowedTools: skillContext.allowedTools,
    );
    final skillPersona = await loadSkillPersona(effectiveDomainId);
    final previousSlotState = recoverPreviousSlotState(
      fallbackDomainId: effectiveDomainId,
      runArtifacts: previousRunArtifacts,
    );
    final previousDomainPolicyBundle = recoverPreviousDomainPolicyBundle(
      runArtifacts: previousRunArtifacts,
    );
    return AssistantExecutionPreparation(
      domainId: effectiveDomainId,
      modeDecision: base.modeDecision,
      skillName: skillContext.skillName,
      skillInstructionMarkdown: skillContext.instructionMarkdown,
      skillPersona: skillPersona,
      allowedToolNames: effectiveToolNames,
      executionShell: executionShell,
      plannerTemplateVersion: plannerTemplateVersion,
      postcheckTemplateVersion: postcheckTemplateVersion,
      synthTemplateVersion: synthTemplateVersion,
      fusionSynthTemplateVersion: fusionSynthTemplateVersion,
      previousSlotState: previousSlotState,
      previousDomainPolicyBundle: previousDomainPolicyBundle,
    );
  }

  Future<ResolvedSkillContext> resolveSkillContext({
    required String domainId,
    required String userQuery,
    DialogueRoundScript? dialogueRoundScript,
    bool preferExplicitDomain = false,
  }) async {
    try {
      final skills = await skillLoader.loadBundledSkills();
      final globalPolicy = await loadGlobalPolicyMarkdown();
      if (skills.isEmpty) {
        if (globalPolicy.isEmpty) return const ResolvedSkillContext.empty();
        return ResolvedSkillContext(
          skillName: 'Global Policy',
          instructionMarkdown: globalPolicy,
          executionShell: const SkillExecutionShell(),
          allowedTools: const <String>[],
        );
      }
      final matched = skillRouter.resolveSkillForDomain(
        userText: userQuery,
        domainId: domainId,
        skills: skills,
      );
      final effectiveMatch = domainId == domainRouter.fallbackDomainId
          ? (preferExplicitDomain
                ? matched
                : (skillRouter.resolveSkill(userQuery, skills) ?? matched))
          : matched;
      if (effectiveMatch == null) {
        if (globalPolicy.isEmpty) return const ResolvedSkillContext.empty();
        return ResolvedSkillContext(
          skillName: 'Global Policy',
          instructionMarkdown: globalPolicy,
          executionShell: const SkillExecutionShell(),
          allowedTools: const <String>[],
        );
      }
      final skillPolicy = await loadSkillPolicyMarkdown(domainId);
      final phaseRefs = await loadPhaseAwareReferences(
        domainId: domainId,
        dialogueRoundScript: dialogueRoundScript,
      );
      final mergedInstruction = mergeSkillInstructions(
        globalPolicy: globalPolicy,
        baseSkillInstruction: effectiveMatch.skillInstructionMarkdown,
        skillPolicy: skillPolicy,
        phaseReferences: phaseRefs,
      );
      return ResolvedSkillContext(
        skillName: effectiveMatch.name,
        instructionMarkdown: mergedInstruction,
        executionShell: effectiveMatch.executionShell,
        allowedTools: effectiveMatch.allowedTools,
      );
    } catch (_) {
      return const ResolvedSkillContext.empty();
    }
  }

  SkillExecutionShell resolveExecutionShellForRun({
    required String domainId,
    required SkillExecutionShell baseShell,
    required IntentGraph intentGraph,
    required AssistantRunRequest request,
  }) {
    final rawProblemClass =
        intentGraph.isMultiSkill &&
            baseShell.problemClass.trim().isNotEmpty &&
            baseShell.problemClass.trim().toLowerCase() != 'general'
        ? baseShell.problemClass
        : intentGraph.problemClassWireName;
    return resolveExecutionShellForProblemClass(
      domainId: domainId,
      baseShell: baseShell,
      rawProblemClass: rawProblemClass,
      mode: (intentGraph.globalConstraints['mode'] as String?)?.trim() ?? '',
      secondarySkills: intentGraph.secondarySkills,
      queryText: request.messages.isNotEmpty
          ? request.messages.last.content
          : '',
    );
  }

  SkillExecutionShell resolveExecutionShellForProblemClass({
    required String domainId,
    required SkillExecutionShell baseShell,
    required String rawProblemClass,
    required String mode,
    required List<String> secondarySkills,
    required String queryText,
  }) {
    final adaptiveProblemClass = normalizeProblemClassForQuery(
      raw: rawProblemClass,
      primarySkill: domainId,
      mode: mode,
      secondarySkills: secondarySkills,
      queryText: queryText,
    );
    final isAdaptiveDomain =
        domainId.trim() == domainRouter.fallbackDomainId ||
        baseShell.problemClass.trim().toLowerCase() == 'general';
    if (!isAdaptiveDomain) {
      return adaptiveProblemClass == 'general'
          ? baseShell
          : baseShell.copyWith(problemClass: adaptiveProblemClass);
    }
    switch (adaptiveProblemClass) {
      case 'realtime_info':
        return baseShell.copyWith(
          problemClass: adaptiveProblemClass,
          maxIterations: math.min(baseShell.maxIterations, 2),
          toolBudget: math.min(baseShell.toolBudget, 1),
          variantBudget: 0,
          reflectionBudget: 0,
          freshnessHoursMax: math.min(baseShell.freshnessHoursMax, 6),
        );
      case 'task_execution':
        return baseShell.copyWith(
          problemClass: adaptiveProblemClass,
          maxIterations: math.min(baseShell.maxIterations, 3),
          toolBudget: math.min(baseShell.toolBudget, 1),
          variantBudget: 0,
          reflectionBudget: 0,
        );
      case 'complex_reasoning':
        return baseShell.copyWith(
          problemClass: adaptiveProblemClass,
          maxIterations: math.max(3, baseShell.maxIterations),
          toolBudget: math.max(2, baseShell.toolBudget),
          variantBudget: math.max(1, baseShell.variantBudget),
          reflectionBudget: math.max(1, baseShell.reflectionBudget),
        );
      case 'simple_qa':
        return baseShell.copyWith(
          problemClass: adaptiveProblemClass,
          maxIterations: math.min(baseShell.maxIterations, 2),
          toolBudget: math.min(baseShell.toolBudget, 1),
          variantBudget: 0,
          reflectionBudget: 0,
        );
      default:
        return baseShell.copyWith(problemClass: adaptiveProblemClass);
    }
  }

  String normalizeProblemClassForQuery({
    required String raw,
    required String primarySkill,
    required String mode,
    required List<String> secondarySkills,
    required String queryText,
  }) {
    final normalized = parseProblemClass(raw.trim()).wireName;
    return normalized.isNotEmpty ? normalized : ProblemClass.general.wireName;
  }

  List<String> resolveAvailableTools({
    required String domainId,
    required List<String> runtimeToolNames,
    List<String> skillAllowedTools = const <String>[],
  }) {
    final resolved = toolMetadataRegistry?.availableToolsForDomain(
      domainId: domainId,
      fallbackNames: runtimeToolNames,
    );
    final domainTools = resolved ?? runtimeToolNames;
    if (skillAllowedTools.isEmpty) return domainTools;
    final allowSet = skillAllowedTools.map((item) => item.trim()).toSet();
    final restricted = domainTools
        .where((item) => allowSet.contains(item.trim()))
        .toList(growable: false);
    if (restricted.isNotEmpty) return restricted;
    return runtimeToolNames
        .where((item) => allowSet.contains(item.trim()))
        .toList(growable: false);
  }

  Future<String> loadPhaseAwareReferences({
    required String domainId,
    DialogueRoundScript? dialogueRoundScript,
  }) async {
    if (domainId.trim().isEmpty) return '';

    final hasRequiredSlots =
        dialogueRoundScript != null &&
        dialogueRoundScript.requiredFieldsForNextState.isNotEmpty;
    final buffer = StringBuffer();
    final domainKnowledge = await loadReferenceFile(
      domainId: domainId,
      fileName: 'domain-knowledge.md',
    );
    if (domainKnowledge.isNotEmpty) {
      buffer.write('## 领域知识与约束\n\n');
      buffer.write(domainKnowledge);
    }
    if (hasRequiredSlots) {
      final toolGuidance = await loadReferenceFile(
        domainId: domainId,
        fileName: 'tool-call-guidance.md',
      );
      if (toolGuidance.isNotEmpty) {
        if (buffer.isNotEmpty) buffer.write('\n\n---\n\n');
        buffer.write('## 工具调用指引\n\n');
        buffer.write(toolGuidance);
      }
    }
    if (!hasRequiredSlots) {
      final outputExamples = await loadReferenceFile(
        domainId: domainId,
        fileName: 'output-examples.md',
      );
      if (outputExamples.isNotEmpty) {
        if (buffer.isNotEmpty) buffer.write('\n\n---\n\n');
        buffer.write('## 输出示例（Few-shot）\n\n');
        buffer.write(outputExamples);
      }
    }
    return buffer.toString();
  }

  Future<String> loadReferenceFile({
    required String domainId,
    required String fileName,
  }) async {
    final path =
        'assets/assistant/skills/${domainId.trim()}/references/$fileName';
    try {
      final text = await rootBundle.loadString(path);
      return text.trim();
    } catch (_) {
      return '';
    }
  }

  Future<String> loadGlobalPolicyMarkdown() async {
    const path = 'assets/assistant/prompts/global/stack.global_policy.md';
    try {
      final text = await rootBundle.loadString(path);
      return text.trim();
    } catch (_) {
      return '';
    }
  }

  Future<String> loadSkillPersona(String domainId) async {
    if (domainId.trim().isEmpty) return '';
    final policyText = await loadSkillPolicyMarkdown(domainId);
    if (policyText.isEmpty) return '';
    final lines = policyText.split('\n');
    final personaBuffer = StringBuffer();
    var inPersonaSection = false;
    for (final line in lines) {
      final lower = line.toLowerCase().trim();
      if (lower.startsWith('## ') &&
          (lower.contains('人设') ||
              lower.contains('persona') ||
              lower.contains('语气') ||
              lower.contains('tone') ||
              lower.contains('风格') ||
              lower.contains('style'))) {
        inPersonaSection = true;
        personaBuffer.writeln(line);
        continue;
      }
      if (lower.startsWith('## ') && inPersonaSection) {
        inPersonaSection = false;
      }
      if (inPersonaSection) {
        personaBuffer.writeln(line);
      }
    }
    final persona = personaBuffer.toString().trim();
    return persona.isNotEmpty ? persona : policyText;
  }

  Future<String> loadSkillPolicyMarkdown(String domainId) async {
    if (domainId.trim().isEmpty) return '';
    final path =
        'assets/assistant/skills/${domainId.trim()}/scripts/skill.policy.md';
    try {
      final text = await rootBundle.loadString(path);
      return text.trim();
    } catch (_) {
      return '';
    }
  }

  String mergeSkillInstructions({
    required String globalPolicy,
    required String baseSkillInstruction,
    required String skillPolicy,
    String phaseReferences = '',
  }) {
    final blocks = <String>[
      if (globalPolicy.trim().isNotEmpty) globalPolicy.trim(),
      if (baseSkillInstruction.trim().isNotEmpty) baseSkillInstruction.trim(),
      if (skillPolicy.trim().isNotEmpty) skillPolicy.trim(),
      if (phaseReferences.trim().isNotEmpty) phaseReferences.trim(),
    ];
    return blocks.join('\n\n---\n\n');
  }

  SlotStateSnapshot recoverPreviousSlotState({
    required String fallbackDomainId,
    RunArtifacts? runArtifacts,
  }) {
    final fromArtifacts = runArtifacts?.slotState;
    if (fromArtifacts != null &&
        (fromArtifacts.slotValues.isNotEmpty ||
            fromArtifacts.missingSlots.isNotEmpty)) {
      return fromArtifacts;
    }
    return SlotStateSnapshot(domainId: fallbackDomainId);
  }

  DomainPolicyBundle? recoverPreviousDomainPolicyBundle({
    RunArtifacts? runArtifacts,
  }) {
    final fromArtifacts = runArtifacts?.domainPolicyBundle;
    if (fromArtifacts != null &&
        (fromArtifacts.executionPolicy.isNotEmpty ||
            fromArtifacts.slotSchema.isNotEmpty ||
            fromArtifacts.dialoguePolicy.isNotEmpty ||
            fromArtifacts.retrievalPolicy.isNotEmpty)) {
      return fromArtifacts;
    }
    return null;
  }
}

class ResolvedSkillContext {
  const ResolvedSkillContext({
    required this.skillName,
    required this.instructionMarkdown,
    required this.executionShell,
    required this.allowedTools,
  });

  const ResolvedSkillContext.empty()
    : skillName = '',
      instructionMarkdown = '',
      executionShell = const SkillExecutionShell(),
      allowedTools = const <String>[];

  final String skillName;
  final String instructionMarkdown;
  final SkillExecutionShell executionShell;
  final List<String> allowedTools;
}
