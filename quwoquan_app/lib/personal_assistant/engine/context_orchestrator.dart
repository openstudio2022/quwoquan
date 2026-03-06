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
    final detectedCityFromQuery = _extractCityFromQuery(query);
    final cityFromContext = _strValue(gpsLocation['city'] ?? contextScopeHint['city']);
    final city = cityFromContext.isNotEmpty ? cityFromContext : detectedCityFromQuery;
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

    // 实时问题优先进入垂类流程：
    // 1) 问句中已有城市名时直接使用；
    // 2) 若无城市名，交由运行时先尝试本地定位/上下文获取，再失败时追问城市。
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

    // 从记忆文本中提取城市提及，用于 slotFillHints
    final recentCityMentions = _extractCityMentions(recalledTexts);

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
        'citySource': cityFromContext.isNotEmpty
            ? 'device_or_scope'
            : (detectedCityFromQuery.isNotEmpty ? 'user_query' : ''),
        'locationPrecision': precision,
        'locationTimestamp': locationTimestamp,
      },
      'longtermMemorySummary': recalledTexts.take(3).join('\n'),
      // LLM 槽位补全信号聚合：让模型在规划阶段自行判断槽位，不依赖规则提取
      // 包含 GPS、历史摘要、记忆城市提及，支持拼音/英文/口语输入的自动理解
      'slotFillHints': <String, dynamic>{
        'gpsCity': city,
        'gpsCityConfidence': hasPreciseLocation
            ? 'high'
            : (hasCoarseLocation ? 'medium' : 'none'),
        'gpsLat': lat,
        'gpsLng': lng,
        'recentCityMentions': recentCityMentions,
        'historySummarySnippet': historySummary.length > 150
            ? historySummary.substring(0, 150)
            : historySummary,
        'ruleExtractedCity': detectedCityFromQuery,
        'ruleExtractedCityConfidence': detectedCityFromQuery.isNotEmpty ? 'medium' : 'none',
        'slotFillInstruction':
            '请根据以上信号（gpsCity/gpsLat/gpsLng/recentCityMentions/historySummarySnippet）'
            '结合用户原始输入（含拼音/英文/口语）自动补全关键槽位（city/timeScope等）。'
            '若输入是拼音或英文，请识别其中文含义并填入对应槽位。'
            '若所有信号均无法确定某槽位，输出 slotFillAction=ask_user。',
      },
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

  String _extractCityFromQuery(String query) {
    final q = query.trim();
    if (q.isEmpty) return '';
    final m1 = RegExp(r'([\u4e00-\u9fa5]{2,8}(?:市|区|县)?)天气').firstMatch(q);
    if (m1 != null) {
      final city = (m1.group(1) ?? '').trim();
      if (_isLikelyCityToken(city)) return city;
    }
    final m2 = RegExp(r'([\u4e00-\u9fa5]{2,8}(?:市|区|县)?)').firstMatch(q);
    final city = (m2?.group(1) ?? '').trim();
    if (_isLikelyCityToken(city)) return city;
    return '';
  }

  bool _isLikelyCityToken(String token) {
    final t = token.trim();
    if (t.isEmpty) return false;
    if (_realtimeKeywordsZh.any((k) => t == k)) return false;
    const blocked = <String>{'明天', '后天', '今日', '昨日', '当地', '本地', '最近'};
    return !blocked.contains(t);
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
  /// 从记忆文本列表中提取城市名提及，作为 slotFillHints 的辅助信号。
  /// 仅做快速规则提取，结果最终由 LLM 判断是否可信。
  List<String> _extractCityMentions(List<String> texts) {
    final seen = <String>{};
    final result = <String>[];
    for (final text in texts) {
      final matches = RegExp(r'[\u4e00-\u9fa5]{2,6}(?:市|区|县|省)?').allMatches(text);
      for (final m in matches) {
        final token = m.group(0) ?? '';
        if (token.isEmpty) continue;
        if (_realtimeKeywordsZh.contains(token)) continue;
        if (_longtermKeywordsZh.contains(token)) continue;
        const noise = <String>{'明天', '后天', '今日', '昨日', '当地', '本地', '最近', '用户'};
        if (noise.contains(token)) continue;
        if (seen.contains(token)) continue;
        seen.add(token);
        result.add(token);
        if (result.length >= 5) break;
      }
      if (result.length >= 5) break;
    }
    return result;
  }

  static const List<String> _insufficientAnswerMarkers = <String>[
    '信息不足',
    '证据不足',
    '无法确定',
    'need more data',
    'insufficient',
  ];
}
