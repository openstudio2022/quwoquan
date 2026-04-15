import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_provider.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';

class AssistantDisplayProjection {
  const AssistantDisplayProjection({
    required this.markdown,
    required this.plainText,
    required this.summary,
  });

  final String markdown;
  final String plainText;
  final String summary;

  bool get hasRenderableContent =>
      markdown.trim().isNotEmpty || plainText.trim().isNotEmpty;
}

abstract final class AssistantDisplayTextResolver {
  static final RegExp _wrappedMarkdownFenceRe = RegExp(
    r'^```(?:md|markdown)\s*\r?\n([\s\S]*?)\r?\n```$',
    caseSensitive: false,
  );
  static final RegExp _leadingJsonFenceRe = RegExp(
    r'^```([a-zA-Z0-9_-]*)\s*\r?\n([\s\S]*?)\r?\n```',
  );
  static final RegExp _leadingAnswerBodyRe = RegExp(
    r'^(#{1,6}|[-*+]\s|\d+\.\s|>\s?|[A-Za-z\u4E00-\u9FFF])',
  );
  static final RegExp _internalFieldRe = RegExp(
    r'(assistant_turn|contractId|machineEnvelope|runArtifacts|queryTasks|queryVariants|tool_call|toolResult)',
  );
  static final RegExp _assistantProtocolFragmentRe = RegExp(
    r'(assistant_turn|contractId|machineEnvelope|runArtifacts|queryTasks|queryVariants|tool_call|toolResult|<tool_call>|</tool_call>)',
    caseSensitive: false,
  );
  static final RegExp _processOnlyFragmentRe = RegExp(
    r'(provider|freshnessHoursMax|timeScope|nextAction|finalAnswerReady|clarificationNeeded|needExpansion|phaseOneRoutingDiagnostics|modelCallCount|runModelCallCount|assistantElapsedMs|tokens?|模型调用|中间结果|\{\{[^}]+\}\}|已完成\s+\d+/\d+\s+步)',
    caseSensitive: false,
  );
  static final RegExp _technicalFailureFragmentRe = RegExp(
    r'(MissingPluginException|No implementation found|Local context failed|PlatformException|Exception:|Error:|channel\s+[a-z0-9_./-]+|method\s+[a-zA-Z0-9_]+|personalassistant/nativeapi|getLocalContext|[\w./-]+\.dart:\d+)',
    caseSensitive: false,
  );
  static final RegExp _internalPlannerNarrationFragmentRe = RegExp(
    r'(\{\{[^}]+\}\}|<tool_call>|</tool_call>|assistant_turn|contractId|runArtifacts)',
    caseSensitive: false,
  );
  static final RegExp _hardInternalProcessFragmentRe = RegExp(
    r'(provider|freshnessHoursMax|timeScope|nextAction|finalAnswerReady|clarificationNeeded|needExpansion|phaseOneRoutingDiagnostics|modelCallCount|runModelCallCount|assistantElapsedMs|tokens?|模型调用)',
    caseSensitive: false,
  );
  static final RegExp _reportStyleProcessFragmentRe = RegExp(
    r'(处理了\s*\d+\s*篇|检索了\s*\d+\s*条|交叉核对|信息已就位|收拢到\s*\d+\s*条)',
    caseSensitive: false,
  );
  static final RegExp _residualXmlToolFragmentRe = RegExp(
    r'</?<?(?:tool_call|function|parameter)[^>\n\r]*>?',
    caseSensitive: false,
  );
  static final RegExp _romanizedQueryLeakFragmentRe = RegExp(
    r'\b(?:[A-Z][a-z]+|[a-z]+)(?:\s+[a-z]+){1,7}\b',
  );
  static AssistantDisplayProjection projectTurn(AssistantTurnOutput turn) {
    final answerLike =
        turn.nextActionType == AssistantNextAction.answer &&
        turn.messageKindType != AssistantMessageKind.progress;
    final displayStateMarkdown = renderAnswerBlocksToMarkdown(
      turn.displayState.answer.blocks,
    );
    final displayStatePlainText = renderAnswerBlocksToPlainText(
      turn.displayState.answer.blocks,
    );
    final sanitizedMarkdown = stabilizeFinalAnswerMarkdown(
      normalizeMarkdown(turn.userMarkdown),
    );
    final fallbackMarkdown = answerLike
        ? stabilizeFinalAnswerMarkdown(normalizeMarkdown(turn.resultText))
        : '';
    final markdown = displayStateMarkdown.isNotEmpty
        ? displayStateMarkdown
        : sanitizedMarkdown.isNotEmpty
        ? sanitizedMarkdown
        : fallbackMarkdown;
    final sanitizedPlain = normalizePlainText(turn.resultText);
    final plainText = displayStatePlainText.isNotEmpty
        ? displayStatePlainText
        : sanitizedPlain.isNotEmpty
        ? sanitizedPlain
        : (markdown.isNotEmpty ? stripMarkdown(markdown) : '');
    final sanitizedSummary =
        normalizePlainText(turn.displayState.answer.summary).isNotEmpty
        ? normalizePlainText(turn.displayState.answer.summary)
        : normalizePlainText(turn.result.summary);
    return AssistantDisplayProjection(
      markdown: markdown,
      plainText: plainText,
      summary: sanitizedSummary.isNotEmpty ? sanitizedSummary : plainText,
    );
  }

