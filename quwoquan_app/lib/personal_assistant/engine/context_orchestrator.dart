class ContextFillTask {
  const ContextFillTask({
    required this.fillType,
    required this.targetSlot,
    required this.reason,
    this.generatedQueryConditions = const <String>[],
    this.scopeExpansionPolicy = '',
    this.retryPolicy = 'single_retry',
  });

  final String fillType;
  final String targetSlot;
  final String reason;
  final List<String> generatedQueryConditions;
  final String scopeExpansionPolicy;
  final String retryPolicy;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'fillType': fillType,
      'targetSlot': targetSlot,
      'reason': reason,
      'generatedQueryConditions': generatedQueryConditions,
      'scopeExpansionPolicy': scopeExpansionPolicy,
      'retryPolicy': retryPolicy,
    };
  }
}

class ContextAssemblyResult {
  const ContextAssemblyResult({
    required this.contextEnvelope,
    required this.fillTasks,
    required this.canEnterDomain,
    required this.summaryText,
    this.hasRealtimeNeed = false,
    this.hasLongtermNeed = false,
  });

  final Map<String, dynamic> contextEnvelope;
  final List<ContextFillTask> fillTasks;
  final bool canEnterDomain;
  final String summaryText;
  final bool hasRealtimeNeed;
  final bool hasLongtermNeed;
}

class SynthesisReadinessResult {
  const SynthesisReadinessResult({
    required this.ready,
    required this.reason,
    this.gapFillTask,
  });

  final bool ready;
  final String reason;
  final ContextFillTask? gapFillTask;
}

class PersonalAssistantContextOrchestrator {
  const PersonalAssistantContextOrchestrator();

