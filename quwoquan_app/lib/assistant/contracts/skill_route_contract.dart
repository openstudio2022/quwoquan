import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';

class SkillRouteTarget {
  const SkillRouteTarget({
    required this.skillId,
    this.role = 'supporting',
    this.priority = 0,
    this.goal = '',
    this.problemClass = '',
    this.taskBrief = '',
    this.routeNarrative = '',
    this.localContextSeed = '',
    this.needClarify = false,
    this.pendingClarifications = const <String>[],
  });

  final String skillId;
  final String role;
  final int priority;
  final String goal;
  final String problemClass;
  final String taskBrief;
  final String routeNarrative;
  final String localContextSeed;
  final bool needClarify;
  final List<String> pendingClarifications;

  factory SkillRouteTarget.primary({
    required String skillId,
    required String goal,
    required String problemClass,
    required String taskBrief,
    required String routeNarrative,
    required String localContextSeed,
    bool needClarify = false,
    List<String> pendingClarifications = const <String>[],
  }) {
    return SkillRouteTarget(
      skillId: skillId,
      role: 'primary',
      priority: 1,
      goal: goal,
      problemClass: problemClass,
      taskBrief: taskBrief,
      routeNarrative: routeNarrative,
      localContextSeed: localContextSeed,
      needClarify: needClarify,
      pendingClarifications: _normalizeStringList(pendingClarifications),
    );
  }

  factory SkillRouteTarget.fromSubagentPlan(
    SubagentPlan plan, {
    required int priority,
  }) {
    return SkillRouteTarget(
      skillId: plan.domainId.trim(),
      role: plan.role.trim().isNotEmpty ? plan.role.trim() : 'supporting',
      priority: priority,
      goal: plan.goal.trim(),
      problemClass: plan.problemClass.trim(),
      taskBrief: plan.taskBrief.trim(),
      routeNarrative: plan.routeNarrative.trim(),
      localContextSeed: plan.localContextSeed.trim(),
      needClarify: plan.needClarify,
      pendingClarifications: _normalizeStringList(plan.pendingClarifications),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'skillId': skillId,
        'role': role,
        'priority': priority,
        'goal': goal,
        'problemClass': problemClass,
        'taskBrief': taskBrief,
        'routeNarrative': routeNarrative,
        'localContextSeed': localContextSeed,
        'needClarify': needClarify,
        'pendingClarifications': pendingClarifications,
      };

  factory SkillRouteTarget.fromJson(Map<String, dynamic> json) {
    return SkillRouteTarget(
      skillId: (json['skillId'] as String?)?.trim() ?? '',
      role: (json['role'] as String?)?.trim() ?? 'supporting',
      priority: (json['priority'] as num?)?.toInt() ?? 0,
      goal: (json['goal'] as String?)?.trim() ?? '',
      problemClass: (json['problemClass'] as String?)?.trim() ?? '',
      taskBrief: (json['taskBrief'] as String?)?.trim() ?? '',
      routeNarrative: (json['routeNarrative'] as String?)?.trim() ?? '',
      localContextSeed: (json['localContextSeed'] as String?)?.trim() ?? '',
      needClarify: json['needClarify'] == true,
      pendingClarifications: _normalizeStringList(json['pendingClarifications']),
    );
  }
}

class SkillRouteOutput {
  const SkillRouteOutput({
    this.contractId = 'skill_route',
    required this.userQuery,
    required this.selectedTargets,
    this.routeNarrative = '',
    this.needClarify = false,
    this.pendingClarifications = const <String>[],
  });

  final String contractId;
  final String userQuery;
  final List<SkillRouteTarget> selectedTargets;
  final String routeNarrative;
  final bool needClarify;
  final List<String> pendingClarifications;

  bool get hasSelectedTargets =>
      selectedTargets.any((item) => item.skillId.trim().isNotEmpty);

  Map<String, dynamic> toJson() => <String, dynamic>{
        'contractId': contractId,
        'userQuery': userQuery,
        'selectedTargets':
            selectedTargets.map((item) => item.toJson()).toList(growable: false),
        'routeNarrative': routeNarrative,
        'needClarify': needClarify,
        'pendingClarifications': pendingClarifications,
      };

  factory SkillRouteOutput.fromJson(Map<String, dynamic> json) {
    return SkillRouteOutput(
      contractId: (json['contractId'] as String?)?.trim() ?? 'skill_route',
      userQuery: (json['userQuery'] as String?)?.trim() ?? '',
      selectedTargets: _targetList(json['selectedTargets']),
      routeNarrative: (json['routeNarrative'] as String?)?.trim() ?? '',
      needClarify: json['needClarify'] == true,
      pendingClarifications: _normalizeStringList(json['pendingClarifications']),
    );
  }

  factory SkillRouteOutput.fromPrimaryAndSupportingPlans({
    required String userQuery,
    required SkillRouteTarget primaryTarget,
    required List<SubagentPlan> supportingPlans,
    String routeNarrative = '',
    bool needClarify = false,
    List<String> pendingClarifications = const <String>[],
  }) {
    final selectedTargets = <SkillRouteTarget>[
      primaryTarget,
      for (var i = 0; i < supportingPlans.length; i++)
        SkillRouteTarget.fromSubagentPlan(
          supportingPlans[i],
          priority: i + 2,
        ),
    ];
    final mergedClarifications = <String>{
      ..._normalizeStringList(pendingClarifications),
      ...selectedTargets.expand((item) => item.pendingClarifications),
    }.toList(growable: false);
    final resolvedRouteNarrative = routeNarrative.trim().isNotEmpty
        ? routeNarrative.trim()
        : selectedTargets
            .map((item) => item.routeNarrative.trim())
            .where((item) => item.isNotEmpty)
            .join(' | ');
    return SkillRouteOutput(
      userQuery: userQuery,
      selectedTargets: selectedTargets,
      routeNarrative: resolvedRouteNarrative,
      needClarify:
          needClarify ||
          primaryTarget.needClarify ||
          supportingPlans.any((item) => item.needClarify) ||
          mergedClarifications.isNotEmpty,
      pendingClarifications: mergedClarifications,
    );
  }
}

List<SkillRouteTarget> _targetList(Object? value) {
  if (value is! List) {
    return const <SkillRouteTarget>[];
  }
  return value
      .whereType<Map>()
      .map((item) => SkillRouteTarget.fromJson(item.cast<String, dynamic>()))
      .where((item) => item.skillId.trim().isNotEmpty)
      .toList(growable: false);
}

List<String> _normalizeStringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
  if (value is String && value.trim().isNotEmpty) {
    return <String>[value.trim()];
  }
  return const <String>[];
}
