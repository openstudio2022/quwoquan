import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';

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
    this.targetObject = '',
    this.userJobToBeDone = '',
    this.hardConstraints = const <String>[],
    this.softConstraints = const <String>[],
    this.excludedScopes = const <String>[],
    this.freshnessNeed = '',
    this.answerShape = '',
    this.requiresExternalEvidence = false,
    this.entityAnchors = const <String>[],
    this.negativeKeywords = const <String>[],
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
  final String targetObject;
  final String userJobToBeDone;
  final List<String> hardConstraints;
  final List<String> softConstraints;
  final List<String> excludedScopes;
  final String freshnessNeed;
  final String answerShape;
  final bool requiresExternalEvidence;
  final List<String> entityAnchors;
  final List<String> negativeKeywords;

  ProblemClass get problemClassKind => parseProblemClass(problemClass);
  QueryIntent get queryIntentKind => parseQueryIntent(queryIntent);
  SkillMode get modeKind => parseSkillMode(mode);
  AnswerShape get answerShapeKind => parseAnswerShape(answerShape);
  FreshnessNeed get freshnessNeedKind => parseFreshnessNeed(freshnessNeed);

  Map<String, dynamic> toIntentPayload() => <String, dynamic>{
    'primaryDomainId': primaryDomainId,
    'secondaryDomains': secondaryDomains,
    'inferredMotive': inferredMotive,
    'problemClass': problemClass,
    'queryIntent': queryIntent,
    'mode': mode,
    'targetObject': targetObject,
    'userJobToBeDone': userJobToBeDone,
    'hardConstraints': hardConstraints,
    'softConstraints': softConstraints,
    'excludedScopes': excludedScopes,
    'freshnessNeed': freshnessNeed,
    'answerShape': answerShape,
    'requiresExternalEvidence': requiresExternalEvidence,
    'entityAnchors': entityAnchors,
    'negativeKeywords': negativeKeywords,
    'queryNormalization': <String, dynamic>{
      'normalizedQuery': normalizedQuery,
      'query': normalizedQuery,
      'entityAnchors': entityAnchors,
      'negativeKeywords': negativeKeywords,
      'answerShape': answerShape,
      'freshnessNeed': freshnessNeed,
      if (city.isNotEmpty) 'city': city,
    },
  };
}

/// DEPRECATED: RegExp/contains 语义推断应迁出 runtime，由 planner 输出 typed problemClass/queryIntent。
/// 见 [canonical_truth_sources.md]。
class DefaultProblemFramer {
  const DefaultProblemFramer();

