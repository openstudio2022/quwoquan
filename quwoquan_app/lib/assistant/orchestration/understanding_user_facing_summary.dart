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
  final focusPhrases = <String>[
    ...concernPoints.map(_sanitizeFocusPhrase).where((item) => item.isNotEmpty),
    ...queryTasks.map(_queryTaskFocusPhrase).where((item) => item.isNotEmpty),
  ].toSet().take(3).toList(growable: false);
  if (focusPhrases.isEmpty) {
    return '我会先把最影响判断的关键信息核清，再把能直接支撑回答的依据收拢。';
  }
  final joined = _joinChineseItems(focusPhrases);
  if (focusPhrases.length == 1) {
    return '我会先把$joined核清，再把能直接支撑回答的依据收拢。';
  }
  return '我会先把$joined这些直接影响判断的信息核清，再把能直接支撑回答的依据收拢。';
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
      .replaceAll(RegExp(r'^(需要|是否|有没有|怎么|如何|请问)\s*'), '')
      .replaceAll(RegExp(r'(相关资料|相关信息|资料|信息|数据|查询结果|检索结果)$'), '')
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
  final candidates = <String>[
    ...task.entityAnchors.map(_sanitizeFocusPhrase),
    _sanitizeFocusPhrase(task.label),
    _sanitizeFocusPhrase(task.dimensionLabel),
  ].where((item) => item.isNotEmpty).toList(growable: false);
  if (candidates.isEmpty) {
    return '';
  }
  return candidates.first;
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