  static AssistantTurnOutput normalizeTurn(AssistantTurnOutput turn) {
    final projection = projectTurn(turn);
    return AssistantTurnOutput(
      contractId: turn.contractId,
      decision: turn.decision,
      messageKind: turn.messageKind,
      userMarkdown: projection.markdown,
      result: AssistantTurnResult(
        text: projection.plainText,
        summary: projection.summary,
        interpretation: turn.result.interpretation,
        actionHints: turn.result.actionHints,
      ),
      displayState: turn.displayState,
      evidence: turn.evidence,
      reasoningBasis: turn.reasoningBasis,
      selfCheck: turn.selfCheck,
      diagnostics: turn.diagnostics,
      modelSelfScore: turn.modelSelfScore,
      askUser: turn.askUser,
      toolCalls: turn.toolCalls,
      slotState: turn.slotState,
      subagentPlan: turn.subagentPlan,
      intentGraph: turn.intentGraph,
      skillRuns: turn.skillRuns,
      aggregationState: turn.aggregationState,
      journey: turn.journey,
      missingContextSlots: turn.missingContextSlots,
      fillGuidance: turn.fillGuidance,
      followupPrompt: turn.followupPrompt,
      phaseId: turn.phaseId,
      actionCode: turn.actionCode,
      reasonCode: turn.reasonCode,
      reasonShort: turn.reasonShort,
      sessionPreferenceFacts: turn.sessionPreferenceFacts,
      longTermPreferenceFacts: turn.longTermPreferenceFacts,
    );
  }

  static String normalizeCompletedDisplayCandidate(
    String raw, {
    bool allowJsonExtraction = true,
  }) {
    var text = raw.trim();
    if (text.isEmpty) return '';
    if (allowJsonExtraction && _looksStructuredCandidate(text)) {
      final extracted = extractDisplayMarkdownFromStructuredText(text);
      if (extracted.isNotEmpty && extracted != text) {
        return normalizeCompletedDisplayCandidate(
          extracted,
          allowJsonExtraction: false,
        );
      }
    }
    return stabilizeFinalAnswerMarkdown(normalizeMarkdown(text));
  }

  static String normalizeCompletedPlainTextCandidate(
    String raw, {
    bool allowJsonExtraction = true,
  }) {
    var text = raw.trim();
    if (text.isEmpty) return '';
    if (allowJsonExtraction && _looksStructuredCandidate(text)) {
      final extracted = extractPlainTextFromStructuredText(text);
      if (extracted.isNotEmpty && extracted != text) {
        return normalizeCompletedPlainTextCandidate(
          extracted,
          allowJsonExtraction: false,
        );
      }
    }
    final plain = normalizePlainText(text);
    if (plain.isNotEmpty) return plain;
    final markdown = normalizeMarkdown(text);
    if (markdown.isEmpty) return '';
    return stripMarkdown(markdown);
  }

  static String extractDisplayMarkdownFromStructuredText(String raw) {
    final parsed = LlmResponseParser.parse(raw);
    if (!parsed.ok || parsed.json == null) return '';
    final payload = parsed.json!;
    final turn = tryParseAssistantTurnOutput(payload);
    if (turn == null) return '';
    return projectTurn(turn).markdown;
  }

  static String extractPlainTextFromStructuredText(String raw) {
    final parsed = LlmResponseParser.parse(raw);
    if (!parsed.ok || parsed.json == null) return '';
    final payload = parsed.json!;
    final turn = tryParseAssistantTurnOutput(payload);
    if (turn == null) return '';
    return projectTurn(turn).plainText;
  }

