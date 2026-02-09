import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

class AssistantChatMessage {
  final String id;
  final String text;
  final bool isSelf;
  final DateTime timestamp;
  final String? contextId;
  final String? kind;
  final List<AssistantCard>? cards;

  const AssistantChatMessage({
    required this.id,
    required this.text,
    required this.isSelf,
    required this.timestamp,
    this.contextId,
    this.kind = 'text',
    this.cards,
  });
}

class AssistantCard {
  final String title;
  final String body;

  const AssistantCard({
    required this.title,
    required this.body,
  });
}

class AssistantChatStore {
  static final ValueNotifier<List<AssistantChatMessage>> messages =
      ValueNotifier<List<AssistantChatMessage>>([]);

  static void normalizeMessages() {
    final current = messages.value;
    if (current.isEmpty) return;
    final normalized = current
        .map(
          (m) => AssistantChatMessage(
            id: m.id,
            text: m.text,
            isSelf: m.isSelf,
            timestamp: m.timestamp,
            contextId: m.contextId,
            kind: m.kind ?? 'text',
            cards: m.cards,
          ),
        )
        .toList();
    messages.value = normalized;
  }

  static void ensureSummaryForContext({
    required String contextId,
    required String summaryText,
    required List<AssistantCard> cards,
  }) {
    final current = List<AssistantChatMessage>.from(messages.value);
    final hasSummary = current.isNotEmpty && current.last.contextId == contextId;
    if (hasSummary) return;
    current.add(
      AssistantChatMessage(
        id: _nextId(),
        text: summaryText,
        isSelf: false,
        timestamp: DateTime.now(),
        contextId: contextId,
        kind: 'summary_cards',
        cards: cards,
      ),
    );
    messages.value = current;
  }

  static void addUserMessage(String text) {
    final current = List<AssistantChatMessage>.from(messages.value);
    current.add(
      AssistantChatMessage(
        id: _nextId(),
        text: text,
        isSelf: true,
        timestamp: DateTime.now(),
      ),
    );
    messages.value = current;
  }

  static void addAssistantMessage(String text) {
    final current = List<AssistantChatMessage>.from(messages.value);
    current.add(
      AssistantChatMessage(
        id: _nextId(),
        text: text,
        isSelf: false,
        timestamp: DateTime.now(),
        kind: 'text',
      ),
    );
    messages.value = current;
  }

  static List<AssistantCard> buildSummaryCards() {
    return const [
      AssistantCard(
        title: UITextConstants.assistantCardHighlightsTitle,
        body: UITextConstants.assistantCardHighlightsBody,
      ),
      AssistantCard(
        title: UITextConstants.assistantCardCommentsTitle,
        body: UITextConstants.assistantCardCommentsBody,
      ),
      AssistantCard(
        title: UITextConstants.assistantCardRecommendationsTitle,
        body: UITextConstants.assistantCardRecommendationsBody,
      ),
    ];
  }

  static String buildSummary({
    required String contextId,
    required String title,
    required String caption,
  }) {
    if (title.isEmpty && caption.isEmpty) {
      return UITextConstants.assistantInitialSummaryNoContent;
    }
    final buffer = StringBuffer();
    buffer.write(UITextConstants.assistantInitialSummaryPrefix);
    if (title.isNotEmpty) {
      buffer.write('\n${UITextConstants.assistantInitialSummaryTitleLabel}$title');
    }
    if (caption.isNotEmpty) {
      buffer.write('\n${UITextConstants.assistantInitialSummaryCaptionLabel}$caption');
    }
    return buffer.toString();
  }

  static String _nextId() => DateTime.now().microsecondsSinceEpoch.toString();
}
