export 'package:quwoquan_app/assistant/generated/contracts/subagent_plan.g.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

class SubagentPlan {
  const SubagentPlan({
    required this.subagentId,
    required this.domainId,
    required this.problemClass,
    required this.goal,
    this.role = 'supporting',
    this.taskBrief = '',
    this.routeNarrative = '',
    this.localContextSeed = '',
    this.needClarify = false,
    this.pendingClarifications = const <String>[],
    this.mode = 'qa',
    this.timeoutMs = 12000,
    this.maxIterations = 2,
    this.toolBudget = 2,
    this.toolWhitelist = const <String>[],
    this.stopPolicy = 'balanced',
    this.searchIntensity = 'medium',
    this.providerPolicy = '',
    this.freshnessHoursMax = 0,
    this.answerThreshold = 0.0,
    this.dependencies = const <String>[],
  });

  final String subagentId;
  final String domainId;
  final String problemClass;
  final String goal;
  final String role;
  final String taskBrief;
  final String routeNarrative;
  final String localContextSeed;
  final bool needClarify;
  final List<String> pendingClarifications;
  final String mode;
  final int timeoutMs;
  final int maxIterations;
  final int toolBudget;
  final List<String> toolWhitelist;
  final String stopPolicy;
  final String searchIntensity;
  final String providerPolicy;
  final int freshnessHoursMax;
  final double answerThreshold;
  final List<String> dependencies;

  ProblemClass get problemClassType => parseProblemClass(problemClass);

  SkillMode get modeType => parseSkillMode(mode);

  StopPolicy get stopPolicyType => parseStopPolicy(stopPolicy);

  SearchIntensity get searchIntensityType =>
      parseSearchIntensity(searchIntensity);

  ProviderPolicy get providerPolicyType =>
      parseProviderPolicy(providerPolicy);

  Map<String, dynamic> toJson() => <String, dynamic>{
    SubagentPlanFields.subagentId: subagentId,
    SubagentPlanFields.domainId: domainId,
    SubagentPlanFields.problemClass: problemClass,
    SubagentPlanFields.goal: goal,
    SubagentPlanFields.role: role,
    SubagentPlanFields.taskBrief: taskBrief,
    SubagentPlanFields.routeNarrative: routeNarrative,
    SubagentPlanFields.localContextSeed: localContextSeed,
    SubagentPlanFields.needClarify: needClarify,
    SubagentPlanFields.pendingClarifications: pendingClarifications,
    SubagentPlanFields.mode: mode,
    SubagentPlanFields.timeoutMs: timeoutMs,
    SubagentPlanFields.maxIterations: maxIterations,
    SubagentPlanFields.toolBudget: toolBudget,
  };

  factory SubagentPlan.fromJson(Map<String, dynamic> json) {
    return SubagentPlan(
      subagentId: (json[SubagentPlanFields.subagentId] as String?)?.trim() ?? '',
      domainId: (json[SubagentPlanFields.domainId] as String?)?.trim() ?? '',
      problemClass:
          (json[SubagentPlanFields.problemClass] as String?)?.trim() ?? '',
      goal: (json[SubagentPlanFields.goal] as String?)?.trim() ?? '',
      role: (json[SubagentPlanFields.role] as String?)?.trim() ?? 'supporting',
      taskBrief: (json[SubagentPlanFields.taskBrief] as String?)?.trim() ?? '',
      routeNarrative:
          (json[SubagentPlanFields.routeNarrative] as String?)?.trim() ?? '',
      localContextSeed:
          (json[SubagentPlanFields.localContextSeed] as String?)?.trim() ?? '',
      needClarify: json[SubagentPlanFields.needClarify] == true,
      pendingClarifications:
          (json[SubagentPlanFields.pendingClarifications] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      mode: (json[SubagentPlanFields.mode] as String?)?.trim() ?? 'qa',
      timeoutMs: _positiveInt(json[SubagentPlanFields.timeoutMs], fallback: 12000),
      maxIterations:
          _positiveInt(json[SubagentPlanFields.maxIterations], fallback: 2),
      toolBudget: _positiveInt(json[SubagentPlanFields.toolBudget], fallback: 2),
      toolWhitelist:
          (json[SubagentPlanFields.toolWhitelist] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      stopPolicy: (json[SubagentPlanFields.stopPolicy] as String?)?.trim() ??
          'balanced',
      searchIntensity:
          (json[SubagentPlanFields.searchIntensity] as String?)?.trim() ??
          'medium',
      providerPolicy:
          (json[SubagentPlanFields.providerPolicy] as String?)?.trim() ?? '',
      freshnessHoursMax: _nonNegativeInt(
        json[SubagentPlanFields.freshnessHoursMax],
        fallback: 0,
      ),
      answerThreshold:
          _normalizedThreshold(json[SubagentPlanFields.answerThreshold]),
      dependencies:
          (json[SubagentPlanFields.dependencies] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
    );
  }

  bool get hasMilestone3Inputs =>
      domainId.trim().isNotEmpty &&
      problemClass.trim().isNotEmpty &&
      goal.trim().isNotEmpty &&
      role.trim().isNotEmpty &&
      taskBrief.trim().isNotEmpty &&
      routeNarrative.trim().isNotEmpty &&
      localContextSeed.trim().isNotEmpty &&
      timeoutMs > 0 &&
      maxIterations > 0 &&
      toolBudget > 0;

  static int _positiveInt(Object? value, {required int fallback}) {
    if (value is int && value > 0) return value;
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed > 0) return parsed;
    return fallback;
  }

  static int _nonNegativeInt(Object? value, {required int fallback}) {
    if (value is int && value >= 0) return value;
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed >= 0) return parsed;
    return fallback;
  }

  static double _normalizedThreshold(Object? value) {
    final parsed =
        (value as num?)?.toDouble() ??
        double.tryParse(value?.toString() ?? '') ??
        0.0;
    if (parsed.isNaN) return 0.0;
    if (parsed < 0) return 0.0;
    if (parsed > 1) return 1.0;
    return parsed;
  }
}

class SubagentPlanFields {
  static const String subagentId = 'subagentId';
  static const String domainId = 'domainId';
  static const String problemClass = 'problemClass';
  static const String goal = 'goal';
  static const String role = 'role';
  static const String taskBrief = 'taskBrief';
  static const String routeNarrative = 'routeNarrative';
  static const String localContextSeed = 'localContextSeed';
  static const String needClarify = 'needClarify';
  static const String pendingClarifications = 'pendingClarifications';
  static const String mode = 'mode';
  static const String timeoutMs = 'timeoutMs';
  static const String maxIterations = 'maxIterations';
  static const String toolBudget = 'toolBudget';
  static const String toolWhitelist = 'toolWhitelist';
  static const String stopPolicy = 'stopPolicy';
  static const String searchIntensity = 'searchIntensity';
  static const String providerPolicy = 'providerPolicy';
  static const String freshnessHoursMax = 'freshnessHoursMax';
  static const String answerThreshold = 'answerThreshold';
  static const String dependencies = 'dependencies';
}
