import 'package:quwoquan_app/assistant/contracts/context_fill_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';

class PersonalAssistantContextOrchestrator {
  const PersonalAssistantContextOrchestrator();

  ContextContinuityPolicy buildContinuityPolicy({
    required String query,
    required List<Map<String, dynamic>> sessionHistory,
  }) {
    query.trim();
    final referenceQueries = _recentUserQueries(sessionHistory);
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
    final historySnippet =
        continuityPolicy.allowHistorySummary ? _truncateHistorySummary(historySummary) : '';
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
    final summaryText =
        'ContextAssembly:\n'
        '- realtimeNeed: $hasRealtimeNeed\n'
        '- longtermNeed: $hasLongtermNeed\n'
        '- continuityMode: ${continuityPolicy.continuityMode.wireName}\n'
        '- missingSlots: ${missingSlots.isEmpty ? 'none' : missingSlots.join(', ')}';
    return ContextAssemblyResult(
      contextEnvelope: contextEnvelope,
      fillTasks: fillTasks,
      canEnterDomain: missingSlots.isEmpty,
      summaryText: summaryText,
      hasRealtimeNeed: hasRealtimeNeed,
      hasLongtermNeed: hasLongtermNeed,
    );
  }

  SynthesisReadinessResult checkSynthesisReadiness({
    required String query,
    required String finalText,
    required bool hasToolResult,
    required String problemClass,
    required ContextAssemblyResult contextAssembly,
  }) {
    final _ = (query, finalText, problemClass);
    final requiresRealtimeEvidence = contextAssembly.hasRealtimeNeed;
    if (requiresRealtimeEvidence && !hasToolResult) {
      return const SynthesisReadinessResult(
        ready: false,
        reason: '实时问题未形成有效检索证据',
        gapFillTask: ContextFillTask(
          fillType: ContextFillType.gapFill,
          targetSlot: ContextTargetSlot.realtimeEvidence,
          reason: '需要新增检索任务补齐实时证据。',
          generatedQueryConditions: <String>['改写查询', '扩大检索范围'],
          scopeExpansionPolicy:
              ContextScopeExpansionPolicy.expandScopeAndRequery,
        ),
      );
    }
    return const SynthesisReadinessResult(ready: true, reason: 'ok');
  }

  String _strValue(Object? raw) => raw?.toString().trim() ?? '';

  double? _numValue(Object? raw) {
    if (raw is num) return raw.toDouble();
    final text = _strValue(raw);
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }

  List<String> _recentUserQueries(List<Map<String, dynamic>> sessionHistory) {
    final result = <String>[];
    for (final item in sessionHistory.reversed) {
      final role = _strValue(item['role']);
      if (role != 'user') continue;
      final content = _strValue(item['content']);
      if (content.isEmpty) continue;
      result.add(content);
      if (result.length >= 3) break;
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
