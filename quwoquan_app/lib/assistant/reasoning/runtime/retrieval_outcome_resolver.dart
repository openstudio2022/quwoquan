// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 工具结果 Map 链；优先 AssistantToolResultRowView 与结构化契约字段。

import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row_view.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';

const RelativeTimeResolver _relativeTimeResolver = RelativeTimeResolver();
const double _minFullAnswerRelevanceScore = 0.45;

class RetrievalOutcomeResolver {
  const RetrievalOutcomeResolver();

  RetrievalOutcome resolve({
    required AnswerBoundaryPolicy policy,
    required RetrievalProcessingSnapshot retrievalProcessing,
    required EvidenceEvaluationResult evidenceEvaluation,
    required SynthesisReadinessResult synthesisReadiness,
    List<QueryTask> queryTasks = const <QueryTask>[],
    List<Map<String, dynamic>> toolResults = const <Map<String, dynamic>>[],
    bool terminalPayloadComplete = true,
    bool degraded = false,
    String referenceNowIso = '',
    String timezone = '',
  }) {
    final referenceCount = retrievalProcessing.acceptedReferences.isNotEmpty
        ? retrievalProcessing.acceptedReferences.length
        : evidenceEvaluation.entries.length;
    final processedDocumentCount =
        retrievalProcessing.processedDocumentCount > 0
        ? retrievalProcessing.processedDocumentCount
        : _positiveIntFromToolResults(toolResults, 'totalReferences');
    final acceptedDocumentCount = retrievalProcessing.acceptedDocumentCount > 0
        ? retrievalProcessing.acceptedDocumentCount
        : referenceCount;
    final hasToolResult =
        toolResults.isNotEmpty ||
        evidenceEvaluation.entries.isNotEmpty ||
        processedDocumentCount > 0 ||
        acceptedDocumentCount > 0;
    final temporalAnchor = _temporalAnchorFromToolResults(
      toolResults,
      referenceNowIso: referenceNowIso,
      timezone: timezone,
    );
    final temporalAssessment = _resolveTemporalAssessment(
      policy: policy,
      queryTasks: queryTasks,
      toolResults: toolResults,
      evidenceEvaluation: evidenceEvaluation,
      referenceNowIso: temporalAnchor.referenceNowIso,
      timezone: temporalAnchor.timezone,
    );
    final authoritySatisfied = !policy.authorityRequired
        ? true
        : (evidenceEvaluation.authoritySatisfied ||
              _boolFromToolResults(toolResults, 'authoritySatisfied'));
    final coveredDimensions = _normalizedDimensions(
      evidenceEvaluation.coveredDimensions,
    );
    final missingDimensions = evidenceEvaluation.missingDimensions.isNotEmpty
        ? _normalizedDimensions(evidenceEvaluation.missingDimensions)
        : _missingDimensions(
            requiredDimensions: policy.blockingDimensions.isNotEmpty
                ? policy.blockingDimensions
                : policy.requiredDimensions,
            coveredDimensions: coveredDimensions,
          );
    final temporalSatisfied = temporalAssessment.requirementSatisfied;
    final relevanceSatisfied = _relevanceSatisfied(
      evidenceEvaluation: evidenceEvaluation,
      toolResults: toolResults,
    );
    final evidencePassed = !policy.evidenceRequired
        ? true
        : (evidenceEvaluation.passed ||
                  (policy.allowBoundedAnswer &&
                      evidenceEvaluation.status == EvidenceStatus.bounded &&
                      authoritySatisfied &&
                      temporalSatisfied &&
                      missingDimensions.isEmpty)) &&
              relevanceSatisfied;
    final summary = _firstNonEmpty(<String>[
      !relevanceSatisfied ? '当前检索到的资料与问题核心关联度不够，需要补充更有针对性的证据后再给出结论。' : '',
      synthesisReadiness.ready ? evidenceEvaluation.summary : '',
      retrievalProcessing.processingSummary,
      synthesisReadiness.reason,
    ]);
    final status = _resolveStatus(
      degraded: degraded,
      terminalPayloadComplete: terminalPayloadComplete,
      hasToolResult: hasToolResult,
      evidencePassed: evidencePassed,
      authoritySatisfied: authoritySatisfied,
      freshnessRequired: temporalAssessment.freshnessRequired,
      freshnessKnown: temporalAssessment.freshnessKnown,
      freshnessSatisfied: temporalAssessment.freshnessSatisfied,
      timeWindowRequired: temporalAssessment.timeWindowRequired,
      timeWindowKnown: temporalAssessment.timeWindowKnown,
      timeWindowSatisfied: temporalAssessment.timeWindowSatisfied,
      missingDimensions: missingDimensions,
      evidenceRequired: policy.evidenceRequired,
    );
    return RetrievalOutcome(
      status: status,
      summary: summary,
      evidenceRequired: policy.evidenceRequired,
      authorityRequired: policy.authorityRequired,
      freshnessRequired: temporalAssessment.freshnessRequired,
      timeWindowRequired: temporalAssessment.timeWindowRequired,
      hasToolResult: hasToolResult,
      referenceCount: referenceCount,
      processedDocumentCount: processedDocumentCount,
      acceptedDocumentCount: acceptedDocumentCount,
      coveredDimensions: coveredDimensions,
      missingDimensions: missingDimensions,
      coveredQueryTaskIds: evidenceEvaluation.coveredQueryTaskIds,
      authorityDomains: policy.authorityDomains,
      authoritySatisfied: authoritySatisfied,
      freshnessHoursMax: policy.freshnessHoursMax,
      freshnessHours: evidenceEvaluation.freshnessHours,
      freshnessKnown: temporalAssessment.freshnessKnown,
      freshnessSatisfied: temporalAssessment.freshnessSatisfied,
      timeWindowKnown: temporalAssessment.timeWindowKnown,
      timeWindowSatisfied: temporalAssessment.timeWindowSatisfied,
      evidencePassed: evidencePassed,
      evidenceStatus: evidenceEvaluation.status.wireName,
      expansionReason: _firstNonEmpty(<String>[
        retrievalProcessing.expansionReason,
        synthesisReadiness.ready ? '' : synthesisReadiness.reason,
      ]),
      terminalPayloadComplete: terminalPayloadComplete,
      degraded: degraded,
      retrievalProcessing: retrievalProcessing,
    );
  }

