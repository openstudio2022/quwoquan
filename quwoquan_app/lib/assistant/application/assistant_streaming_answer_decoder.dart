import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';

enum AssistantStreamingAnswerPayloadKind {
  unknown,
  plainText,
  structuredEnvelope,
}

class AssistantStreamingAnswerDecoder {
  String _rawBuffer = '';
  String _visibleBuffer = '';
  String _xmlToolResidue = '';
  bool _insideXmlToolBlock = false;
  AssistantStreamingAnswerPayloadKind _payloadKind =
      AssistantStreamingAnswerPayloadKind.unknown;

  bool get hasVisibleContent => _visibleBuffer.trim().isNotEmpty;

  void reset() {
    _rawBuffer = '';
    _visibleBuffer = '';
    _xmlToolResidue = '';
    _insideXmlToolBlock = false;
    _payloadKind = AssistantStreamingAnswerPayloadKind.unknown;
  }

  String appendChunk(String rawChunk) {
    final strippedXml = _stripStreamingXmlToolArtifacts(rawChunk).trimRight();
    if (strippedXml.trim().isEmpty) return '';
    _rawBuffer = '$_rawBuffer$strippedXml';
    _updatePayloadKind();
    switch (_payloadKind) {
      case AssistantStreamingAnswerPayloadKind.structuredEnvelope:
        return _structuredAnswerDelta();
      case AssistantStreamingAnswerPayloadKind.plainText:
        return _answerDeltaFromCandidate(_rawBuffer);
      case AssistantStreamingAnswerPayloadKind.unknown:
        return '';
    }
  }

  void _updatePayloadKind() {
    if (_payloadKind ==
        AssistantStreamingAnswerPayloadKind.structuredEnvelope) {
      return;
    }
    final trimmed = _rawBuffer.trimLeft();
    if (trimmed.isEmpty) {
      _payloadKind = AssistantStreamingAnswerPayloadKind.unknown;
      return;
    }
    if (_looksLikeStructuredPayload(trimmed)) {
      _payloadKind = AssistantStreamingAnswerPayloadKind.structuredEnvelope;
      return;
    }
    final wrappedMarkdownBody = _wrappedMarkdownBodyIfPresent(_rawBuffer);
    if (wrappedMarkdownBody != null && wrappedMarkdownBody.isNotEmpty) {
      _payloadKind = AssistantStreamingAnswerPayloadKind.plainText;
      return;
    }
    if (_looksLikePotentialStructuredPrefix(trimmed)) {
      _payloadKind = AssistantStreamingAnswerPayloadKind.unknown;
      return;
    }
    _payloadKind = AssistantStreamingAnswerPayloadKind.plainText;
  }

  String _structuredAnswerDelta() {
    final raw = _rawBuffer.trim();
    if (raw.isEmpty) return '';
    final parsed = LlmResponseParser.parse(raw);
    if (parsed.ok && parsed.json != null) {
      final turn = tryParseAssistantTurnOutput(parsed.json!);
      if (turn == null) return '';
      if (turn.nextActionType != AssistantNextAction.answer) return '';
      if (turn.messageKindType == AssistantMessageKind.progress ||
          turn.messageKindType == AssistantMessageKind.askUser) {
        return '';
      }
      final projection = AssistantDisplayTextResolver.projectTurn(turn);
      final answerText = projection.markdown.isNotEmpty
          ? projection.markdown
          : projection.plainText;
      return _answerDeltaFromCandidate(answerText);
    }
    final nextAction = _extractLenientJsonStringField(raw, 'nextAction').trim();
    if (nextAction.isNotEmpty && nextAction != 'answer') return '';
    final messageKind = _extractLenientJsonStringField(
      raw,
      'messageKind',
    ).trim().toLowerCase();
    if (messageKind == 'progress' ||
        messageKind == 'ask_user' ||
        messageKind == 'tool_call' ||
        messageKind == 'clarify') {
      return '';
    }
    if (nextAction.isEmpty && messageKind.isEmpty) return '';
    final userMarkdown = _extractLenientJsonStringField(raw, 'userMarkdown');
    if (userMarkdown.isEmpty) return '';
    return _answerDeltaFromCandidate(userMarkdown);
  }

