import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';

enum SearchPlanDimension {
  currentState,
  decisionImpact,
  candidateSpace,
  tradeoffs,
  fitConstraints,
  fitScenarios,
  riskBoundaries,
  keyFacts,
  decisionThreshold,
  coreObject,
  supportingEvidence,
  latestSignal,
  unknown,
}

SearchPlanDimension parseSearchPlanDimension(String raw) {
  switch (raw.trim()) {
    case 'current_state':
    case '当前状态':
      return SearchPlanDimension.currentState;
    case 'decision_impact':
    case '决策影响':
      return SearchPlanDimension.decisionImpact;
    case 'candidate_space':
    case '候选范围':
    case '候选方案':
      return SearchPlanDimension.candidateSpace;
    case 'tradeoffs':
    case '关键取舍':
      return SearchPlanDimension.tradeoffs;
    case 'fit_constraints':
    case '适配条件':
      return SearchPlanDimension.fitConstraints;
    case 'fit_scenarios':
    case '适用场景':
      return SearchPlanDimension.fitScenarios;
    case 'risk_boundaries':
    case '风险边界':
      return SearchPlanDimension.riskBoundaries;
    case 'key_facts':
    case '关键事实':
      return SearchPlanDimension.keyFacts;
    case 'decision_threshold':
    case '判断条件':
      return SearchPlanDimension.decisionThreshold;
    case 'core_object':
    case '核心对象':
      return SearchPlanDimension.coreObject;
    case 'supporting_evidence':
    case '支撑依据':
      return SearchPlanDimension.supportingEvidence;
    case 'latest_signal':
    case '最新变化':
      return SearchPlanDimension.latestSignal;
    default:
      return SearchPlanDimension.unknown;
  }
}

extension SearchPlanDimensionX on SearchPlanDimension {
  String get wireName {
    switch (this) {
      case SearchPlanDimension.currentState:
        return 'current_state';
      case SearchPlanDimension.decisionImpact:
        return 'decision_impact';
      case SearchPlanDimension.candidateSpace:
        return 'candidate_space';
      case SearchPlanDimension.tradeoffs:
        return 'tradeoffs';
      case SearchPlanDimension.fitConstraints:
        return 'fit_constraints';
      case SearchPlanDimension.fitScenarios:
        return 'fit_scenarios';
      case SearchPlanDimension.riskBoundaries:
        return 'risk_boundaries';
      case SearchPlanDimension.keyFacts:
        return 'key_facts';
      case SearchPlanDimension.decisionThreshold:
        return 'decision_threshold';
      case SearchPlanDimension.coreObject:
        return 'core_object';
      case SearchPlanDimension.supportingEvidence:
        return 'supporting_evidence';
      case SearchPlanDimension.latestSignal:
        return 'latest_signal';
      case SearchPlanDimension.unknown:
        return '';
    }
  }

  String get displayLabel {
    switch (this) {
      case SearchPlanDimension.currentState:
        return '当前状态';
      case SearchPlanDimension.decisionImpact:
        return '决策影响';
      case SearchPlanDimension.candidateSpace:
        return '候选范围';
      case SearchPlanDimension.tradeoffs:
        return '关键取舍';
      case SearchPlanDimension.fitConstraints:
        return '适配条件';
      case SearchPlanDimension.fitScenarios:
        return '适用场景';
      case SearchPlanDimension.riskBoundaries:
        return '风险边界';
      case SearchPlanDimension.keyFacts:
        return '关键事实';
      case SearchPlanDimension.decisionThreshold:
        return '判断条件';
      case SearchPlanDimension.coreObject:
        return '核心对象';
      case SearchPlanDimension.supportingEvidence:
        return '支撑依据';
      case SearchPlanDimension.latestSignal:
        return '最新变化';
      case SearchPlanDimension.unknown:
        return '';
    }
  }
}

class SearchPlanItem {
  const SearchPlanItem({
    required this.id,
    required this.query,
    this.label = '',
    this.dimension = SearchPlanDimension.unknown,
    this.entityRefs = const <String>[],
    this.negativeKeywords = const <String>[],
    this.authorityDomains = const <String>[],
    this.freshnessHoursMax = 0,
    this.answerShape = AnswerShape.unspecified,
    this.freshnessNeed = FreshnessNeed.unspecified,
    this.timeScope = '',
    this.timeRangeStart = '',
    this.timeRangeEnd = '',
    this.timePoint = '',
    this.timezone = '',
  });

  final String id;
  final String query;
  final String label;
  final SearchPlanDimension dimension;
  final List<String> entityRefs;
  final List<String> negativeKeywords;
  final List<String> authorityDomains;
  final int freshnessHoursMax;
  final AnswerShape answerShape;
  final FreshnessNeed freshnessNeed;
  final String timeScope;
  final String timeRangeStart;
  final String timeRangeEnd;
  final String timePoint;
  final String timezone;