  ContextAssemblyResult assemble({
    required String query,
    required String historySummary,
    required List<String> recalledTexts,
    required String deviceProfile,
    required String deviceModel,
    required String deviceOs,
    required Map<String, dynamic> gpsLocation,
    required Map<String, dynamic> contextScopeHint,
  }) {
    final lowered = query.toLowerCase();
    final hasRealtimeNeed =
        _containsAny(lowered, _realtimeKeywords) || _containsAny(query, _realtimeKeywordsZh);
    final hasLongtermNeed =
        _containsAny(lowered, _longtermKeywords) || _containsAny(query, _longtermKeywordsZh);

    final lat = _numValue(gpsLocation['lat'] ?? contextScopeHint['lat']);
    final lng = _numValue(gpsLocation['lng'] ?? contextScopeHint['lng']);
    final city = _strValue(gpsLocation['city'] ?? contextScopeHint['city']);
    final precision = _strValue(
      gpsLocation['locationPrecision'] ?? contextScopeHint['locationPrecision'],
    );
    final locationTimestamp = _strValue(
      gpsLocation['locationTimestamp'] ?? contextScopeHint['locationTimestamp'],
    );
    final hasPreciseLocation = lat != null && lng != null;
    final hasCoarseLocation = city.isNotEmpty;

    final hasLongtermMemory = recalledTexts.isNotEmpty;
    final missingSlots = <String>[];
    final fillTasks = <ContextFillTask>[];

    if (hasRealtimeNeed && !hasPreciseLocation && !hasCoarseLocation) {
      missingSlots.add('gps_or_city_location');
      fillTasks.add(
        const ContextFillTask(
          fillType: 'context_fill',
          targetSlot: 'gps_or_city_location',
          reason: '该问题涉及实时本地信息，需要 GPS 或城市位置信息。',
          generatedQueryConditions: <String>['定位授权', '城市名称'],
          scopeExpansionPolicy: 'fallback_city_level',
        ),
      );
    }
    if (hasLongtermNeed && !hasLongtermMemory) {
      missingSlots.add('longterm_memory');
      fillTasks.add(
        ContextFillTask(
          fillType: 'context_fill',
          targetSlot: 'longterm_memory',
          reason: '该问题涉及长期历史回顾，需要补齐长期记忆检索结果。',
          generatedQueryConditions: <String>[query],
          scopeExpansionPolicy: 'expand_time_window',
        ),
      );
    }

    final contextEnvelope = <String, dynamic>{
      'sourceStatus': <String, dynamic>{
        'historySummary': historySummary.isNotEmpty ? 'ready' : 'empty',
        'longtermMemory': hasLongtermMemory ? 'ready' : 'missing',
        'location': hasPreciseLocation
            ? 'precise'
            : (hasCoarseLocation ? 'coarse' : 'missing'),
      },
      'freshness': <String, dynamic>{
        'locationTimestamp': locationTimestamp,
      },
      'confidence': <String, dynamic>{
        'locationConfidence': hasPreciseLocation
            ? 'high'
            : (hasCoarseLocation ? 'medium' : 'low'),
        'memoryConfidence': hasLongtermMemory ? 'medium' : 'low',
      },
      'missingSlots': missingSlots,
      'deviceProfile': <String, dynamic>{
        'deviceProfile': deviceProfile,
        'deviceModel': deviceModel,
        'deviceOs': deviceOs,
      },
      'gpsLocation': <String, dynamic>{
        'lat': lat,
        'lng': lng,
        'city': city,
        'locationPrecision': precision,
        'locationTimestamp': locationTimestamp,
      },
      'longtermMemorySummary': recalledTexts.take(3).join('\n'),
    };
    final summaryText =
        'ContextAssembly:\n'
        '- realtimeNeed: $hasRealtimeNeed\n'
        '- longtermNeed: $hasLongtermNeed\n'
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
    required ContextAssemblyResult contextAssembly,
  }) {
    final lowered = finalText.toLowerCase();
    if (contextAssembly.hasRealtimeNeed && !hasToolResult) {
      return const SynthesisReadinessResult(
        ready: false,
        reason: '实时问题未形成有效检索证据',
        gapFillTask: ContextFillTask(
          fillType: 'gap_fill',
          targetSlot: 'realtime_evidence',
          reason: '需要新增检索任务补齐实时证据。',
          generatedQueryConditions: <String>['改写查询', '扩大检索范围'],
          scopeExpansionPolicy: 'expand_scope_and_requery',
        ),
      );
    }
    if (_containsAny(lowered, _insufficientAnswerMarkers)) {
      return const SynthesisReadinessResult(
        ready: false,
        reason: '回答文本显示证据不足',
        gapFillTask: ContextFillTask(
          fillType: 'gap_fill',
          targetSlot: 'answer_sufficiency',
          reason: '需再次检索补齐关键依据后再汇总。',
          generatedQueryConditions: <String>['补充证据', '交叉验证'],
          scopeExpansionPolicy: 'expand_provider_and_time_window',
        ),
      );
    }
    return const SynthesisReadinessResult(ready: true, reason: 'ok');
  }

  bool _containsAny(String input, List<String> keywords) {
    for (final keyword in keywords) {
      if (input.contains(keyword)) return true;
    }
    return false;
  }

  String _strValue(Object? raw) => raw?.toString().trim() ?? '';

  double? _numValue(Object? raw) {
    if (raw is num) return raw.toDouble();
    final text = _strValue(raw);
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }

  static const List<String> _realtimeKeywords = <String>[
    'weather',
    'travel',
    'nearby',
    'traffic',
    'location',
    'today',
    'now',
  ];
  static const List<String> _realtimeKeywordsZh = <String>[
    '天气',
    '出行',
    '附近',
    '周边',
    '路况',
    '定位',
    '今天',
    '现在',
  ];
  static const List<String> _longtermKeywords = <String>[
    'history',
    'long term',
    'longterm',
    'previous',
    'last year',
    'months ago',
  ];
  static const List<String> _longtermKeywordsZh = <String>[
    '很久前',
    '以前',
    '之前',
    '历史',
    '上次',
    '去年',
  ];
  static const List<String> _insufficientAnswerMarkers = <String>[
    '信息不足',
    '证据不足',
    '无法确定',
    'need more data',
    'insufficient',
  ];
}