  String _answerDeltaFromCandidate(String candidate) {
    final visibleMarkdown = _sanitizeStreamingMarkdownCandidate(candidate);
    if (visibleMarkdown.isEmpty) {
      return '';
    }
    if (AssistantContentFilters.isJsonEnvelope(visibleMarkdown) ||
        AssistantContentFilters.isProgressPlaceholder(visibleMarkdown) ||
        AssistantContentFilters.isDegradedText(visibleMarkdown) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          visibleMarkdown,
        )) {
      return '';
    }
    final delta = _streamingVisibleDelta(
      previousVisible: _visibleBuffer,
      nextVisible: visibleMarkdown,
    );
    if (delta.isEmpty && visibleMarkdown == _visibleBuffer) {
      return '';
    }
    _visibleBuffer = visibleMarkdown;
    return delta;
  }

  String _streamingVisibleDelta({
    required String previousVisible,
    required String nextVisible,
  }) {
    if (nextVisible.isEmpty || nextVisible == previousVisible) {
      return '';
    }
    if (previousVisible.isEmpty) {
      return nextVisible;
    }
    if (nextVisible.startsWith(previousVisible)) {
      return nextVisible.substring(previousVisible.length);
    }
    if (nextVisible.length <= previousVisible.length) {
      return '';
    }
    return nextVisible.substring(previousVisible.length);
  }

  String _sanitizeStreamingMarkdownCandidate(String candidate) {
    if (candidate.trim().isEmpty) {
      return '';
    }
    final withoutWrapper = _stripLeadingStreamingMarkdownWrapper(candidate);
    if (withoutWrapper == null || withoutWrapper.isEmpty) {
      return '';
    }
    final stabilized =
        AssistantDisplayTextResolver.stabilizeStreamingMarkdownCandidate(
          withoutWrapper,
        );
    if (stabilized.isEmpty) {
      return '';
    }
    final trailingFenceStart = _trailingUnclosedFenceStart(stabilized);
    if (trailingFenceStart < 0) {
      return stabilized;
    }
    return stabilized.substring(0, trailingFenceStart);
  }

  String? _stripLeadingStreamingMarkdownWrapper(String text) {
    if (!text.startsWith('```')) {
      return text;
    }
    final lineBreakIndex = _firstLineBreakIndex(text);
    if (lineBreakIndex < 0) {
      final prefix = text.trimRight().toLowerCase();
      if ('```md'.startsWith(prefix) || '```markdown'.startsWith(prefix)) {
        return null;
      }
      return prefix == '```' ? null : text;
    }
    final openingLine = text.substring(0, lineBreakIndex).trim().toLowerCase();
    if (openingLine != '```md' && openingLine != '```markdown') {
      return text;
    }
    final nextLineStart =
        text.codeUnitAt(lineBreakIndex) == 0x0D &&
            lineBreakIndex + 1 < text.length &&
            text.codeUnitAt(lineBreakIndex + 1) == 0x0A
        ? lineBreakIndex + 2
        : lineBreakIndex + 1;
    return nextLineStart >= text.length ? '' : text.substring(nextLineStart);
  }

  String? _wrappedMarkdownBodyIfPresent(String text) {
    if (!text.startsWith('```')) return null;
    return _stripLeadingStreamingMarkdownWrapper(text);
  }

  int _firstLineBreakIndex(String text) {
    for (int i = 0; i < text.length; i++) {
      final codeUnit = text.codeUnitAt(i);
      if (codeUnit == 0x0A || codeUnit == 0x0D) {
        return i;
      }
    }
    return -1;
  }

  int _trailingUnclosedFenceStart(String text) {
    final fenceStarts = <int>[];
    var offset = 0;
    while (offset < text.length) {
      final index = text.indexOf('```', offset);
      if (index < 0) {
        break;
      }
      fenceStarts.add(index);
      offset = index + 3;
    }
    if (fenceStarts.length.isEven) {
      return -1;
    }
    return fenceStarts.last;
  }

  bool _looksLikeStructuredPayload(String raw) {
    final normalized = raw.trimLeft();
    if (normalized.isEmpty) return false;
    if (normalized.startsWith('{') ||
        normalized.startsWith('[') ||
        normalized.startsWith('```json') ||
        normalized.startsWith('```javascript') ||
        normalized.startsWith('```js')) {
      return true;
    }
    return AssistantContentFilters.isJsonEnvelope(normalized) ||
        _jsonEnvelopeFragmentRe.hasMatch(normalized) ||
        _jsonKeyFragmentRe.hasMatch(normalized) ||
        _jsonSyntaxOnlyRe.hasMatch(normalized) ||
        _containsXmlToolToken(normalized);
  }

  bool _looksLikePotentialStructuredPrefix(String raw) {
    final wrappedMarkdownBody = _wrappedMarkdownBodyIfPresent(raw);
    if (wrappedMarkdownBody != null && wrappedMarkdownBody.isNotEmpty) {
      return false;
    }
    final normalized = raw.trimLeft().toLowerCase();
    if (normalized.isEmpty) return false;
    if (_looksLikeStructuredPayload(raw)) return true;
    return _structuredPrefixCandidates.any(
      (prefix) =>
          prefix.startsWith(normalized) || normalized.startsWith(prefix),
    );
  }

  String _extractLenientJsonStringField(String raw, String fieldName) {
    final key = '"$fieldName"';
    final fieldIndex = raw.indexOf(key);
    if (fieldIndex < 0) return '';
    var cursor = fieldIndex + key.length;
    while (cursor < raw.length && _isWhitespaceCode(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || raw[cursor] != ':') return '';
    cursor += 1;
    while (cursor < raw.length && _isWhitespaceCode(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || raw[cursor] != '"') return '';
    cursor += 1;
    final buffer = StringBuffer();
    var escaped = false;
    while (cursor < raw.length) {
      final ch = raw[cursor];
      if (escaped) {
        switch (ch) {
          case 'n':
            buffer.write('\n');
            break;
          case 'r':
            buffer.write('\r');
            break;
          case 't':
            buffer.write('\t');
            break;
          case '"':
          case r'\':
          case '/':
            buffer.write(ch);
            break;
          case 'u':
            if (cursor + 4 < raw.length) {
              final hex = raw.substring(cursor + 1, cursor + 5);
              final codePoint = int.tryParse(hex, radix: 16);
              if (codePoint != null) {
                buffer.writeCharCode(codePoint);
                cursor += 4;
                break;
              }
            }
            break;
          default:
            buffer.write(ch);
            break;
        }
        escaped = false;
        cursor += 1;
        continue;
      }
      if (ch == r'\') {
        escaped = true;
        cursor += 1;
        continue;
      }
      if (ch == '"') {
        break;
      }
      buffer.write(ch);
      cursor += 1;
    }
    return buffer.toString();
  }

  bool _isWhitespaceCode(int codeUnit) {
    return codeUnit == 0x20 ||
        codeUnit == 0x0A ||
        codeUnit == 0x0D ||
        codeUnit == 0x09;
  }

  int _firstXmlToolTokenStart(String text, List<String> tokens) {
    final lower = text.toLowerCase();
    var best = -1;
    for (final token in tokens) {
      final idx = lower.indexOf(token);
      if (idx < 0) continue;
      if (best < 0 || idx < best) {
        best = idx;
      }
    }
    return best;
  }

  String? _xmlToolTokenAt(String text, int start, List<String> tokens) {
    if (start < 0) return null;
    final lower = text.toLowerCase();
    for (final token in tokens) {
      if (lower.startsWith(token, start)) {
        return token;
      }
    }
    return null;
  }

  int _trailingPartialXmlToolStart(String text) {
    final lower = text.toLowerCase();
    final lastLt = lower.lastIndexOf('<');
    if (lastLt < 0) return -1;
    final tail = lower.substring(lastLt);
    if (tail.contains('>')) return -1;
    for (final token in _xmlToolStreamingTokens) {
      if (token.startsWith(tail) || tail.startsWith(token)) {
        return lastLt;
      }
    }
    return -1;
  }

  String _stripStreamingXmlToolArtifacts(String chunk) {
    var remaining = '$_xmlToolResidue$chunk';
    _xmlToolResidue = '';
    if (remaining.isEmpty) return '';
    final visible = StringBuffer();
    while (remaining.isNotEmpty) {
      if (_insideXmlToolBlock) {
        final closeStart = _firstXmlToolTokenStart(
          remaining,
          _xmlToolStreamingCloseTokens,
        );
        if (closeStart < 0) {
          _xmlToolResidue = remaining;
          return visible.toString();
        }
        final closeEnd = remaining.indexOf('>', closeStart);
        if (closeEnd < 0) {
          _xmlToolResidue = remaining.substring(closeStart);
          return visible.toString();
        }
        remaining = remaining.substring(closeEnd + 1);
        _insideXmlToolBlock = false;
        continue;
      }
      final tagStart = _firstXmlToolTokenStart(
        remaining,
        _xmlToolStreamingTokens,
      );
      if (tagStart < 0) {
        final partialStart = _trailingPartialXmlToolStart(remaining);
        if (partialStart >= 0) {
          visible.write(remaining.substring(0, partialStart));
          _xmlToolResidue = remaining.substring(partialStart);
        } else {
          visible.write(remaining);
        }
        return visible.toString();
      }
      if (tagStart > 0) {
        visible.write(remaining.substring(0, tagStart));
      }
      final token = _xmlToolTokenAt(
        remaining,
        tagStart,
        _xmlToolStreamingTokens,
      );
      final tagEnd = remaining.indexOf('>', tagStart);
      if (tagEnd < 0) {
        _xmlToolResidue = remaining.substring(tagStart);
        if (token != null && _xmlToolStreamingOpenTokens.contains(token)) {
          _insideXmlToolBlock = true;
        }
        return visible.toString();
      }
      remaining = remaining.substring(tagEnd + 1);
      if (token != null && _xmlToolStreamingOpenTokens.contains(token)) {
        _insideXmlToolBlock = true;
      }
    }
    return visible.toString();
  }

  bool _containsXmlToolToken(String text) {
    final lower = text.toLowerCase();
    return _xmlToolStreamingTokens.any(lower.contains);
  }

  static final _jsonEnvelopeFragmentRe = RegExp(
    r'"?(contractId|assistant_turn|decision|toolPlan|nextAction|userMarkdown)"?\s*:',
  );
  static final _jsonKeyFragmentRe = RegExp(
    r'"?(contractId|decision|nextAction|toolPlan|'
    r'userMarkdown|messageKind|slotFillPlan|queryNormalization|'
    r'selfCheck|diagnostics|reasoningBasis|'
    r'queryTasks|contextSlots|subagentPlan|evidence|result|'
    r'confidence|reasoning|answerEligibility|missingCriticalSlots|'
    r'assistant_turn|provider|freshnessHoursMax|timeScope|queryVariants|'
    r'plan|answer|ask_user|tool_call)"?\s*:?',
  );
  static final _jsonSyntaxOnlyRe = RegExp(r'^[\s"{}:\[\],\\.]+$');
  static const List<String> _xmlToolStreamingOpenTokens = <String>[
    '<tool_call',
    '<function=',
    '<parameter=',
  ];
  static const List<String> _xmlToolStreamingCloseTokens = <String>[
    '</tool_call',
    '</function',
    '</parameter',
  ];
  static const List<String> _xmlToolStreamingTokens = <String>[
    '<tool_call',
    '<function=',
    '<parameter=',
    '</tool_call',
    '</function',
    '</parameter',
  ];
  static const List<String> _structuredPrefixCandidates = <String>[
    '{',
    '[',
    '```',
    '"',
    'contractversion',
    'assistant_turn',
    'decision',
    'nextaction',
    'usermarkdown',
    'messagekind',
    'querytasks',
    'queryvariants',
    'machineenvelope',
    'runartifacts',
    'tool_call',
    '<tool_call',
    '<function=',
    '<parameter=',
  ];
}