  String get effectiveLabel =>
      label.trim().isNotEmpty ? label.trim() : dimension.displayLabel;

  String get dimensionCode => dimension.wireName;

  String get dimensionLabel => dimension.displayLabel;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'id': id,
    'query': query,
    'label': effectiveLabel.isNotEmpty ? effectiveLabel : query,
    if (dimension != SearchPlanDimension.unknown)
      'dimension': dimension.wireName,
    if (dimension.displayLabel.isNotEmpty)
      'dimensionLabel': dimension.displayLabel,
    if (entityRefs.isNotEmpty) 'entityRefs': entityRefs,
    if (negativeKeywords.isNotEmpty) 'negativeKeywords': negativeKeywords,
    if (authorityDomains.isNotEmpty) 'authorityDomains': authorityDomains,
    if (freshnessHoursMax > 0) 'freshnessHoursMax': freshnessHoursMax,
    if (answerShape != AnswerShape.unspecified) 'answerShape': answerShape.wireName,
    if (freshnessNeed != FreshnessNeed.unspecified)
      'freshnessNeed': freshnessNeed.wireName,
    if (timeScope.trim().isNotEmpty) 'timeScope': timeScope,
    if (timeRangeStart.trim().isNotEmpty) 'timeRangeStart': timeRangeStart,
    if (timeRangeEnd.trim().isNotEmpty) 'timeRangeEnd': timeRangeEnd,
    if (timePoint.trim().isNotEmpty) 'timePoint': timePoint,
    if (timezone.trim().isNotEmpty) 'timezone': timezone,
  };

  factory SearchPlanItem.fromJson(Map<String, dynamic> json) {
    final query = (json['query'] as String?)?.trim() ?? '';
    final label = (json['label'] as String?)?.trim() ?? '';
    final dimension = parseSearchPlanDimension(
      (json['dimension'] as String?)?.trim().isNotEmpty == true
          ? (json['dimension'] as String).trim()
          : (json['dimensionLabel'] as String?)?.trim() ?? label,
    );
    return SearchPlanItem(
      id: (json['id'] as String?)?.trim().isNotEmpty == true
          ? (json['id'] as String).trim()
          : _normalizePlanId(
              query,
              preferred: label.isNotEmpty ? label : dimension.displayLabel,
            ),
      query: query,
      label: label,
      dimension: dimension,
      entityRefs: _stringList(json['entityRefs']),
      negativeKeywords: _stringList(json['negativeKeywords']),
      authorityDomains: _stringList(json['authorityDomains']),
      freshnessHoursMax: (json['freshnessHoursMax'] as num?)?.toInt() ?? 0,
      answerShape: parseAnswerShape((json['answerShape'] as String?)?.trim() ?? ''),
      freshnessNeed: parseFreshnessNeed(
        (json['freshnessNeed'] as String?)?.trim() ?? '',
      ),
      timeScope: (json['timeScope'] as String?)?.trim() ?? '',
      timeRangeStart: (json['timeRangeStart'] as String?)?.trim() ?? '',
      timeRangeEnd: (json['timeRangeEnd'] as String?)?.trim() ?? '',
      timePoint: (json['timePoint'] as String?)?.trim() ?? '',
      timezone: (json['timezone'] as String?)?.trim() ?? '',
    );
  }

  SearchPlanItem copyWith({
    String? id,
    String? query,
    String? label,
    SearchPlanDimension? dimension,
    List<String>? entityRefs,
    List<String>? negativeKeywords,
    List<String>? authorityDomains,
    int? freshnessHoursMax,
    AnswerShape? answerShape,
    FreshnessNeed? freshnessNeed,
    String? timeScope,
    String? timeRangeStart,
    String? timeRangeEnd,
    String? timePoint,
    String? timezone,
  }) {
    return SearchPlanItem(
      id: id ?? this.id,
      query: query ?? this.query,
      label: label ?? this.label,
      dimension: dimension ?? this.dimension,
      entityRefs: entityRefs ?? this.entityRefs,
      negativeKeywords: negativeKeywords ?? this.negativeKeywords,
      authorityDomains: authorityDomains ?? this.authorityDomains,
      freshnessHoursMax: freshnessHoursMax ?? this.freshnessHoursMax,
      answerShape: answerShape ?? this.answerShape,
      freshnessNeed: freshnessNeed ?? this.freshnessNeed,
      timeScope: timeScope ?? this.timeScope,
      timeRangeStart: timeRangeStart ?? this.timeRangeStart,
      timeRangeEnd: timeRangeEnd ?? this.timeRangeEnd,
      timePoint: timePoint ?? this.timePoint,
      timezone: timezone ?? this.timezone,
    );
  }

  static List<SearchPlanItem> normalizeList(Object? raw) {
    final rawList = raw is List ? raw : const <Object?>[];
    final parsed = rawList
        .whereType<Map>()
        .map((item) => SearchPlanItem.fromJson(item.cast<String, dynamic>()))
        .where((item) => item.query.trim().isNotEmpty)
        .toList(growable: false);
    final seen = <String>{};
    final unique = <SearchPlanItem>[];
    for (final item in parsed) {
      final key = item.id.trim().isNotEmpty ? item.id.trim() : item.query.trim();
      if (!seen.add(key)) {
        continue;
      }
      unique.add(item);
    }
    return unique;
  }

  static List<Map<String, dynamic>> toJsonList(Iterable<SearchPlanItem> plans) {
    return plans.map((item) => item.toJson()).toList(growable: false);
  }
}

