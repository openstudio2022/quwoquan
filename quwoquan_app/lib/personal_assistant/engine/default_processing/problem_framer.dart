class ProblemFrame {
  const ProblemFrame({
    required this.query,
    required this.normalizedQuery,
    required this.primaryDomainId,
    required this.problemClass,
    required this.queryIntent,
    required this.inferredMotive,
    this.mode = 'qa',
    this.city = '',
    this.secondaryDomains = const <String>[],
  });

  final String query;
  final String normalizedQuery;
  final String primaryDomainId;
  final String problemClass;
  final String queryIntent;
  final String inferredMotive;
  final String mode;
  final String city;
  final List<String> secondaryDomains;

  Map<String, dynamic> toIntentPayload() => <String, dynamic>{
    'primaryDomainId': primaryDomainId,
    'secondaryDomains': secondaryDomains,
    'inferredMotive': inferredMotive,
    'problemClass': problemClass,
    'queryIntent': queryIntent,
    'mode': mode,
    'queryNormalization': <String, dynamic>{
      'query': normalizedQuery,
      if (city.isNotEmpty) 'city': city,
    },
  };
}

class DefaultProblemFramer {
  const DefaultProblemFramer();

  ProblemFrame frame(String query) {
    final normalized = query.trim();
    final queryIntent = inferQueryIntent(normalized);
    final problemClass = inferProblemClassForIntent(queryIntent);
    final primaryDomainId = queryIntent == 'weather_now'
        ? 'weather'
        : 'fallback_general_search';
    return ProblemFrame(
      query: query,
      normalizedQuery: normalized,
      primaryDomainId: primaryDomainId,
      problemClass: problemClass,
      queryIntent: queryIntent,
      inferredMotive: _inferMotive(normalized, queryIntent),
      city: extractCity(normalized),
    );
  }

  String inferProblemClass(String query) {
    return inferProblemClassForIntent(inferQueryIntent(query));
  }

  String inferQueryIntent(String query) {
    if (query.isEmpty) return 'general_lookup';
    if (isWeatherLike(query)) return 'weather_now';
    if (isTravelAlternativeLike(query)) return 'travelAlternativeOptions';
    if (isWildlifeBestTimeLike(query)) return 'wildlifeBestTime';
    if (isStayLike(query)) return 'stayPlanning';
    return 'general_lookup';
  }

  String inferProblemClassForIntent(String queryIntent) {
    switch (queryIntent) {
      case 'weather_now':
        return 'realtime_info';
      case 'travelAlternativeOptions':
      case 'stayPlanning':
        return 'complex_reasoning';
      case 'wildlifeBestTime':
        return 'evidence_lookup';
      default:
        return 'simple_qa';
    }
  }

  bool isTravelAlternativeLike(String text) {
    if (text.isEmpty) return false;
    final hasAlternativeSignal = RegExp(
      r'(备选|备选方案|几个方案|多给我几个|替代|候选|方向考虑|方向算上|方向考虑进去)',
      caseSensitive: false,
    ).hasMatch(text);
    final hasTravelSignal = RegExp(
      r'(九寨沟|路线|行程|方向|玩法|方案)',
      caseSensitive: false,
    ).hasMatch(text);
    return hasAlternativeSignal && hasTravelSignal;
  }

  bool isWildlifeBestTimeLike(String text) {
    if (text.isEmpty) return false;
    final hasTimeSignal = RegExp(
      r'(最佳时间|什么时候|几月|季节|时段)',
      caseSensitive: false,
    ).hasMatch(text);
    final hasWildlifeSignal = RegExp(
      r'(土拨鼠|观赏|拍摄|野生动物)',
      caseSensitive: false,
    ).hasMatch(text);
    return hasTimeSignal && hasWildlifeSignal;
  }

  bool isWeatherLike(String text) {
    if (text.isEmpty) return false;
    return RegExp(
      r'(天气|气温|降雨|风力|体感|预报|weather|forecast|temperature|humidity|rain)',
      caseSensitive: false,
    ).hasMatch(text);
  }

  bool isStayLike(String text) {
    if (text.isEmpty) return false;
    return RegExp(
      r'(住宿|酒店|民宿|住哪|住哪里|行程|攻略|预算|性价比)',
      caseSensitive: false,
    ).hasMatch(text);
  }

  String extractCity(String text) {
    if (text.isEmpty) return '';
    final scopedMatch = RegExp(
      r'([\u4e00-\u9fa5]{2,8}?)(?:天气|气温|降雨|风力|体感|预报|住宿|酒店|民宿|行程|攻略|预算|方向|备选|方案|观赏|拍摄|最佳时间)',
    ).firstMatch(text);
    if (scopedMatch != null) {
      return _normalizeCityCandidate(scopedMatch.group(1));
    }
    final suffixMatch = RegExp(
      r'([\u4e00-\u9fa5]{2,8}(?:市|区|县))',
    ).firstMatch(text);
    if (suffixMatch != null) {
      return _normalizeCityCandidate(suffixMatch.group(1));
    }
    final scenicMatch = RegExp(
      r'([\u4e00-\u9fa5]{2,8}(?:沟|山|湖|草原|景区|国家公园))',
    ).firstMatch(text);
    if (scenicMatch != null) {
      return _normalizeCityCandidate(scenicMatch.group(1));
    }
    return '';
  }

  String _normalizeCityCandidate(String? raw) {
    final candidate = (raw ?? '')
        .trim()
        .replaceFirst(RegExp(r'^(如果把|如果将|把|将|往|向|到)'), '')
        .replaceFirst(RegExp(r'(呢|呀|啊|吗|吧)$'), '')
        .trim();
    if (candidate.length < 2 || candidate.length > 8) return '';
    const blocked = <String>{
      '今天',
      '明天',
      '后天',
      '现在',
      '当前',
      '最近',
      '这里',
      '那里',
      '这个',
      '那个',
      '天气',
      '行程',
      '住宿',
      '酒店',
      '民宿',
      '预算',
      '备选',
      '方案',
      '方向',
      '观赏',
      '拍摄',
      '最佳时间',
      '土拨鼠',
    };
    if (blocked.contains(candidate)) return '';
    if (RegExp(r'^(今天|明天|后天|这周|下周|周末|最近|当前|现在)').hasMatch(candidate)) {
      return '';
    }
    return candidate;
  }

  String _inferMotive(String normalized, String queryIntent) {
    if (normalized.isEmpty) return '用户希望获得帮助';
    switch (queryIntent) {
      case 'travelAlternativeOptions':
        return '用户希望比较九寨沟方向的多个备选方案，并知道各自更适合什么情况';
      case 'wildlifeBestTime':
        return '用户希望知道土拨鼠更容易观赏到的季节、时段和天气条件';
      case 'weather_now':
        return '用户希望拿到可直接用于判断出行的实时天气信息';
      case 'stayPlanning':
        return '用户希望把住宿与行程选择收敛成可执行建议';
      default:
        return '用户希望了解：$normalized';
    }
  }
}
