import 'package:quwoquan_app/assistant/contracts/assistant_answer_payload_read_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_response_codec.dart';

class AssistantPipelineSubagentPlanCodec
    with AssistantPipelineResponseCodecMixin {
  const AssistantPipelineSubagentPlanCodec();

  List<SubagentPlan> buildSkillRunPlans({
    required AssistantPlanView planView,
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final explicitPlans = _buildExplicitSkillRunPlans(
      answerPayload: answerPayload,
      latestUserQuery: latestUserQuery,
      primaryDomainId: primaryDomainId,
    );
    if (explicitPlans.isNotEmpty) {
      return explicitPlans;
    }
    return _buildDerivedSkillRunPlansFromIntent(
      planView: planView,
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
      primaryDomainId: primaryDomainId,
    );
  }

  List<SubagentPlan> buildDerivedSkillRunPlansFromIntent({
    required AssistantPlanView planView,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    return _buildDerivedSkillRunPlansFromIntent(
      planView: planView,
      latestUserQuery: latestUserQuery,
      primaryDomainId: primaryDomainId,
    );
  }

  List<SubagentPlan> _buildExplicitSkillRunPlans({
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
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
          ),
        )
        .toList(growable: false);
  }

  List<SubagentPlan> _buildDerivedSkillRunPlansFromIntent({
    required AssistantPlanView planView,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final _ = (planView, latestUserQuery, primaryDomainId);
    return const <SubagentPlan>[];
  }

  String _buildSkillLocalContextSeed({
    required String userGoal,
    required String problemClass,
    required String latestUserQuery,
    required String skillId,
    required String primaryDomainId,
    List<String> entityRefs = const <String>[],
  }) {
    final anchors = entityRefs
        .where((item) => item.trim().isNotEmpty)
        .map((item) => item.trim())
        .toList(growable: false);
    final goal = userGoal.trim().isNotEmpty ? userGoal.trim() : latestUserQuery.trim();
    final buffer = StringBuffer()
      ..write('query=')
      ..write(goal)
      ..write('; primary=')
      ..write(primaryDomainId)
      ..write('; skill=')
      ..write(skillId)
      ..write('; class=')
      ..write(problemClass.trim());
    if (anchors.isNotEmpty) {
      buffer.write('; entities=');
      buffer.write(anchors.join('、'));
    }
    return buffer.toString();
  }

  SubagentPlan _normalizeSubagentPlan({
    required Map<String, dynamic> plan,
    required String latestUserQuery,
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
        (plan[SubagentPlanFields.problemClass] as String?)?.trim() ?? '';
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
              userGoal: goal.isNotEmpty ? goal : latestUserQuery,
              problemClass: rawProblemClass,
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

  String _defaultRouteNarrative(String domainId) {
    return 'primary=$domainId';
  }

  String normalizeProblemClassForQuery({
    required String raw,
  }) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return '';
    return parseProblemClass(trimmed).wireName;
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
