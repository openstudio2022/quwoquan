import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_fill_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/continuity_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_gap_planner.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';

class PersonalAssistantContextOrchestrator {
  const PersonalAssistantContextOrchestrator();

  static const _continuityResolver = ContinuityResolver();
  static const _gapPlanner = ContextGapPlanner();
  static const _answerBoundaryResolver = AnswerBoundaryResolver();

  ContextContinuityPolicy buildContinuityPolicy({
    required String query,
    required List<Map<String, dynamic>> sessionHistory,
    int recentRoundsLimit = defaultRecentDialogueRoundsLimit,
  }) {
    query.trim();
    final referenceQueries = _recentUserQueries(
      sessionHistory,
      limit: recentRoundsLimit,
    );
    final typedHints = _continuityHintsFromHistory(sessionHistory);
    final continuityMode = parseContextContinuityMode(
      (typedHints['continuityMode'] as String?)?.trim() ?? '',
    );
    return ContextContinuityPolicy(
      queryIntent: (typedHints['queryIntent'] as String?)?.trim() ?? '',
      problemClass: (typedHints['problemClass'] as String?)?.trim() ?? '',
      continuityMode: continuityMode == ContextContinuityMode.unknown
          ? ContextContinuityMode.freshTopic
          : continuityMode,
      explicitContinuation: typedHints['explicitContinuation'] == true,
      topicOverlap: 0,
      allowHistorySummary: typedHints['allowHistorySummary'] == true,
      allowLongtermMemory: typedHints['allowLongtermMemory'] == true,
      allowLocationHints: typedHints['allowLocationHints'] == true,
      referenceQueries: referenceQueries,
    );
  }

