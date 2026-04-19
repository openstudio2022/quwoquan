import 'package:quwoquan_app/assistant/contracts/assistant_answer_payload_read_view.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_response_codec.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_prompt_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';

class AssistantPipelineSubagentPlanCodec
    with AssistantPipelineResponseCodecMixin {
  const AssistantPipelineSubagentPlanCodec();

  List<SubagentPlan> buildSkillRunPlans({
    required IntentGraph intentGraph,
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final explicitPlans = _buildExplicitSkillRunPlans(
      answerPayload: answerPayload,
      latestUserQuery: latestUserQuery,
      fallbackProblemClass: intentGraph.problemClassWireName,
      primaryDomainId: primaryDomainId,
    );
    if (explicitPlans.isNotEmpty) {
      return explicitPlans;
    }
    return _buildDerivedSkillRunPlansFromIntent(
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
      primaryDomainId: primaryDomainId,
    );
  }

  List<SubagentPlan> buildExplicitSkillRunPlans({
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String fallbackProblemClass,
    required String primaryDomainId,
  }) {
    return _buildExplicitSkillRunPlans(
      answerPayload: answerPayload,
      latestUserQuery: latestUserQuery,
      fallbackProblemClass: fallbackProblemClass,
      primaryDomainId: primaryDomainId,
    );
  }

  List<SubagentPlan> buildDerivedSkillRunPlansFromIntent({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    return _buildDerivedSkillRunPlansFromIntent(
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
      primaryDomainId: primaryDomainId,
    );
  }

  List<SubagentPlan> _buildExplicitSkillRunPlans({
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String fallbackProblemClass,
    required String primaryDomainId,
  }) {
    final existingPlans = AssistantAnswerPayloadReadView(
      answerPayload,
    ).subagentPlanMaps;
    if (existingPlans.isEmpty) return const <SubagentPlan>[];
    return existingPlans
        .where(
          (item) =>
              ((item[SubagentPlanFields.domainId] as String?)?.trim() ?? '')
                  .isNotEmpty &&
              ((item[SubagentPlanFields.domainId] as String?)?.trim() ?? '') !=
                  primaryDomainId,
        )
        .map(
          (item) => _normalizeSubagentPlan(
            plan: item,
            latestUserQuery: latestUserQuery,
            fallbackProblemClass: fallbackProblemClass,
          ),
        )
        .toList(growable: false);
  }

  List<SubagentPlan> _buildDerivedSkillRunPlansFromIntent({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final routeNarrative = _buildSkillRouteNarrative(
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
      primaryDomainId: primaryDomainId,
    );
    return intentGraph.secondarySkills
        .where(
          (item) => item.trim().isNotEmpty && item.trim() != primaryDomainId,
        )
        .map(
          (skillId) => _normalizeSubagentPlan(
            plan: <String, dynamic>{
              SubagentPlanFields.subagentId: 'skill_${skillId}_1',
              SubagentPlanFields.domainId: skillId,
              SubagentPlanFields.problemClass:
                  intentGraph.problemClassWireName.isNotEmpty
                  ? intentGraph.problemClassWireName
                  : ProblemClass.general.wireName,
              SubagentPlanFields.mode: 'qa',
              SubagentPlanFields.goal:
                  latestUserQuery.trim().isNotEmpty
                  ? latestUserQuery.trim()
                  : skillId,
              SubagentPlanFields.taskBrief: skillId,
              SubagentPlanFields.routeNarrative: routeNarrative,
              SubagentPlanFields.localContextSeed: _buildSkillLocalContextSeed(
                intentGraph: intentGraph,
                latestUserQuery: latestUserQuery,
                skillId: skillId,
                primaryDomainId: primaryDomainId,
              ),
              SubagentPlanFields.role: 'supporting',
              SubagentPlanFields.needClarify: intentGraph.clarificationNeeded,
              SubagentPlanFields.pendingClarifications: const <String>[],
              SubagentPlanFields.maxIterations: 2,
              SubagentPlanFields.toolBudget: 2,
              SubagentPlanFields.stopPolicy: StopPolicy.balanced.wireName,
              SubagentPlanFields.searchIntensity:
                  intentGraph.problemClass == ProblemClass.realtimeInfo
                  ? SearchIntensity.low.wireName
                  : SearchIntensity.medium.wireName,
            },
            latestUserQuery: latestUserQuery,
            fallbackProblemClass: intentGraph.problemClassWireName,
          ),
        )
        .toList(growable: false);
  }

  SubagentPlan _normalizeSubagentPlan({
    required Map<String, dynamic> plan,
    required String latestUserQuery,
    required String fallbackProblemClass,
  }) {
    final domainId = (plan[SubagentPlanFields.domainId] as String?)?.trim() ?? '';
    final goal = (plan[SubagentPlanFields.goal] as String?)?.trim() ?? '';
    final taskBrief =
        (plan[SubagentPlanFields.taskBrief] as String?)?.trim() ?? goal;
    final role =
        (plan[SubagentPlanFields.role] as String?)?.trim() ?? 'supporting';
    final routeNarrative =
        (plan[SubagentPlanFields.routeNarrative] as String?)?.trim() ??
        _defaultRouteNarrative(domainId);
    final localContextSeed =
        (plan[SubagentPlanFields.localContextSeed] as String?)?.trim() ??
        '';
    final mode = (plan[SubagentPlanFields.mode] as String?)?.trim() ?? 'qa';
    final rawProblemClass =
        (plan[SubagentPlanFields.problemClass] as String?)?.trim() ??
        fallbackProblemClass;
    return SubagentPlan.fromJson(<String, dynamic>{
      ...plan,
      SubagentPlanFields.domainId: domainId,
      SubagentPlanFields.goal: goal,
      SubagentPlanFields.taskBrief: taskBrief.isNotEmpty ? taskBrief : goal,
      SubagentPlanFields.role: role,
      SubagentPlanFields.routeNarrative:
          routeNarrative.isNotEmpty ? routeNarrative : _defaultRouteNarrative(domainId),
      SubagentPlanFields.localContextSeed: localContextSeed.isNotEmpty
          ? localContextSeed
          : _buildSkillLocalContextSeed(
              intentGraph: IntentGraph.fromJson(<String, dynamic>{
                AssistantPipelineStateKeys.userGoal:
                    goal.isNotEmpty ? goal : latestUserQuery,
                'primarySkill': domainId,
                'problemClass': rawProblemClass,
                'secondarySkills': const <String>[],
                AssistantPipelinePromptKeys.queryTasks:
                    const <Map<String, dynamic>>[],
              }),
              latestUserQuery: latestUserQuery,
              skillId: domainId,
              primaryDomainId: domainId,
            ),
      SubagentPlanFields.needClarify:
          plan[SubagentPlanFields.needClarify] == true,
      SubagentPlanFields.pendingClarifications: normalizeStringList(
        plan[SubagentPlanFields.pendingClarifications],
      ),
      SubagentPlanFields.mode: mode,
      SubagentPlanFields.problemClass: normalizeProblemClassForQuery(
        raw: rawProblemClass,
      ),
      SubagentPlanFields.stopPolicy:
          (plan[SubagentPlanFields.stopPolicy] as String?)?.trim() ??
          'balanced',
      SubagentPlanFields.searchIntensity:
          (plan[SubagentPlanFields.searchIntensity] as String?)?.trim() ??
          'medium',
      SubagentPlanFields.providerPolicy:
          (plan[SubagentPlanFields.providerPolicy] as String?)?.trim() ?? '',
      SubagentPlanFields.freshnessHoursMax: nonNegativeInt(
        plan[SubagentPlanFields.freshnessHoursMax],
        fallback: 0,
      ),
      SubagentPlanFields.answerThreshold: normalizedThreshold(
        plan[SubagentPlanFields.answerThreshold],
        fallback: 0.0,
      ),
      SubagentPlanFields.dependencies:
          normalizeStringList(plan[SubagentPlanFields.dependencies]),
    });
  }

  String _buildSkillRouteNarrative({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final secondarySkills = intentGraph.secondarySkills
        .where(
          (item) => item.trim().isNotEmpty && item.trim() != primaryDomainId,
        )
        .map((item) => item.trim())
        .toList(growable: false);
    if (secondarySkills.isEmpty) {
      return 'primary=$primaryDomainId; secondary=[]; query=${latestUserQuery.trim()}';
    }
    return 'primary=$primaryDomainId; secondary=${secondarySkills.join(',')}; '
        'query=${latestUserQuery.trim()}';
  }

  String _buildSkillLocalContextSeed({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    required String skillId,
    required String primaryDomainId,
  }) {
    final anchors = intentGraph.entityAnchors
        .where((item) => item.trim().isNotEmpty)
        .map((item) => item.trim())
        .toList(growable: false);
    final buffer = StringBuffer()
      ..write('query=')
      ..write(latestUserQuery.trim())
      ..write('; primary=')
      ..write(primaryDomainId)
      ..write('; skill=')
      ..write(skillId)
      ..write('; class=')
      ..write(intentGraph.problemClassWireName);
    if (anchors.isNotEmpty) {
      buffer.write('; anchors=');
      buffer.write(anchors.join('、'));
    }
    return buffer.toString();
  }

  String _defaultRouteNarrative(String domainId) {
    return 'primary=$domainId';
  }

  String normalizeProblemClassForQuery({
    required String raw,
  }) {
    final normalized = parseProblemClass(raw.trim()).wireName;
    return normalized.isNotEmpty ? normalized : ProblemClass.general.wireName;
  }

  int nonNegativeInt(Object? value, {required int fallback}) {
    if (value is int && value >= 0) return value;
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed >= 0) return parsed;
    return fallback;
  }

  double normalizedThreshold(Object? value, {required double fallback}) {
    final parsed =
        (value as num?)?.toDouble() ??
        double.tryParse(value?.toString() ?? '') ??
        fallback;
    if (parsed.isNaN) return fallback;
    if (parsed < 0) return 0.0;
    if (parsed > 1) return 1.0;
    return parsed;
  }
}