  RetrievalOutcome resolveFromStructured({
    required Map<String, dynamic> structured,
    RunArtifacts? runArtifacts,
    bool degraded = false,
  }) {
    final raw = (structured[assistantRetrievalOutcomeField] as Map?)
        ?.cast<String, Object?>();
    if (raw != null && raw.isNotEmpty) {
      try {
        return RetrievalOutcome.fromJson(raw);
      } catch (_) {
        // Fall through to structured derivation.
      }
    }
    final retrievalProcessing =
        _parseRetrievalProcessing(
          structured['retrievalProcessing'] ??
              structured['runArtifacts'] ??
              runArtifacts?.retrievalProcessing.toJson(),
        ) ??
        runArtifacts?.retrievalProcessing ??
        const RetrievalProcessingSnapshot();
    final evidenceEvaluation = _parseEvidenceEvaluation(
      structured['evidenceEvaluation'] ??
          runArtifacts?.diagnostics.evidenceEvaluationForOutcomeMerge(),
      entries: runArtifacts?.evidenceLedger ?? const <EvidenceLedgerEntry>[],
    );
    final boundaryPolicy = _parseBoundaryPolicy(
      structured['answerBoundaryPolicy'] ??
          runArtifacts?.diagnostics.answerBoundaryPolicyForOutcomeMerge(),
    );
    final synthesisReadiness =
        _parseSynthesisReadiness(structured['synthesisReadiness']) ??
        const SynthesisReadinessResult();
    final temporalReference = _resolveStructuredTemporalReference(
      structured,
      runArtifacts: runArtifacts,
    );
    return resolve(
      policy: boundaryPolicy,
      retrievalProcessing: retrievalProcessing,
      evidenceEvaluation: evidenceEvaluation,
      synthesisReadiness: synthesisReadiness,
      queryTasks: _parseQueryTasks(
        structured['queryTasks'] ??
            ((structured['intentGraph'] as Map?)?['queryTasks']),
      ),
      toolResults: _toolResultsFromStructured(structured),
      terminalPayloadComplete: _terminalPayloadComplete(structured),
      degraded: degraded,
      referenceNowIso: temporalReference.referenceNowIso,
      timezone: temporalReference.timezone,
    );
  }