  static String normalizeMarkdown(String raw) {
    var text = OpenAiCompatibleLlmProvider.stripXmlToolCalls(raw).trim();
    if (text.isEmpty) return '';
    text = text.replaceAll(_residualXmlToolFragmentRe, '').trim();
    text = _stripWrappedMarkdownEnvelope(text);
    text = _stripLeadingStructuredFragments(text);
    text = text.replaceAll(_residualXmlToolFragmentRe, '').trim();
    text = _stripWrappedMarkdownEnvelope(text).trim();
    if (text.isEmpty) return '';
    if (AssistantContentFilters.isJsonEnvelope(text) ||
        AssistantContentFilters.isProgressPlaceholder(text) ||
        AssistantContentFilters.isDegradedText(text)) {
      return '';
    }
    if (_internalFieldRe.hasMatch(text) && !_looksLikeAnswerBody(text)) {
      return '';
    }
    text = _normalizeMarkdownStructuralSpacing(text, aggressive: false);
    return text;
  }

  static String stabilizeStreamingMarkdownCandidate(String raw) {
    final text = raw.trimRight();
    if (text.isEmpty) return '';
    return _normalizeMarkdownStructuralSpacing(
      text,
      aggressive: false,
    ).trimRight();
  }

  static String stabilizeFinalAnswerMarkdown(String raw) {
    var text = raw.trim();
    if (text.isEmpty) return '';
    text = _normalizeMarkdownStructuralSpacing(text, aggressive: true);
    text = _demoteGenericMarkdownHeadings(text);
    text = _normalizeMarkdownStructuralSpacing(text, aggressive: true);
    text = text
        .replaceAll(RegExp(r'^\s*•\s*$', multiLine: true), '')
        .replaceAll(RegExp(r'\n{3,}'), '\n\n')
        .trim();
    return text;
  }

  static String normalizePlainText(String raw) {
    final markdown = normalizeMarkdown(raw);
    if (markdown.isEmpty) return '';
    return stripMarkdown(markdown);
  }

  static String _normalizeMarkdownStructuralSpacing(
    String raw, {
    required bool aggressive,
  }) {
    var text = raw.replaceAll('\r\n', '\n');
    text = text.replaceAllMapped(
      RegExp(r'(^|\n)(#{1,6})(?=[^\s#])', multiLine: true),
      (match) => '${match.group(1) ?? ''}${match.group(2) ?? ''} ',
    );
    text = text.replaceAllMapped(
      RegExp(r'([。！？!?：:])([ \t]*)(#{1,6}\s*)'),
      (match) => '${match.group(1) ?? ''}\n\n${match.group(3) ?? ''}',
    );
    text = text.replaceAllMapped(
      RegExp(r'(^|\n)(#{1,6})(?=[^\s#])', multiLine: true),
      (match) => '${match.group(1) ?? ''}${match.group(2) ?? ''} ',
    );
    text = text.replaceAllMapped(
      RegExp(r'([。！？!?：:])([ \t]*)(\d+)\.(?=\S)'),
      (match) => '${match.group(1) ?? ''}\n\n${match.group(3) ?? ''}. ',
    );
    text = text.replaceAllMapped(
      RegExp(r'([。！？!?：:])([ \t]*)(?:([-+•])|(\*(?!\*)))(?=\S)'),
      (match) => '${match.group(1) ?? ''}\n- ',
    );
    text = text.replaceAllMapped(
      RegExp(r'(^|\n)(?:([-+•])|(\*(?!\*)))(?=\S)', multiLine: true),
      (match) => '${match.group(1) ?? ''}- ',
    );
    text = text.replaceAllMapped(
      RegExp(r'(^|\n)(\d+)\.(?=\S)', multiLine: true),
      (match) => '${match.group(1) ?? ''}${match.group(2) ?? ''}. ',
    );
    if (aggressive) {
      text = text.replaceAllMapped(
        RegExp(r'^(\*\*.+\*\*)\n(?!\n)', multiLine: true),
        (match) => '${match.group(1) ?? ''}\n\n',
      );
    }
    return text.replaceAll(RegExp(r'\n{3,}'), '\n\n').trim();
  }

  static String _demoteGenericMarkdownHeadings(String markdown) {
    return markdown.replaceAllMapped(
      RegExp(r'^\s*#{1,6}\s*(.+?)\s*$', multiLine: true),
      (match) {
        final title = (match.group(1) ?? '').trim();
        if (title.isEmpty) {
          return '';
        }
        return '**$title**';
      },
    );
  }

  static bool containsInternalAssistantProtocolFragment(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return false;
    if (_assistantProtocolFragmentRe.hasMatch(text)) return true;
    final stripped = OpenAiCompatibleLlmProvider.stripXmlToolCalls(text).trim();
    if (stripped.isEmpty) {
      return text.contains('<tool_call') ||
          text.contains('<function') ||
          text.contains('<parameter');
    }
    return _assistantProtocolFragmentRe.hasMatch(stripped);
  }

