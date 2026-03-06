class SkillMarkdownParseResult {
  const SkillMarkdownParseResult({
    required this.frontmatter,
    required this.body,
  });

  final Map<String, dynamic> frontmatter;
  final String body;
}

class SkillMarkdownParser {
  const SkillMarkdownParser();

  SkillMarkdownParseResult parse(String raw) {
    final text = raw.replaceAll('\r\n', '\n');
    if (!text.startsWith('---\n')) {
      return SkillMarkdownParseResult(
        frontmatter: const <String, dynamic>{},
        body: text.trim(),
      );
    }
    final end = text.indexOf('\n---\n', 4);
    if (end < 0) {
      return SkillMarkdownParseResult(
        frontmatter: const <String, dynamic>{},
        body: text.trim(),
      );
    }
    final fmRaw = text.substring(4, end).trim();
    final body = text.substring(end + 5).trim();
    return SkillMarkdownParseResult(
      frontmatter: _parseFrontmatter(fmRaw),
      body: body,
    );
  }

  Map<String, dynamic> _parseFrontmatter(String raw) {
    final out = <String, dynamic>{};
    final lines = raw.split('\n');
    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
      final sep = trimmed.indexOf(':');
      if (sep <= 0) continue;
      final key = trimmed.substring(0, sep).trim();
      final valueRaw = trimmed.substring(sep + 1).trim();
      out[key] = _parseValue(valueRaw);
    }
    return out;
  }

  dynamic _parseValue(String raw) {
    if (raw.isEmpty) return '';
    if (raw.startsWith('[') && raw.endsWith(']')) {
      final inside = raw.substring(1, raw.length - 1).trim();
      if (inside.isEmpty) return const <String>[];
      return inside
          .split(',')
          .map((item) => _stripQuotes(item.trim()))
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return _stripQuotes(raw);
  }

  String _stripQuotes(String value) {
    final v = value.trim();
    if (v.length >= 2 &&
        ((v.startsWith('"') && v.endsWith('"')) ||
            (v.startsWith("'") && v.endsWith("'")))) {
      return v.substring(1, v.length - 1).trim();
    }
    return v;
  }
}