  bool _relevanceSatisfied({
    required EvidenceEvaluationResult evidenceEvaluation,
    required List<Map<String, dynamic>> toolResults,
  }) {
    final effectiveScore = _resolveEffectiveRelevanceScore(
      evidenceEvaluation: evidenceEvaluation,
      toolResults: toolResults,
    );
    if (effectiveScore == null) {
      return true;
    }
    return effectiveScore >= _minFullAnswerRelevanceScore;
  }

  double? _resolveEffectiveRelevanceScore({
    required EvidenceEvaluationResult evidenceEvaluation,
    required List<Map<String, dynamic>> toolResults,
  }) {
    if (evidenceEvaluation.entries.isNotEmpty ||
        evidenceEvaluation.relevanceScore > 0) {
      return evidenceEvaluation.relevanceScore;
    }
    final fromToolResults = _toolResultRelevanceScore(toolResults);
    if (fromToolResults > 0) {
      return fromToolResults;
    }
    return null;
  }

  double _toolResultRelevanceScore(List<Map<String, dynamic>> toolResults) {
    var bestScore = 0.0;
    for (final result in toolResults) {
      final data =
          (result['data'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      final qualityScore = (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
      if (qualityScore > bestScore) {
        bestScore = qualityScore;
      }
      final references =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, Object?>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (references.isEmpty) {
        continue;
      }
      final scored = references
          .map((item) => (item['relevanceScore'] as num?)?.toDouble() ?? 0.0)
          .where((score) => score > 0)
          .toList(growable: false);
      if (scored.isEmpty) {
        continue;
      }
      final averageScore =
          scored.reduce((left, right) => left + right) / scored.length;
      if (averageScore > bestScore) {
        bestScore = averageScore;
      }
    }
    return bestScore;
  }

  RetrievalOutcome resolveFromToolResult({
    required Map<String, dynamic> resultData,
    required AnswerBoundaryPolicy policy,
  }) {
    final references =
        (resultData['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, Object?>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final retrievalProcessing = RetrievalProcessingSnapshot(
      processedDocumentCount:
          (resultData['totalReferences'] as num?)?.toInt() ?? references.length,
      acceptedDocumentCount:
          (resultData['referenceCount'] as num?)?.toInt() ?? references.length,
      processingSummary: (resultData['summary'] as String?)?.trim() ?? '',
      selectedKeyPoints:
          (resultData['selectedKeyPoints'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      expansionReason: (resultData['expansionReason'] as String?)?.trim() ?? '',
      acceptedReferences: references
          .map(
            (item) => RetrievalProcessingReference(
              title: (item['title'] as String?)?.trim() ?? '',
              url: (item['url'] as String?)?.trim() ?? '',
              source: (item['source'] as String?)?.trim() ?? '',
              snippet: (item['snippet'] as String?)?.trim() ?? '',
            ),
          )
          .where(
            (item) =>
                item.title.isNotEmpty ||
                item.url.isNotEmpty ||
                item.source.isNotEmpty,
          )
          .toList(growable: false),
    );
    final evidenceEvaluation = EvidenceEvaluationResult(
      entries: const <EvidenceLedgerEntry>[],
      coverageScore: (resultData['coverage'] as num?)?.toDouble() ?? 0.0,
      authorityScore: (resultData['authorityScore'] as num?)?.toDouble() ?? 0.0,
      relevanceScore: (resultData['relevanceScore'] as num?)?.toDouble() ?? 0.0,
      freshnessHours: (resultData['freshnessHours'] as num?)?.toInt() ?? 0,
      status: _parseEvidenceStatus(
        (resultData['evidenceStatus'] as String?)?.trim() ??
            (resultData['retrievalInsufficient'] == true ? 'retry' : ''),
      ),
      passed:
          resultData['evidencePassed'] == true ||
          resultData['retrievalInsufficient'] != true,
      authoritySatisfied: resultData['authoritySatisfied'] != false,
      freshnessSatisfied: resultData['freshnessSatisfied'] == true,
      evidenceRequired: policy.evidenceRequired,
      coveredDimensions: _normalizedDimensions(
        resultData['coveredDimensions'] is List
            ? (resultData['coveredDimensions'] as List).cast<String>()
            : const <String>[],
      ),
      coveredQueryTaskIds:
          (resultData['coveredQueryTaskIds'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      blockingDimensions: policy.blockingDimensions,
      missingDimensions: _normalizedDimensions(
        resultData['missingDimensions'] is List
            ? (resultData['missingDimensions'] as List).cast<String>()
            : const <String>[],
      ),
      summary: (resultData['summary'] as String?)?.trim() ?? '',
    );
    return resolve(
      policy: policy,
      retrievalProcessing: retrievalProcessing,
      evidenceEvaluation: evidenceEvaluation,
      synthesisReadiness: const SynthesisReadinessResult(ready: true),
      queryTasks: _parseQueryTasks(resultData['queryTasks']),
      toolResults: <Map<String, dynamic>>[
        <String, dynamic>{'data': resultData},
      ],
    );
  }

  /// 工具层 timeConstraint 常带 referenceNowIso（与 query 语义一致）；优先于调用方未传的墙钟缺省。
  ({String referenceNowIso, String timezone}) _temporalAnchorFromToolResults(
    List<Map<String, dynamic>> toolResults, {
    required String referenceNowIso,
    required String timezone,
  }) {
    var mergedRef = referenceNowIso.trim();
    var mergedTz = timezone.trim();
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      final tc =
          (data['timeConstraint'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      final iso = (tc['referenceNowIso'] as String?)?.trim() ?? '';
      if (iso.isEmpty) {
        continue;
      }
      mergedRef = iso;
      final tz = (tc['timezone'] as String?)?.trim() ?? '';
      if (tz.isNotEmpty) {
        mergedTz = tz;
      }
      break;
    }
    return (referenceNowIso: mergedRef, timezone: mergedTz);
  }

  _TemporalAssessment _resolveTemporalAssessment({
    required AnswerBoundaryPolicy policy,
    required List<QueryTask> queryTasks,
    required List<Map<String, dynamic>> toolResults,
    required EvidenceEvaluationResult evidenceEvaluation,
    required String referenceNowIso,
    required String timezone,
  }) {
    final historicalWindowRequired = _requiresHistoricalWindow(
      queryTasks: queryTasks,
      toolResults: toolResults,
      referenceNowIso: referenceNowIso,
      timezone: timezone,
    );
    final strictFreshnessRequired =
        !historicalWindowRequired &&
        _requiresStrictFreshness(
          policy: policy,
          queryTasks: queryTasks,
          toolResults: toolResults,
        );
    if (historicalWindowRequired) {
      final timeWindowKnown =
          _resolveFreshnessKnown(toolResults) ||
          evidenceEvaluation.entries.any((entry) => entry.freshnessHours > 0);
      final timeWindowSatisfied = toolResults.isNotEmpty
          ? _resolveTemporalSatisfiedFromToolResults(toolResults)
          : evidenceEvaluation.freshnessSatisfied;
      return _TemporalAssessment(
        freshnessRequired: false,
        freshnessKnown: false,
        freshnessSatisfied: true,
        timeWindowRequired: true,
        timeWindowKnown: timeWindowKnown,
        timeWindowSatisfied: timeWindowSatisfied,
      );
    }
    if (strictFreshnessRequired) {
      final freshnessKnown =
          _resolveFreshnessKnown(toolResults) ||
          evidenceEvaluation.entries.any((entry) => entry.freshnessHours > 0);
      final freshnessSatisfied = toolResults.isNotEmpty
          ? _resolveTemporalSatisfiedFromToolResults(toolResults)
          : evidenceEvaluation.freshnessSatisfied;
      return _TemporalAssessment(
        freshnessRequired: true,
        freshnessKnown: freshnessKnown,
        freshnessSatisfied: freshnessSatisfied,
      );
    }
    return const _TemporalAssessment(
      freshnessRequired: false,
      freshnessKnown: false,
      freshnessSatisfied: true,
      timeWindowRequired: false,
      timeWindowKnown: false,
      timeWindowSatisfied: true,
    );
  }

  bool _requiresStrictFreshness({
    required AnswerBoundaryPolicy policy,
    required List<QueryTask> queryTasks,
    required List<Map<String, dynamic>> toolResults,
  }) {
    if (queryTasks.any(
      (task) =>
          task.freshnessNeed == FreshnessNeed.recent ||
          task.freshnessNeed == FreshnessNeed.realtime,
    )) {
      return true;
    }
    if (queryTasks.any(_queryTaskNeedsStrictFreshness)) {
      return true;
    }
    if (queryTasks.any(
      (task) =>
          task.timeScope == 'latest' ||
          task.timeScope == 'today' ||
          task.timeScope == 'last_7d',
    )) {
      return true;
    }
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      if (data['freshnessRequired'] == true) {
        return true;
      }
      final timeConstraint =
          (data['timeConstraint'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      final temporalMode =
          (timeConstraint['temporalMode'] as String?)?.trim().toLowerCase() ??
          '';
      if (temporalMode == 'realtime') {
        return true;
      }
      final scope = (timeConstraint['scope'] as String?)?.trim() ?? '';
      if (scope == 'latest' || scope == 'today' || scope == 'last_7d') {
        return true;
      }
    }
    return queryTasks.isEmpty &&
        policy.freshnessHoursMax > 0 &&
        policy.freshnessHoursMax < 24 * 30;
  }

  bool _queryTaskNeedsStrictFreshness(QueryTask task) {
    if (task.freshnessHoursMax <= 0) {
      return false;
    }
    final timeScope = task.timeScope.trim();
    if (timeScope == 'latest' ||
        timeScope == 'today' ||
        timeScope == 'last_7d') {
      return true;
    }
    if (_hasExplicitTimeWindow(task)) {
      return false;
    }
    return true;
  }

  bool _hasExplicitTimeWindow(QueryTask task) {
    return task.timePoint.trim().isNotEmpty ||
        task.timeRangeStart.trim().isNotEmpty ||
        task.timeRangeEnd.trim().isNotEmpty;
  }

  bool _requiresHistoricalWindow({
    required List<QueryTask> queryTasks,
    required List<Map<String, dynamic>> toolResults,
    required String referenceNowIso,
    required String timezone,
  }) {
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      final timeConstraint =
          (data['timeConstraint'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      final temporalMode =
          (timeConstraint['temporalMode'] as String?)?.trim().toLowerCase() ??
          '';
      if (temporalMode == 'historical') {
        return true;
      }
      if (_isHistoricalTimeConstraint(
        timeConstraint,
        referenceNowIso: referenceNowIso,
        timezone: timezone,
      )) {
        return true;
      }
    }
    return queryTasks.any(
      (task) => _isHistoricalQueryTask(
        task,
        referenceNowIso: referenceNowIso,
        timezone: timezone,
      ),
    );
  }

  bool _resolveFreshnessKnown(List<Map<String, dynamic>> toolResults) {
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      if (data['freshnessKnown'] == true) {
        return true;
      }
      final references =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((entry) => entry.cast<String, Object?>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final reference in references) {
        if (reference['freshnessKnown'] == true) {
          return true;
        }
        if ((reference['observedAt'] as String?)?.trim().isNotEmpty == true ||
            (reference['publishedAt'] as String?)?.trim().isNotEmpty == true) {
          return true;
        }
      }
    }
    return false;
  }

  bool _resolveTemporalSatisfiedFromToolResults(
    List<Map<String, dynamic>> toolResults,
  ) {
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, Object?>() ??
          const <String, Object?>{};
      if (data['freshnessSatisfied'] == true) {
        return true;
      }
      final references =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((entry) => entry.cast<String, Object?>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final reference in references) {
        if (reference['freshnessSatisfied'] == true) {
          return true;
        }
      }
    }
    return false;
  }

  bool _isHistoricalQueryTask(
    QueryTask task, {
    String referenceNowIso = '',
    String timezone = '',
  }) {
    if (task.timeScope.trim().isEmpty &&
        task.timePoint.trim().isEmpty &&
        task.timeRangeStart.trim().isEmpty &&
        task.timeRangeEnd.trim().isEmpty) {
      return false;
    }
    final timeScope = task.timeScope.trim();
    if (timeScope == 'latest' ||
        timeScope == 'today' ||
        timeScope == 'last_7d') {
      return false;
    }
    final referenceNow = _resolveReferenceNow(
      referenceNowIso: referenceNowIso,
      timezone: _firstNonEmpty(<String>[task.timezone, timezone]),
    );
    final dayFloor = DateTime(
      referenceNow.year,
      referenceNow.month,
      referenceNow.day,
    );
    final end =
        _parseDateTime(task.timeRangeEnd) ??
        _parseDateTime(task.timePoint) ??
        _parseDateTime(task.timeRangeStart);
    return end != null && end.isBefore(dayFloor);
  }

  bool _isHistoricalTimeConstraint(
    Map<String, dynamic> raw, {
    String referenceNowIso = '',
    String timezone = '',
  }) {
    if (raw.isEmpty) {
      return false;
    }
    final scope = (raw['scope'] as String?)?.trim() ?? '';
    if (scope == 'latest' || scope == 'today' || scope == 'last_7d') {
      return false;
    }
    final end = _parseDateTime((raw['timeRangeEnd'] as String?)?.trim() ?? '');
    if (end == null) {
      return false;
    }
    final referenceNow = _resolveReferenceNow(
      referenceNowIso: _firstNonEmpty(<String>[
        (raw['referenceNowIso'] as String?) ?? '',
        referenceNowIso,
      ]),
      timezone: _firstNonEmpty(<String>[
        (raw['timezone'] as String?) ?? '',
        timezone,
      ]),
    );
    final dayFloor = DateTime(
      referenceNow.year,
      referenceNow.month,
      referenceNow.day,
    );
    return end.isBefore(dayFloor);
  }

  DateTime _resolveReferenceNow({
    required String referenceNowIso,
    required String timezone,
  }) {
    final explicit = _parseDateTime(referenceNowIso);
    if (explicit != null) {
      return explicit;
    }
    return _relativeTimeResolver
        .resolveReferenceContext(
          referenceNowIso: referenceNowIso,
          timezone: timezone,
        )
        .referenceNow;
  }

  DateTime? _parseDateTime(String raw) {
    if (raw.trim().isEmpty) {
      return null;
    }
    final parsed = DateTime.tryParse(raw.trim());
    if (parsed != null) {
      return parsed;
    }
    final dateOnly = RegExp(
      r'^(\d{4})-(\d{2})-(\d{2})$',
    ).firstMatch(raw.trim());
    if (dateOnly == null) {
      return null;
    }
    final year = int.tryParse(dateOnly.group(1) ?? '');
    final month = int.tryParse(dateOnly.group(2) ?? '');
    final day = int.tryParse(dateOnly.group(3) ?? '');
    if (year == null || month == null || day == null) {
      return null;
    }
    return DateTime(year, month, day);
  }

  bool _boolFromToolResults(
    List<Map<String, dynamic>> toolResults,
    String key,
  ) {
    for (final item in toolResults) {
      final data = AssistantToolResultRowView(item).dataPayload;
      if (data[key] == true) return true;
    }
    return false;
  }

  int _positiveIntFromToolResults(
    List<Map<String, dynamic>> toolResults,
    String key,
  ) {
    var maxValue = 0;
    for (final item in toolResults) {
      final data = AssistantToolResultRowView(item).dataPayload;
      final candidate = (data[key] as num?)?.toInt() ?? 0;
      if (candidate > maxValue) {
        maxValue = candidate;
      }
    }
    return maxValue;
  }

  List<String> _normalizedDimensions(List<String> values) {
    final seen = <String>{};
    final out = <String>[];
    for (final raw in values) {
      final normalized = raw.trim();
      if (normalized.isEmpty || !seen.add(normalized)) {
        continue;
      }
      out.add(normalized);
    }
    return out;
  }

  List<String> _missingDimensions({
    required List<String> requiredDimensions,
    required List<String> coveredDimensions,
  }) {
    final covered = coveredDimensions.map((item) => item.trim()).toSet();
    return requiredDimensions
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty && !covered.contains(item))
        .toSet()
        .toList(growable: false);
  }

  String _resolveStatus({
    required bool degraded,
    required bool terminalPayloadComplete,
    required bool evidenceRequired,
    required bool hasToolResult,
    required bool evidencePassed,
    required bool authoritySatisfied,
    required bool freshnessRequired,
    required bool freshnessKnown,
    required bool freshnessSatisfied,
    required bool timeWindowRequired,
    required bool timeWindowKnown,
    required bool timeWindowSatisfied,
    required List<String> missingDimensions,
  }) {
    if (degraded) return 'degraded';
    if (!terminalPayloadComplete) return 'incomplete';
    if (!evidenceRequired) {
      if (!authoritySatisfied) return 'need_more_evidence';
      if (freshnessRequired && (!freshnessKnown || !freshnessSatisfied)) {
        return 'need_more_evidence';
      }
      if (timeWindowRequired && (!timeWindowKnown || !timeWindowSatisfied)) {
        return 'need_more_evidence';
      }
      if (missingDimensions.isNotEmpty) return 'need_more_evidence';
      return 'ready';
    }
    if (!hasToolResult) return 'empty';
    if (!evidencePassed) return 'need_more_evidence';
    if (!authoritySatisfied) return 'need_more_evidence';
    if (freshnessRequired && (!freshnessKnown || !freshnessSatisfied)) {
      return 'need_more_evidence';
    }
    if (timeWindowRequired && (!timeWindowKnown || !timeWindowSatisfied)) {
      return 'need_more_evidence';
    }
    if (missingDimensions.isNotEmpty) return 'need_more_evidence';
    return 'ready';
  }

  RetrievalProcessingSnapshot? _parseRetrievalProcessing(Object? raw) {
    if (raw is! Map) {
      return null;
    }
    final json = raw.cast<String, Object?>();
    if (json.containsKey('processedDocumentCount') ||
        json.containsKey('acceptedDocumentCount') ||
        json.containsKey('acceptedReferences')) {
      return RetrievalProcessingSnapshot.fromJson(json);
    }
    final nested = (json['retrievalProcessing'] as Map?)
        ?.cast<String, Object?>();
    if (nested != null &&
        (nested.containsKey('processedDocumentCount') ||
            nested.containsKey('acceptedDocumentCount') ||
            nested.containsKey('acceptedReferences'))) {
      return RetrievalProcessingSnapshot.fromJson(nested);
    }
    return null;
  }

  EvidenceEvaluationResult _parseEvidenceEvaluation(
    Object? raw, {
    required List<EvidenceLedgerEntry> entries,
  }) {
    if (raw is Map) {
      final json = raw.cast<String, Object?>();
      return EvidenceEvaluationResult(
        entries: entries,
        coverageScore: (json['coverageScore'] as num?)?.toDouble() ?? 0.0,
        authorityScore: (json['authorityScore'] as num?)?.toDouble() ?? 0.0,
        relevanceScore: (json['relevanceScore'] as num?)?.toDouble() ?? 0.0,
        freshnessHours: (json['freshnessHours'] as num?)?.toInt() ?? 0,
        status: _parseEvidenceStatus((json['status'] as String?)?.trim() ?? ''),
        passed: json['passed'] == true,
        authoritySatisfied: json['authoritySatisfied'] == true,
        freshnessSatisfied: json['freshnessSatisfied'] == true,
        evidenceRequired: json['evidenceRequired'] == true,
        coveredDimensions:
            (json['coveredDimensions'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        coveredQueryTaskIds:
            (json['coveredQueryTaskIds'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        blockingDimensions:
            (json['blockingDimensions'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        missingDimensions:
            (json['missingDimensions'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        summary: (json['summary'] as String?)?.trim() ?? '',
      );
    }
    return const EvidenceEvaluationResult();
  }

  AnswerBoundaryPolicy _parseBoundaryPolicy(Object? raw) {
    if (raw is! Map) return const AnswerBoundaryPolicy();
    try {
      return AnswerBoundaryPolicy.fromJson(raw.cast<String, Object?>());
    } catch (_) {
      return const AnswerBoundaryPolicy();
    }
  }

  SynthesisReadinessResult? _parseSynthesisReadiness(Object? raw) {
    if (raw is! Map) return null;
    try {
      return SynthesisReadinessResult.fromJson(raw.cast<String, Object?>());
    } catch (_) {
      return null;
    }
  }

  List<QueryTask> _parseQueryTasks(Object? raw) {
    return QueryTask.normalizeList(raw);
  }

  List<Map<String, dynamic>> _toolResultsFromStructured(
    Map<String, dynamic> structured,
  ) {
    final domainResults =
        (structured['domainResults'] as Map?)?.cast<String, Object?>() ??
        const <String, Object?>{};
    return (domainResults['toolResults'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, Object?>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
  }

  bool _terminalPayloadComplete(Map<String, dynamic> structured) {
    final gate = (structured[assistantAnswerGateDecisionField] as Map?)
        ?.cast<String, Object?>();
    if (gate != null && gate.containsKey('terminalPayloadComplete')) {
      return gate['terminalPayloadComplete'] != false;
    }
    return true;
  }

  EvidenceStatus _parseEvidenceStatus(String raw) {
    return parseEvidenceStatus(raw);
  }

  String _firstNonEmpty(Iterable<String> candidates) {
    for (final raw in candidates) {
      final value = raw.trim();
      if (value.isNotEmpty) {
        return value;
      }
    }
    return '';
  }

  _StructuredTemporalReference _resolveStructuredTemporalReference(
    Map<String, dynamic> structured, {
    RunArtifacts? runArtifacts,
  }) {
    final topLevel =
        (structured['queryNormalization'] as Map?)?.cast<String, Object?>() ??
        const <String, Object?>{};
    final intentGraph = (structured['intentGraph'] as Map?)
        ?.cast<String, Object?>();
    final nested =
        (intentGraph?['queryNormalization'] as Map?)?.cast<String, Object?>() ??
        const <String, Object?>{};
    final diagnostics =
        (runArtifacts?.diagnostics.extensions['queryNormalization'] as Map?)
            ?.cast<String, Object?>() ??
        const <String, Object?>{};
    return _StructuredTemporalReference(
      referenceNowIso: _firstNonEmpty(<String>[
        (topLevel['referenceNowIso'] as String?) ?? '',
        (nested['referenceNowIso'] as String?) ?? '',
        (diagnostics['referenceNowIso'] as String?) ?? '',
      ]),
      timezone: _firstNonEmpty(<String>[
        (topLevel['timezone'] as String?) ?? '',
        (nested['timezone'] as String?) ?? '',
        (diagnostics['timezone'] as String?) ?? '',
      ]),
    );
  }
}

class _TemporalAssessment {
  const _TemporalAssessment({
    this.freshnessRequired = false,
    this.freshnessKnown = false,
    this.freshnessSatisfied = true,
    this.timeWindowRequired = false,
    this.timeWindowKnown = false,
    this.timeWindowSatisfied = true,
  });

  final bool freshnessRequired;
  final bool freshnessKnown;
  final bool freshnessSatisfied;
  final bool timeWindowRequired;
  final bool timeWindowKnown;
  final bool timeWindowSatisfied;

  bool get requirementSatisfied => timeWindowRequired
      ? (timeWindowKnown && timeWindowSatisfied)
      : (!freshnessRequired || freshnessSatisfied);
}

class _StructuredTemporalReference {
  const _StructuredTemporalReference({
    this.referenceNowIso = '',
    this.timezone = '',
  });

  final String referenceNowIso;
  final String timezone;
}
