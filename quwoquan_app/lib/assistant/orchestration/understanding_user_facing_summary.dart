import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';

String buildUnderstandingUserFacingSummary({
  required String intentSummary,
  String queryDesignSummary = '',
  List<String> concernPoints = const <String>[],
}) {
  final normalizedIntent = _normalizeSentence(intentSummary);
  final normalizedDesign = _normalizeSentence(queryDesignSummary);
  final focus = concernPoints
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .take(2)
      .join('、');
  if (normalizedIntent.isEmpty && normalizedDesign.isEmpty) {
    if (focus.isEmpty) {
      return '';
    }
    return '我会先围绕$focus把关键判断点核对清楚。';
  }
  final parts = <String>[
    if (normalizedIntent.isNotEmpty) normalizedIntent,
    if (normalizedDesign.isNotEmpty)
      normalizedDesign
    else if (focus.isNotEmpty)
      '我会先围绕$focus把关键信息核对清楚。',
  ];
  return parts.join('\n').trim();
}

String buildUnderstandingQueryDesignSummary({
  List<String> concernPoints = const <String>[],
  List<QueryTask> queryTasks = const <QueryTask>[],
}) {
  final focusPhrases = <String>{
    ...concernPoints.map(_sanitizeFocusPhrase).where((item) => item.isNotEmpty),
    ...queryTasks.map(_queryTaskFocusPhrase).where((item) => item.isNotEmpty),
  }.take(3).toList(growable: false);
  if (focusPhrases.isEmpty) {
    return '我会先把最影响判断的关键信息核清，再把能直接支撑回答的依据收拢。';
  }
  final joined = _joinChineseItems(focusPhrases);
  if (focusPhrases.length == 1) {
    return '我会先把$joined核清，再把能直接支撑回答的依据收拢。';
  }
  return '我会先把$joined这些直接影响判断的信息核清，再把能直接支撑回答的依据收拢。';
}

String deriveQueryTaskFocusLabel(QueryTask task) {
  final anchors = task.entityAnchors
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  final candidates = <String>[
    _sanitizeFocusPhrase(task.dimensionLabel),
    _focusPhraseFromSearchText(task.label, anchors: anchors),
    _focusPhraseFromSearchText(task.query, anchors: anchors),
    ...anchors.map(_sanitizeFocusPhrase),
  ].where((item) => item.isNotEmpty).toList(growable: false);
  if (candidates.isEmpty) {
    return '';
  }
  return candidates.first;
}

String deriveQueryTaskFocusReason(QueryTask task) {
  final reason = _focusPhraseFromSearchText(
    task.label,
    anchors: task.entityAnchors,
  );
  final label = deriveQueryTaskFocusLabel(task);
  final query = _focusPhraseFromSearchText(
    task.query,
    anchors: task.entityAnchors,
  );
  if (reason.isEmpty) {
    return '';
  }
  final normalizedReason = _normalizedFocusKey(reason);
  if (normalizedReason == _normalizedFocusKey(label) ||
      normalizedReason == _normalizedFocusKey(query)) {
    return '';
  }
  return reason;
}

String buildUnderstandingDetail(List<String> concernPoints) {
  return concernPoints
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .take(3)
      .join('\n');
}

String _normalizeSentence(String raw) {
  final text = raw.trim();
  if (text.isEmpty) {
    return '';
  }
  if (RegExp(r'[。！？!?]$').hasMatch(text)) {
    return text;
  }
  return '$text。';
}

String _sanitizeFocusPhrase(String raw) {
  final text = raw
      .trim()
      .replaceAll(RegExp(r'20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?'), ' ')
      .replaceAll(RegExp(r'\d{1,2}月\d{1,2}日'), ' ')
      .replaceAll(RegExp(r'\d{1,2}:\d{2}'), ' ')
      .replaceAll(RegExp(r'(今天|昨日|昨天|明天|后天|最近|当前|本周|上周|下周|周[一二三四五六日天])'), ' ')
      .replaceAll(RegExp(r'^(需要|是否|有没有|怎么|如何|请问)\s*'), '')
      .replaceAll(RegExp(r'(相关资料|相关信息|资料|信息|数据|查询结果|检索结果)$'), '')
      .replaceAll(RegExp(r'[\(\)（）【】\[\],，。；;:：/]+'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (text.isEmpty) {
    return '';
  }
  if (text.length > 20) {
    return text.substring(0, 20).trim();
  }
  return text;
}

String _queryTaskFocusPhrase(QueryTask task) {
  return deriveQueryTaskFocusLabel(task);
}

String _joinChineseItems(List<String> items) {
  if (items.isEmpty) {
    return '';
  }
  if (items.length == 1) {
    return items.first;
  }
  if (items.length == 2) {
    return '${items[0]}和${items[1]}';
  }
  return '${items[0]}、${items[1]}和${items[2]}';
}

String _focusPhraseFromSearchText(
  String raw, {
  List<String> anchors = const <String>[],
}) {
  var text = raw.trim();
  if (text.isEmpty) {
    return '';
  }
  text = text
      .replaceAll(
        RegExp(
          r'20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?(?:\s*至\s*20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?)?',
        ),
        ' ',
      )
      .replaceAll(RegExp(r'\d{1,2}月\d{1,2}日'), ' ')
      .replaceAll(RegExp(r'\d{1,2}:\d{2}'), ' ')
      .replaceAll(RegExp(r'(今天|昨日|昨天|明天|后天|最近|当前|本周|上周|下周|周[一二三四五六日天])'), ' ');
  final sortedAnchors =
      anchors
          .map((item) => item.trim())
          .where((item) => item.length >= 2)
          .toList(growable: false)
        ..sort((left, right) => right.length.compareTo(left.length));
  for (final anchor in sortedAnchors) {
    text = text.replaceAll(anchor, ' ');
  }
  final tokens = text
      .replaceAll(RegExp(r'[\(\)（）【】\[\],，。；;:：/]+'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim()
      .split(' ')
      .map((item) => item.trim())
      .where((item) => item.length >= 2 && !_isGenericSearchNoise(item))
      .toList(growable: false);
  if (tokens.isEmpty) {
    return _sanitizeFocusPhrase(text);
  }
  final selected = tokens.take(3).toList(growable: false);
  if (selected.length == 2 &&
      selected.every((item) => item.runes.length <= 4)) {
    return '${selected[0]}${selected[1]}';
  }
  return selected.join('、');
}

bool _isGenericSearchNoise(String token) {
  const genericTokens = <String>{
    '最新',
    '当前',
    '最近',
    '分析',
    '消息',
    '资讯',
    '情况',
    '数据',
    '结果',
    '最新消息',
    '相关',
  };
  return genericTokens.contains(token);
}

String _normalizedFocusKey(String raw) {
  return raw.replaceAll(RegExp(r'[\s、，。；;:：/]+'), '').trim().toLowerCase();
}
