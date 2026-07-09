/// tagRef 契约路径 → 展示名的唯一换算处。
///
/// tagRef 是 `publish/tags` 契约树全路径（如 `Entity/地点/景区/5A景区`、
/// `Topic/地理/行政区/四川省/成都市/都江堰市`），展示名取最后一段叶子名；
/// UI 不得各自 split 复制第二套换算规则。
String tagRefDisplayLabel(String tagRef) {
  final segments = tagRef
      .split('/')
      .map((segment) => segment.trim())
      .where((segment) => segment.isNotEmpty)
      .toList(growable: false);
  return segments.isEmpty ? '' : segments.last;
}

/// 批量换算：保序去重、去空，供标签行直接消费。
List<String> tagRefDisplayLabels(Iterable<String> tagRefs) {
  final labels = <String>{};
  for (final ref in tagRefs) {
    final label = tagRefDisplayLabel(ref);
    if (label.isNotEmpty) {
      labels.add(label);
    }
  }
  return labels.toList(growable: false);
}