  ProblemFrame frame(
    String query, {
    Map<String, dynamic> intentPayload = const <String, dynamic>{},
  }) {
    final normalized = _normalizeQuery(query);
    final queryNormalization =
        (intentPayload['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final queryIntent = _stringValue(intentPayload['queryIntent']);
    final problemClass =
        _stringValue(intentPayload['problemClass']).isNotEmpty
        ? _stringValue(intentPayload['problemClass'])
        : ProblemClass.general.wireName;
    final primaryDomainId =
        _stringValue(intentPayload['primaryDomainId']).isNotEmpty
        ? _stringValue(intentPayload['primaryDomainId'])
        : 'fallback_general_search';
    final targetObject =
        _stringValue(intentPayload['targetObject']).isNotEmpty
        ? _stringValue(intentPayload['targetObject'])
        : _inferTargetObject(normalized);
    final answerShape = _stringValue(intentPayload['answerShape']);
    final excludedScopes = _stringList(intentPayload['excludedScopes']).isNotEmpty
        ? _stringList(intentPayload['excludedScopes'])
        : _extractExcludedScopes(normalized);
    final requiresExternalEvidence = intentPayload['requiresExternalEvidence'] == true;
    final location = extractCity(normalized);
    final entityAnchors = _extractEntityAnchors(
      normalized,
      targetObject: targetObject,
      location: location,
    );
    final negativeKeywords = _stringList(intentPayload['negativeKeywords']).isNotEmpty
        ? _stringList(intentPayload['negativeKeywords'])
        : excludedScopes.toList(growable: false);
    final hardConstraints = _stringList(intentPayload['hardConstraints']);
    final softConstraints = _stringList(intentPayload['softConstraints']);
    final freshnessNeed = _stringValue(intentPayload['freshnessNeed']);
    return ProblemFrame(
      query: query,
      normalizedQuery: normalized,
      primaryDomainId: primaryDomainId,
      problemClass: problemClass,
      queryIntent: queryIntent,
      inferredMotive: _stringValue(intentPayload['inferredMotive']),
      mode: _stringValue(intentPayload['mode']).isNotEmpty
          ? _stringValue(intentPayload['mode'])
          : SkillMode.qa.wireName,
      city: _stringValue(queryNormalization['city']).isNotEmpty
          ? _stringValue(queryNormalization['city'])
          : location,
      secondaryDomains: _stringList(intentPayload['secondaryDomains']),
      targetObject: targetObject,
      userJobToBeDone: _stringValue(intentPayload['userJobToBeDone']),
      hardConstraints: hardConstraints,
      softConstraints: softConstraints,
      excludedScopes: excludedScopes,
      freshnessNeed: freshnessNeed,
      answerShape: answerShape,
      requiresExternalEvidence: requiresExternalEvidence,
      entityAnchors: _stringList(intentPayload['entityAnchors']).isNotEmpty
          ? _stringList(intentPayload['entityAnchors'])
          : entityAnchors,
      negativeKeywords: negativeKeywords,
    );
  }

  String extractCity(String text) {
    if (text.isEmpty) return '';
    final placeLikeMatches = RegExp(
      r'([\u4e00-\u9fffA-Za-z]{2,20}(?:市|区|县|镇|乡|村|街道|公园|景区|机场|车站|大厦|广场|口岸|山|湖|河|沟|湾|岛|草原))',
    ).allMatches(text);
    for (final match in placeLikeMatches) {
      final normalized = _normalizeLocationCandidate(match.group(1));
      if (normalized.isNotEmpty) return normalized;
    }
    final connectorMatch = RegExp(
      r'(?:在|去|到|从|围绕|关于|针对)\s*([\u4e00-\u9fffA-Za-z]{2,16})',
    ).firstMatch(text);
    if (connectorMatch != null) {
      return _normalizeLocationCandidate(connectorMatch.group(1));
    }
    return '';
  }

  String _normalizeLocationCandidate(String? raw) {
    final candidate = (raw ?? '')
        .trim()
        .replaceFirst(RegExp(r'^(如果把|如果将|把|将|往|向|到|在|去|从|围绕|关于|针对)'), '')
        .replaceFirst(RegExp(r'(呢|呀|啊|吗|吧|吗？|\?)$'), '')
        .trim();
    if (candidate.length < 2 || candidate.length > 20) return '';
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
      '问题',
      '方案',
      '情况',
      '东西',
      '资料',
    };
    if (blocked.contains(candidate)) return '';
    if (RegExp(r'^(今天|明天|后天|这周|下周|周末|最近|当前|现在)').hasMatch(candidate)) {
      return '';
    }
    return candidate;
  }

  String _inferTargetObject(String normalized) {
    final quoted = RegExp(r'''["“'「]([^"”'」]{2,40})["”'」]''').firstMatch(
      normalized,
    );
    if (quoted != null) {
      final value = (quoted.group(1) ?? '').trim();
      if (value.isNotEmpty) return value;
    }
    final englishBrand = RegExp(r'\b([A-Za-z][A-Za-z0-9._-]{1,40})\b').firstMatch(
      normalized,
    );
    if (englishBrand != null) {
      return (englishBrand.group(1) ?? '').trim();
    }
    final stripped = normalized
        .replaceAll(
          RegExp(
            r'(帮我|请问|想问|想了解|想知道|能不能|是否|如果把|如果将|多给我|给我|关于|围绕|针对)',
          ),
          ' ',
        )
        .replaceAll(RegExp(r'[，。！？,.!?]'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    return stripped.isNotEmpty ? stripped : normalized;
  }

  List<String> _extractEntityAnchors(
    String normalized, {
    required String targetObject,
    required String location,
  }) {
    final anchors = <String>{};
    if (location.isNotEmpty) {
      anchors.add(location);
    }
    if (targetObject.isNotEmpty && targetObject != normalized) {
      anchors.add(targetObject);
    }
    final quotedMatches = RegExp(r'''["“'「]([^"”'」]{2,40})["”'」]''')
        .allMatches(normalized)
        .map((match) => (match.group(1) ?? '').trim())
        .where((item) => item.isNotEmpty);
    anchors.addAll(quotedMatches);
    final englishMatches = RegExp(r'\b([A-Za-z][A-Za-z0-9._-]{1,40})\b')
        .allMatches(normalized)
        .map((match) => (match.group(1) ?? '').trim())
        .where((item) => item.isNotEmpty);
    anchors.addAll(englishMatches);
    if (anchors.isEmpty && targetObject.isNotEmpty) {
      anchors.add(targetObject);
    }
    return anchors.toList(growable: false);
  }

  List<String> _extractExcludedScopes(String normalized) {
    final excluded = <String>{};
    final matches = <RegExpMatch>[
      ...RegExp(r'(?:不要|排除|去掉|不想要|别给我)\s*([^，。；;、]+)')
          .allMatches(normalized),
      ...RegExp(r'(?:而不是|不是)\s*([^，。；;、]+)').allMatches(normalized),
    ];
    for (final match in matches) {
      final raw = (match.group(1) ?? '').trim();
      if (raw.isEmpty) continue;
      final parts = raw
          .split(RegExp(r'[、,，/和或]'))
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty && item.length <= 20);
      excluded.addAll(parts);
    }
    return excluded.toList(growable: false);
  }

  String _stringValue(Object? raw) => raw?.toString().trim() ?? '';

  List<String> _stringList(Object? raw) {
    return (raw as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
  }

  String _normalizeQuery(String query) {
    return query
        .trim()
        .replaceAll(RegExp(r'\s+'), ' ')
        .replaceAll(RegExp(r'[“”]'), '"');
  }
}
