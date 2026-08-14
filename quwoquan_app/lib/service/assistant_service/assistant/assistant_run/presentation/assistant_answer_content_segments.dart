part of 'assistant_answer_content.dart';

class _MarkdownSegment {
  const _MarkdownSegment._({
    required this.content,
    required this.isCard,
    this.cardType = '',
    this.cardPayload,
  });

  final String content;
  final bool isCard;
  final String cardType;
  final AssistantStructuredCardPayload? cardPayload;

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
    final decoded = AssistantStructuredCardPayload.tryParse(payload);
    if (decoded == null) {
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
    final payload = cardPayload;
    if (!isCard || payload == null) return content;
    final lines = <String>[
      '### ${payload.title.isNotEmpty ? payload.title : _fallbackTitle()}',
    ];
    if (cardType == 'diagram' && payload.mermaid.isNotEmpty) {
      lines
        ..add('```mermaid')
        ..add(payload.mermaid)
        ..add('```');
    }
    for (final entry in payload.entries) {
      lines.add('- **${entry.key}**: ${entry.valueText}');
    }
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
}