class SearchIterationRound {
  const SearchIterationRound({
    this.iteration = 0,
    this.triggerReason = '',
    this.plannerInputSummary = '',
    this.plannerOutputSummary = '',
    this.searchPlans = const <SearchPlanItem>[],
    this.acceptedEvidenceCount = 0,
    this.missingDimensions = const <String>[],
    this.convergenceStatus = SearchIterationConvergenceStatus.unknown,
  });

  final int iteration;
  final String triggerReason;
  final String plannerInputSummary;
  final String plannerOutputSummary;
  final List<SearchPlanItem> searchPlans;
  final int acceptedEvidenceCount;
  final List<String> missingDimensions;
  final SearchIterationConvergenceStatus convergenceStatus;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'iteration': iteration,
    'triggerReason': triggerReason,
    'plannerInputSummary': plannerInputSummary,
    'plannerOutputSummary': plannerOutputSummary,
    'searchPlans': SearchPlanItem.toJsonList(searchPlans),
    'acceptedEvidenceCount': acceptedEvidenceCount,
    'missingDimensions': missingDimensions,
    'convergenceStatus': convergenceStatus.wireName,
  };

  factory SearchIterationRound.fromJson(Map<String, dynamic> json) {
    return SearchIterationRound(
      iteration: (json['iteration'] as num?)?.toInt() ?? 0,
      triggerReason: (json['triggerReason'] as String?)?.trim() ?? '',
      plannerInputSummary: (json['plannerInputSummary'] as String?)?.trim() ?? '',
      plannerOutputSummary:
          (json['plannerOutputSummary'] as String?)?.trim() ?? '',
      searchPlans: SearchPlanItem.normalizeList(json['searchPlans']),
      acceptedEvidenceCount:
          (json['acceptedEvidenceCount'] as num?)?.toInt() ?? 0,
      missingDimensions: _stringList(json['missingDimensions']),
      convergenceStatus: parseSearchIterationConvergenceStatus(
        (json['convergenceStatus'] as String?)?.trim() ?? '',
      ),
    );
  }
}

class SearchIterationState {
  const SearchIterationState({
    this.maxIterations = 0,
    this.currentIteration = 0,
    this.rounds = const <SearchIterationRound>[],
  });

  final int maxIterations;
  final int currentIteration;
  final List<SearchIterationRound> rounds;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'maxIterations': maxIterations,
    'currentIteration': currentIteration,
    'rounds': rounds.map((item) => item.toJson()).toList(growable: false),
  };

  factory SearchIterationState.fromJson(Map<String, dynamic> json) {
    return SearchIterationState(
      maxIterations: (json['maxIterations'] as num?)?.toInt() ?? 0,
      currentIteration: (json['currentIteration'] as num?)?.toInt() ?? 0,
      rounds: (json['rounds'] as List?)
              ?.whereType<Map>()
              .map((item) => SearchIterationRound.fromJson(item.cast<String, dynamic>()))
              .toList(growable: false) ??
          const <SearchIterationRound>[],
    );
  }
}

List<SearchPlanItem> searchPlansFromTaskGraph(TaskGraph taskGraph) {
  final plans = <SearchPlanItem>[];
  for (final task in taskGraph.tasks) {
    final explicitPlans = SearchPlanItem.normalizeList(
      task.toolArgs.fields['searchPlans'],
    );
    if (explicitPlans.isNotEmpty) {
      plans.addAll(explicitPlans);
      continue;
    }
    final query = (task.toolArgs.fields['query'] as String?)?.trim() ?? '';
    if (query.isEmpty) {
      continue;
    }
    plans.add(SearchPlanItem(id: task.taskId, query: query));
  }
  return SearchPlanItem.normalizeList(SearchPlanItem.toJsonList(plans));
}

List<String> _stringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
  return const <String>[];
}

String _normalizePlanId(String query, {String preferred = ''}) {
  final base = (preferred.trim().isNotEmpty ? preferred : query).trim();
  if (base.isEmpty) {
    return 'search_plan';
  }
  final normalized = base
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9\u4e00-\u9fff]+'), '_')
      .replaceAll(RegExp(r'_+'), '_')
      .replaceAll(RegExp(r'^_|_$'), '');
  return normalized.isEmpty ? 'search_plan' : normalized;
}