  ContextAssemblyResult assemble({
    required String query,
    required String historySummary,
    required List<String> recalledTexts,
    required String deviceProfile,
    required String deviceModel,
    required String deviceOs,
    required Map<String, dynamic> gpsLocation,
    required Map<String, dynamic> contextScopeHint,
    required ContextContinuityPolicy continuityPolicy,
  }) {
    final typedProblemClass = _strValue(
      contextScopeHint['problemClass'] ?? continuityPolicy.problemClass,
    );
    final hasRealtimeNeed =
        contextScopeHint['requiresRealtimeEvidence'] == true ||
        parseProblemClass(typedProblemClass) == ProblemClass.realtimeInfo;
    final hasLongtermNeed =
        contextScopeHint['requiresLongtermMemory'] == true ||
        continuityPolicy.allowLongtermMemory;

    final lat = _numValue(gpsLocation['lat'] ?? contextScopeHint['lat']);
    final lng = _numValue(gpsLocation['lng'] ?? contextScopeHint['lng']);
    final cityFromContext = _strValue(
      gpsLocation['city'] ?? contextScopeHint['city'],
    );
    final precision = _strValue(
      gpsLocation['locationPrecision'] ?? contextScopeHint['locationPrecision'],
    );
    final locationTimestamp = _strValue(
      gpsLocation['locationTimestamp'] ?? contextScopeHint['locationTimestamp'],
    );
    final allowGpsSignals = continuityPolicy.allowLocationHints;
    final availableGeoContext = buildAvailableGeoContext(
      gpsLocation: _sanitizedGeoSignalsForAvailability(
        gpsLocation: gpsLocation,
        allowPreciseSignals: allowGpsSignals,
      ),
      scopeHint: contextScopeHint,
    );
    final historySnippet = continuityPolicy.allowHistorySummary
        ? _truncateHistorySummary(historySummary)
        : '';
    final continuityOverrideSlots =
        (contextScopeHint['continuityOverrideSlots'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final hasPreciseLocation = allowGpsSignals && lat != null && lng != null;
    final hasCoarseLocation = allowGpsSignals && cityFromContext.isNotEmpty;

    final hasLongtermMemory =
        continuityPolicy.allowLongtermMemory && recalledTexts.isNotEmpty;
    final missingSlots = <String>[];
    final fillTasks = <ContextFillTask>[];

    if (hasLongtermNeed && !hasLongtermMemory) {
      missingSlots.add('longterm_memory');
      fillTasks.add(
        ContextFillTask(
          fillType: ContextFillType.contextFill,
          targetSlot: ContextTargetSlot.longtermMemory,
          reason: '该问题涉及长期历史回顾，需要补齐长期记忆检索结果。',
          generatedQueryConditions: <String>[query],
          scopeExpansionPolicy: ContextScopeExpansionPolicy.expandTimeWindow,
        ),
      );
    }

    final slotFillHints = <String, dynamic>{
      'slotFillPolicy': _buildSlotFillPolicy(
        allowGpsSignals:
            allowGpsSignals &&
            (cityFromContext.isNotEmpty || lat != null || lng != null),
        allowHistorySummary: historySnippet.isNotEmpty,
      ),
    };
    if (allowGpsSignals && cityFromContext.isNotEmpty) {
      slotFillHints['gpsCity'] = cityFromContext;
      slotFillHints['gpsCityConfidence'] = hasPreciseLocation
          ? 'high'
          : (hasCoarseLocation ? 'medium' : 'none');
    }
    if (allowGpsSignals && lat != null) {
      slotFillHints['gpsLat'] = lat;
    }
    if (allowGpsSignals && lng != null) {
      slotFillHints['gpsLng'] = lng;
    }
    if (historySnippet.isNotEmpty) {
      slotFillHints['historySummarySnippet'] = historySnippet;
    }
    if (continuityOverrideSlots.isNotEmpty) {
      slotFillHints['continuityOverrideSlots'] = continuityOverrideSlots;
    }
    final gpsLocationEnvelope = <String, dynamic>{
      'locationPrecision': allowGpsSignals ? precision : '',
      'locationTimestamp': allowGpsSignals ? locationTimestamp : '',
    };
    if (allowGpsSignals && lat != null) {
      gpsLocationEnvelope['lat'] = lat;
    }
    if (allowGpsSignals && lng != null) {
      gpsLocationEnvelope['lng'] = lng;
    }
    if (allowGpsSignals && cityFromContext.isNotEmpty) {
      gpsLocationEnvelope['city'] = cityFromContext;
      gpsLocationEnvelope['citySource'] = 'device_or_scope';
    }

    final contextEnvelope = <String, dynamic>{
      'sourceStatus': <String, dynamic>{
        'historySummary': continuityPolicy.allowHistorySummary
            ? (historySnippet.isNotEmpty ? 'ready' : 'empty')
            : 'gated',
        'longtermMemory': continuityPolicy.allowLongtermMemory
            ? (hasLongtermMemory ? 'ready' : 'missing')
            : 'gated',
        'location': continuityPolicy.allowLocationHints
            ? (hasPreciseLocation
                  ? 'precise'
                  : (hasCoarseLocation ? 'coarse' : 'missing'))
            : 'suppressed',
      },
      'freshness': <String, dynamic>{
        'locationTimestamp': allowGpsSignals ? locationTimestamp : '',
      },
      'confidence': <String, dynamic>{
        'locationConfidence': continuityPolicy.allowLocationHints
            ? (hasPreciseLocation
                  ? 'high'
                  : (hasCoarseLocation ? 'medium' : 'low'))
            : 'suppressed',
        'memoryConfidence': continuityPolicy.allowLongtermMemory
            ? (hasLongtermMemory ? 'medium' : 'low')
            : 'suppressed',
      },
      'missingSlots': missingSlots,
      'continuityGate': continuityPolicy.toJson(),
      'typedSignals': <String, dynamic>{
        'problemClass': typedProblemClass,
        'requiresRealtimeEvidence': hasRealtimeNeed,
        'requiresLongtermMemory': hasLongtermNeed,
      },
      'availableGeoContext': availableGeoContext.toJson(),
      if (continuityOverrideSlots.isNotEmpty)
        'continuityOverrideSlots': continuityOverrideSlots,
      'deviceProfile': <String, dynamic>{
        'deviceProfile': deviceProfile,
        'deviceModel': deviceModel,
        'deviceOs': deviceOs,
      },
      'gpsLocation': gpsLocationEnvelope,
      if (hasLongtermMemory)
        'longtermMemorySummary': recalledTexts.take(3).join('\n'),
      // LLM 槽位补全信号聚合：仅保留结构化上下文，不再注入规则提取结果。
      'slotFillHints': slotFillHints,
    };
    RunArtifacts? runArtifacts;
    final runArtifactsRaw = contextScopeHint['runArtifacts'];
    if (runArtifactsRaw is Map) {
      runArtifacts = parseRunArtifacts(
        (runArtifactsRaw).cast<String, dynamic>(),
      );
    }

    if (runArtifacts != null) {
      final resolved = _continuityResolver.resolve(
        query: query,
        sessionHistory: const [],
        basePolicy: continuityPolicy,
        previousRunArtifacts: runArtifacts,
      );
      if (resolved.slotsToCarry.isNotEmpty) {
        final carried = <String, dynamic>{};
        for (final e in resolved.slotsToCarry.entries) {
          carried[e.key] = e.value.toJson();
        }
        slotFillHints['carriedSlotsFromPreviousRun'] = carried;
      }

      final preliminary = ContextAssemblyResult(
        contextEnvelope: contextEnvelope,
        fillTasks: fillTasks,
        canEnterDomain: missingSlots.isEmpty,
        summaryText: '',
        hasRealtimeNeed: hasRealtimeNeed,
        hasLongtermNeed: hasLongtermNeed,
      );
      final gapTasks = _gapPlanner.planGaps(
        resolvedContinuity: resolved,
        contextAssembly: preliminary,
        query: query,
        runArtifacts: runArtifacts,
        recalledTexts: recalledTexts,
      );
      for (final t in gapTasks) {
        if (!fillTasks.any(
          (f) => f.targetSlot == t.targetSlot && f.reason == t.reason,
        )) {
          fillTasks.add(t);
        }
      }
      if (slotFillHints.containsKey('carriedSlotsFromPreviousRun')) {
        contextEnvelope['carriedSlotsFromPreviousRun'] =
            slotFillHints['carriedSlotsFromPreviousRun'];
      }
    }

    final summaryText =
        'ContextAssembly:\n'
        '- realtimeNeed: $hasRealtimeNeed\n'
        '- longtermNeed: $hasLongtermNeed\n'
        '- continuityMode: ${continuityPolicy.continuityMode.wireName}\n'
        '- availableGeo: ${availableGeoContext.cityLabel.isNotEmpty ? availableGeoContext.cityLabel : (availableGeoContext.countryLabel.isNotEmpty ? availableGeoContext.countryLabel : 'none')}\n'
        '- missingSlots: ${missingSlots.isEmpty ? 'none' : missingSlots.join(', ')}';
    return ContextAssemblyResult(
      contextEnvelope: contextEnvelope,
      fillTasks: fillTasks,
      canEnterDomain: missingSlots.isEmpty,
      summaryText: summaryText,
      hasRealtimeNeed: hasRealtimeNeed,
      hasLongtermNeed: hasLongtermNeed,
      availableGeoContext: availableGeoContext,
    );
  }

  SynthesisReadinessResult checkSynthesisReadiness({
    required String query,
    required String finalText,
    required bool hasToolResult,
    required String problemClass,
    required ContextAssemblyResult contextAssembly,
    required IntentGraph intentGraph,
    required List<QueryTask> queryTasks,
    AnswerBoundaryPolicy? boundaryPolicy,
    EvidenceEvaluationResult? evidenceEvaluation,
  }) {
    final _ = (finalText, problemClass);
    final policy =
        boundaryPolicy ??
        _answerBoundaryResolver.resolve(
          intentGraph: intentGraph,
          contextAssembly: contextAssembly,
          retrievalPolicy: const <String, dynamic>{},
          queryTasks: queryTasks,
        );
    final generatedQueryConditions = queryTasks
        .map((task) => task.query.trim())
        .where((item) => item.isNotEmpty)
        .take(3)
        .toList(growable: false);
    if (policy.requireToolResultBeforeSynthesis && !hasToolResult) {
      return SynthesisReadinessResult(
        ready: false,
        reason: policy.summary.isNotEmpty ? policy.summary : '外部证据尚未形成。',
        replanTask: _buildEvidenceReplanTask(
          query: query,
          generatedQueryConditions: generatedQueryConditions,
          policy: policy,
        ),
      );
    }
    final evaluation = evidenceEvaluation;
    if (evaluation != null && evaluation.status == EvidenceStatus.retry) {
      final reason = evaluation.summary.trim().isNotEmpty
          ? evaluation.summary.trim()
          : (policy.summary.isNotEmpty ? policy.summary : '外部证据仍需继续补齐。');
      return SynthesisReadinessResult(
        ready: false,
        reason: reason,
        replanTask: _buildEvidenceReplanTask(
          query: query,
          generatedQueryConditions: generatedQueryConditions,
          policy: policy,
        ),
      );
    }
    if (policy.evidenceRequired) {
      final hasUsableEvidence =
          hasToolResult ||
          (evaluation != null && evaluation.entries.isNotEmpty);
      if (!hasUsableEvidence) {
        final reason = (evaluation?.summary.trim().isNotEmpty ?? false)
            ? evaluation!.summary.trim()
            : (policy.summary.isNotEmpty ? policy.summary : '外部证据尚未形成。');
        return SynthesisReadinessResult(
          ready: false,
          reason: reason,
          replanTask: _buildEvidenceReplanTask(
            query: query,
            generatedQueryConditions: generatedQueryConditions,
            policy: policy,
          ),
        );
      }
    }
    return const SynthesisReadinessResult(ready: true, reason: 'ok');
  }

  SlotStateSnapshot bindEvidenceToSlots({
    required SlotStateSnapshot slotState,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    if (slotState.slotValues.isEmpty || evidenceLedger.isEmpty) {
      return slotState;
    }
    final evidenceIdsBySlot = <String, List<String>>{};
    for (final entry in evidenceLedger) {
      final evidenceId = entry.evidenceId.trim();
      if (evidenceId.isEmpty) continue;
      for (final contribution in entry.slotContributions.entries) {
        final slotId = contribution.key.trim();
        final ids = evidenceIdsBySlot.putIfAbsent(slotId, () => <String>[]);
        if (!ids.contains(evidenceId)) {
          ids.add(evidenceId);
        }
      }
    }
    if (evidenceIdsBySlot.isEmpty) return slotState;
    var changed = false;
    final updatedSlotValues = <String, SlotValueSnapshot>{};
    for (final entry in slotState.slotValues.entries) {
      final fallbackSlotId = entry.key.trim();
      final snapshot = entry.value;
      final slotId = snapshot.slotId.trim().isNotEmpty
          ? snapshot.slotId.trim()
          : fallbackSlotId;
      final mergedEvidenceIds =
          _mergeEvidenceIds(snapshot.evidenceIds, <String>[
            ...(evidenceIdsBySlot[slotId] ?? const <String>[]),
            if (fallbackSlotId.isNotEmpty && fallbackSlotId != slotId)
              ...(evidenceIdsBySlot[fallbackSlotId] ?? const <String>[]),
          ]);
      final normalizedSnapshot =
          slotId != snapshot.slotId.trim() ||
              !_sameStringList(snapshot.evidenceIds, mergedEvidenceIds)
          ? snapshot.copyWith(slotId: slotId, evidenceIds: mergedEvidenceIds)
          : snapshot;
      changed = changed || !identical(normalizedSnapshot, snapshot);
      updatedSlotValues[entry.key] = normalizedSnapshot;
    }
    if (!changed) return slotState;
    return SlotStateSnapshot(
      domainId: slotState.domainId,
      slots: slotState.slots,
      slotValues: updatedSlotValues,
      missingSlots: slotState.missingSlots,
      updatedAt: slotState.updatedAt,
    );
  }

  ContextFillTask _buildEvidenceReplanTask({
    required String query,
    required List<String> generatedQueryConditions,
    required AnswerBoundaryPolicy policy,
  }) {
    return ContextFillTask(
      fillType: ContextFillType.replan,
      targetSlot: ContextTargetSlot.realtimeEvidence,
      reason: '需要先完成至少一轮证据检索，再进入最终成答。',
      generatedQueryConditions: generatedQueryConditions.isNotEmpty
          ? generatedQueryConditions
          : <String>[query],
      scopeExpansionPolicy: policy.expansionPolicy,
    );
  }

  List<String> _mergeEvidenceIds(List<String> existing, List<String> incoming) {
    final merged = <String>[];
    final seen = <String>{};
    for (final raw in <String>[...existing, ...incoming]) {
      final value = raw.trim();
      if (value.isEmpty || !seen.add(value)) continue;
      merged.add(value);
    }
    return merged;
  }

  bool _sameStringList(List<String> a, List<String> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }

  String _strValue(Object? raw) => raw?.toString().trim() ?? '';

  double? _numValue(Object? raw) {
    if (raw is num) return raw.toDouble();
    final text = _strValue(raw);
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }

  List<String> _recentUserQueries(
    List<Map<String, dynamic>> sessionHistory, {
    required int limit,
  }) {
    final rounds = buildRecentDialogueRounds(sessionHistory, limit: limit);
    final fromRounds = recentUserQueriesFromRounds(rounds);
    if (fromRounds.isNotEmpty) {
      return fromRounds;
    }
    final result = <String>[];
    for (final item in sessionHistory.reversed) {
      final role = _strValue(item['role']);
      if (role != 'user') continue;
      final content = _strValue(item['content']);
      if (content.isEmpty) continue;
      result.add(content);
      if (result.length >= limit) break;
    }
    return result;
  }

  String _truncateHistorySummary(String summary) {
    final trimmed = summary.trim();
    if (trimmed.isEmpty) return '';
    return trimmed.length > 150 ? trimmed.substring(0, 150) : trimmed;
  }

  Map<String, dynamic> _buildSlotFillPolicy({
    required bool allowGpsSignals,
    required bool allowHistorySummary,
  }) {
    return <String, dynamic>{
      'preferredSignals': <String>[
        'current_query',
        if (allowGpsSignals) 'gps_location',
        if (allowHistorySummary) 'history_summary',
      ],
      'normalizeCrossLingualValues': true,
      'missingSlotAction': 'ask_user',
    };
  }

  Map<String, dynamic> _sanitizedGeoSignalsForAvailability({
    required Map<String, dynamic> gpsLocation,
    required bool allowPreciseSignals,
  }) {
    final sanitized = Map<String, dynamic>.from(gpsLocation);
    if (allowPreciseSignals) {
      return sanitized;
    }
    sanitized.remove('lat');
    sanitized.remove('lng');
    for (final key in const <String>[
      'city',
      'cityLabel',
      'region',
      'regionLabel',
      'province',
      'district',
      'districtLabel',
      'country',
      'countryCode',
      'countryLabel',
    ]) {
      sanitized.remove(key);
    }
    final nested = (sanitized['location'] as Map?)?.cast<String, dynamic>();
    if (nested != null && nested.isNotEmpty) {
      sanitized['location'] = <String, dynamic>{
        ...nested,
      }..removeWhere(
          (key, _) =>
              key == 'lat' ||
              key == 'lng' ||
              key == 'latitude' ||
              key == 'longitude' ||
              key == 'lon' ||
              key == 'city' ||
              key == 'cityLabel' ||
              key == 'region' ||
              key == 'regionLabel' ||
              key == 'province' ||
              key == 'district' ||
              key == 'districtLabel',
        );
    }
    return sanitized;
  }

  Map<String, dynamic> _continuityHintsFromHistory(
    List<Map<String, dynamic>> sessionHistory,
  ) {
    for (final item in sessionHistory.reversed) {
      final continuity =
          (item['continuityPolicy'] as Map?)?.cast<String, dynamic>() ??
          (item['contextContinuity'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      if (continuity.isNotEmpty) {
        return continuity;
      }
    }
    return const <String, dynamic>{};
  }
}
