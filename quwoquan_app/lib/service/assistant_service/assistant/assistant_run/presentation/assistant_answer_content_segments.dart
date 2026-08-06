// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — Markdown card payload 是受校验的开放 JSON。
part of 'assistant_answer_content.dart';

class _MarkdownSegment {
  const _MarkdownSegment._({
    required this.content,
    required this.isCard,
    this.cardType = '',
    this.cardPayload = const <String, dynamic>{},
  });

  final String content;
  final bool isCard;
  final String cardType;
  final Map<String, dynamic> cardPayload;

  static const Set<String> _supportedCardTypes = <String>{
    'compare',
    'trend',
    'diagram',
  };

  factory _MarkdownSegment.text(String content) =>
      _MarkdownSegment._(content: content, isCard: false);

  factory _MarkdownSegment.hidden() =>
      const _MarkdownSegment._(content: '', isCard: false);

  factory _MarkdownSegment.card({
    required String cardType,
    required String payload,
  }) {
    final type = cardType.trim().toLowerCase();
    if (!_supportedCardTypes.contains(type)) {
      return _MarkdownSegment.hidden();
    }
    final decoded = _tryDecode(payload);
    if (decoded == null || decoded.isEmpty) {
      return _MarkdownSegment.hidden();
    }
    return _MarkdownSegment._(
      content: payload,
      isCard: true,
      cardType: type,
      cardPayload: decoded,
    );
  }

  static List<_MarkdownSegment> parse(String raw) {
    if (!raw.contains('```card:')) {
      return <_MarkdownSegment>[
        _MarkdownSegment.text(raw.replaceAll('🔗[', '[')),
      ];
    }
    final sanitizedRaw = _stripDanglingCardFence(raw.replaceAll('🔗[', '['));
    final regex = RegExp(r'```card:([a-zA-Z0-9_-]+)\n([\s\S]*?)```');
    final segments = <_MarkdownSegment>[];
    var index = 0;
    for (final match in regex.allMatches(sanitizedRaw)) {
      if (match.start > index) {
        segments.add(
          _MarkdownSegment.text(sanitizedRaw.substring(index, match.start)),
        );
      }
      final type = (match.group(1) ?? '').trim();
      final payload = (match.group(2) ?? '').trim();
      segments.add(_MarkdownSegment.card(cardType: type, payload: payload));
      index = match.end;
    }
    if (index < sanitizedRaw.length) {
      segments.add(_MarkdownSegment.text(sanitizedRaw.substring(index)));
    }
    return segments.where((seg) => seg.content.trim().isNotEmpty).toList();
  }

  static String _stripDanglingCardFence(String raw) {
    final start = raw.indexOf('```card:');
    if (start < 0) return raw;
    final end = raw.indexOf('```', start + 8);
    if (end >= 0) return raw;
    return raw.substring(0, start).trimRight();
  }

  String toCardMarkdown() {
    if (!isCard || cardPayload.isEmpty) return content;
    final title = (cardPayload['title'] as String?)?.trim();
    final lines = <String>[
      '### ${title?.isNotEmpty == true ? title! : _fallbackTitle()}',
    ];
    if (cardType == 'diagram') {
      final mermaid = (cardPayload['mermaid'] as String?)?.trim() ?? '';
      if (mermaid.isNotEmpty) {
        lines
          ..add('```mermaid')
          ..add(mermaid)
          ..add('```');
      }
    }
    cardPayload.forEach((key, value) {
      if (key == 'title' || key == 'mermaid') return;
      lines.add('- **$key**: ${_valueText(value)}');
    });
    return lines.join('\n');
  }

  String _fallbackTitle() {
    switch (cardType) {
      case 'compare':
        return AssistantText.assistantCardCompare;
      case 'trend':
        return AssistantText.assistantCardTrend;
      case 'diagram':
        return AssistantText.assistantCardDiagram;
      default:
        return cardType;
    }
  }

  static Map<String, dynamic>? _tryDecode(String payload) {
    try {
      final decoded = jsonDecode(payload);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return decoded.cast<String, dynamic>();
      return null;
    } catch (error, stackTrace) {
      developer.log(
        'assistant structured card payload could not be decoded',
        name: 'assistant.answer_content',
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  static String _valueText(Object? value) {
    if (value == null) return '';
    if (value is num || value is bool || value is String) {
      return value.toString();
    }
    return jsonEncode(value);
  }
}
