class SubagentPlan {
  const SubagentPlan({
    required this.subagentId,
    required this.domainId,
    required this.problemClass,
    required this.goal,
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

  Map<String, dynamic> toJson() => <String, dynamic>{
    'subagentId': subagentId,
    'domainId': domainId,
    'problemClass': problemClass,
    'goal': goal,
    'mode': mode,
    'timeoutMs': timeoutMs,
    'maxIterations': maxIterations,
    'toolBudget': toolBudget,
    'toolWhitelist': toolWhitelist,
    'stopPolicy': stopPolicy,
    'searchIntensity': searchIntensity,
    'providerPolicy': providerPolicy,
    'freshnessHoursMax': freshnessHoursMax,
    'answerThreshold': answerThreshold,
    'dependencies': dependencies,
  };

  factory SubagentPlan.fromJson(Map<String, dynamic> json) {
    return SubagentPlan(
      subagentId: (json['subagentId'] as String?)?.trim() ?? '',
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      problemClass: (json['problemClass'] as String?)?.trim() ?? '',
      goal: (json['goal'] as String?)?.trim() ?? '',
      mode: (json['mode'] as String?)?.trim() ?? 'qa',
      timeoutMs: _positiveInt(json['timeoutMs'], fallback: 12000),
      maxIterations: _positiveInt(json['maxIterations'], fallback: 2),
      toolBudget: _positiveInt(json['toolBudget'], fallback: 2),
      toolWhitelist:
          (json['toolWhitelist'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      stopPolicy: (json['stopPolicy'] as String?)?.trim() ?? 'balanced',
      searchIntensity: (json['searchIntensity'] as String?)?.trim() ?? 'medium',
      providerPolicy: (json['providerPolicy'] as String?)?.trim() ?? '',
      freshnessHoursMax: _nonNegativeInt(
        json['freshnessHoursMax'],
        fallback: 0,
      ),
      answerThreshold: _normalizedThreshold(json['answerThreshold']),
      dependencies:
          (json['dependencies'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
    );
  }

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