  static bool containsInternalProcessFragment(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return false;
    return containsInternalAssistantProtocolFragment(text) ||
        _processOnlyFragmentRe.hasMatch(text) ||
        containsTechnicalFailureFragment(text);
  }

  static bool containsTechnicalFailureFragment(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return false;
    return _technicalFailureFragmentRe.hasMatch(text);
  }

  static bool containsInternalPlannerNarrationFragment(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return false;
    return _internalPlannerNarrationFragmentRe.hasMatch(text);
  }

  static String normalizeUserFacingProcessNarration(String raw) {
    final stripped = stripRomanizedQueryLeakSentences(raw);
    if (stripped.isEmpty) return '';
    var text = normalizeMarkdown(stripped);
    if (text.isEmpty) {
      text = normalizePlainText(stripped);
    }
    if (text.isEmpty) return '';
    if (RegExp(r'\{\{[^{}]+\}\}').hasMatch(text)) {
      return '';
    }
    if (_hardInternalProcessFragmentRe.hasMatch(text) ||
        _reportStyleProcessFragmentRe.hasMatch(text) ||
        containsInternalAssistantProtocolFragment(text) ||
        containsTechnicalFailureFragment(text) ||
        AssistantContentFilters.isJsonEnvelope(text) ||
        AssistantContentFilters.isDegradedText(text)) {
      return '';
    }
    if (text.startsWith('{') || text.startsWith('[')) {
      return '';
    }
    return text.trim();
  }

  static bool containsUnsafeDisplayProtocolLeak(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return false;
    return AssistantContentFilters.isJsonEnvelope(text) ||
        containsInternalAssistantProtocolFragment(text);
  }

  static bool isRenderableDisplayText(String raw) {
    final text = OpenAiCompatibleLlmProvider.stripXmlToolCalls(raw).trim();
    if (text.isEmpty) return false;
    return !AssistantContentFilters.isNotDisplayable(text) &&
        !containsUnsafeDisplayProtocolLeak(text) &&
        !containsTechnicalFailureFragment(text);
  }

  static bool _containsRomanizedQueryLeakFragment(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return false;
    return _romanizedQueryLeakFragmentRe.hasMatch(text);
  }

  static String stripRomanizedQueryLeakSentences(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return '';
    final preservedLines = <String>[];
    for (final rawLine in text.replaceAll('\r\n', '\n').split('\n')) {
      final line = rawLine.trim();
      if (line.isEmpty) {
        continue;
      }
      final sentenceMatches = RegExp(
        r'[^。！？!?]+[。！？!?]?',
      ).allMatches(line).toList();
      if (sentenceMatches.isEmpty) {
        if (!_containsRomanizedQueryLeakFragment(line)) {
          preservedLines.add(line);
        }
        continue;
      }
      final keptSentences = <String>[];
      for (final match in sentenceMatches) {
        final sentence = (match.group(0) ?? '').trim();
        if (sentence.isEmpty ||
            _containsRomanizedQueryLeakFragment(sentence) ||
            AssistantContentFilters.isDegradedText(sentence) ||
            containsInternalAssistantProtocolFragment(sentence) ||
            containsTechnicalFailureFragment(sentence)) {
          continue;
        }
        keptSentences.add(sentence);
      }
      final rebuilt = keptSentences.join('').trim();
      if (rebuilt.isNotEmpty) {
        preservedLines.add(rebuilt);
      }
    }
    return preservedLines.join('\n').trim();
  }

  static bool hasStructuredPrefixLeak(String raw) {
    final strippedXml = OpenAiCompatibleLlmProvider.stripXmlToolCalls(
      raw,
    ).trimLeft();
    if (strippedXml.isEmpty) return false;
    return _stripLeadingStructuredFragments(strippedXml) != strippedXml.trim();
  }

  static String stripMarkdown(String markdown) {
    final raw = markdown.trim();
    if (raw.isEmpty) return '';
    var text = raw
        .replaceAllMapped(
          RegExp(r'\[([^\]]+)\]\(([^)]+)\)'),
          (match) => match.group(1) ?? '',
        )
        .replaceAllMapped(RegExp(r'`([^`]+)`'), (match) => match.group(1) ?? '')
        .replaceAll(RegExp(r'^#{1,6}\s*', multiLine: true), '')
        .replaceAll(RegExp(r'^\s*[-*+]\s+', multiLine: true), '')
        .replaceAll(RegExp(r'^\s*\d+\.\s+', multiLine: true), '')
        .replaceAll('**', '')
        .replaceAll('__', '')
        .replaceAll('*', '')
        .replaceAll('_', '')
        .replaceAll('```', '')
        .replaceAll('|', ' ')
        .replaceAll(RegExp(r'\n{3,}'), '\n\n');
    final lines = text
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList(growable: false);
    text = lines.join('\n');
    return text.trim();
  }

