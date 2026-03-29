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