  static String _stripWrappedMarkdownEnvelope(String text) {
    final match = _wrappedMarkdownFenceRe.firstMatch(text);
    if (match == null) {
      return text;
    }
    return (match.group(1) ?? '').trim();
  }

  static String _stripLeadingStructuredFragments(String raw) {
    var current = raw.trimLeft();
    for (var i = 0; i < 4; i++) {
      final strippedFence = _stripLeadingStructuredFence(current);
      if (strippedFence != null) {
        current = strippedFence.trimLeft();
        continue;
      }
      final strippedJson = _stripLeadingStructuredJsonValue(current);
      if (strippedJson != null) {
        current = strippedJson.trimLeft();
        continue;
      }
      break;
    }
    return current.trim();
  }

  static String? _stripLeadingStructuredFence(String text) {
    final match = _leadingJsonFenceRe.firstMatch(text);
    if (match == null || match.start != 0) return null;
    final language = (match.group(1) ?? '').trim().toLowerCase();
    if (language.isNotEmpty &&
        language != 'json' &&
        language != 'javascript' &&
        language != 'js' &&
        language != 'text') {
      return null;
    }
    final body = (match.group(2) ?? '').trim();
    final structuredValue = _tryDecodeStructuredValue(body);
    if (!_isStructuredLeakPayload(structuredValue)) {
      return null;
    }
    final remaining = text.substring(match.end).trimLeft();
    if (!_looksLikeAnswerBody(remaining)) {
      return null;
    }
    return remaining;
  }

  static String? _stripLeadingStructuredJsonValue(String text) {
    final trimmed = text.trimLeft();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
      return null;
    }
    final end = _firstCompleteStructuredValueEnd(trimmed);
    if (end < 0) return null;
    final prefix = trimmed.substring(0, end);
    final structuredValue = _tryDecodeStructuredValue(prefix);
    if (!_isStructuredLeakPayload(structuredValue)) {
      return null;
    }
    final remaining = trimmed.substring(end).trimLeft();
    if (!_looksLikeAnswerBody(remaining)) {
      return null;
    }
    return remaining;
  }

  static Object? _tryDecodeStructuredValue(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map || decoded is List) {
        return decoded;
      }
    } catch (_) {}
    return null;
  }

  static bool _isStructuredLeakPayload(Object? value) {
    if (value is Map) {
      return value.isNotEmpty;
    }
    if (value is List) {
      if (value.isEmpty) return false;
      return value.any((item) => item is Map || item is List);
    }
    return false;
  }

  static int _firstCompleteStructuredValueEnd(String text) {
    if (text.isEmpty) return -1;
    final start = text.codeUnitAt(0);
    if (start != 0x7B && start != 0x5B) {
      return -1;
    }
    final stack = <int>[start];
    var inString = false;
    var escaped = false;
    for (var i = 1; i < text.length; i++) {
      final codeUnit = text.codeUnitAt(i);
      if (inString) {
        if (escaped) {
          escaped = false;
          continue;
        }
        if (codeUnit == 0x5C) {
          escaped = true;
          continue;
        }
        if (codeUnit == 0x22) {
          inString = false;
        }
        continue;
      }
      if (codeUnit == 0x22) {
        inString = true;
        continue;
      }
      if (codeUnit == 0x7B || codeUnit == 0x5B) {
        stack.add(codeUnit);
        continue;
      }
      if (codeUnit != 0x7D && codeUnit != 0x5D) {
        continue;
      }
      if (stack.isEmpty) return -1;
      final open = stack.removeLast();
      if ((open == 0x7B && codeUnit != 0x7D) ||
          (open == 0x5B && codeUnit != 0x5D)) {
        return -1;
      }
      if (stack.isEmpty) {
        return i + 1;
      }
    }
    return -1;
  }

  static bool _looksStructuredCandidate(String text) =>
      text.startsWith('{') || text.startsWith('[') || text.startsWith('```');

  static bool _looksLikeAnswerBody(String text) {
    final trimmed = text.trimLeft();
    if (trimmed.isEmpty) return false;
    if (trimmed.startsWith('```') || trimmed.startsWith('`')) {
      return true;
    }
    return _leadingAnswerBodyRe.hasMatch(trimmed);
  }
}
