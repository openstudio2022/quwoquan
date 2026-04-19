import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';

class PreferenceFactService {
  const PreferenceFactService();

  List<PreferenceFact> collectPreferenceFactsFromMessages(
    List<Map<String, dynamic>> messages, {
    required List<PreferenceFact> Function(AssistantTurnOutput turn) selector,
  }) {
    final collected = <PreferenceFact>[];
    final seen = <String>{};
    for (final message in messages) {
      if ((message['role'] ?? '').toString() != 'assistant') continue;
      final turn = _tryParseAssistantTurn((message['content'] as String?) ?? '');
      if (turn == null) continue;
      for (final fact in selector(turn)) {
        final key = fact.factId.isNotEmpty
            ? fact.factId
            : '${fact.scope}:${fact.key}:${fact.value}';
        if (!seen.add(key)) continue;
        collected.add(fact);
      }
    }
    return collected;
  }

  List<PreferenceFact> buildSessionPreferenceFacts({
    required String problemClass,
    required int uiReferenceCount,
    String feedbackHint = '',
    String followupPrompt = '',
  }) {
    final now = DateTime.now().toIso8601String();
    final facts = <PreferenceFact>[
      PreferenceFact(
        factId: 'session_problem_class_$now',
        scope: 'session',
        key: 'problemClass',
        value: problemClass,
        source: 'assistant_pipeline_engine',
        createdAt: now,
      ),
      PreferenceFact(
        factId: 'session_reference_count_$now',
        scope: 'session',
        key: 'referenceCount',
        value: uiReferenceCount.toString(),
        source: 'assistant_pipeline_engine',
        createdAt: now,
      ),
    ];
    if (feedbackHint.trim().isNotEmpty) {
      facts.add(
        PreferenceFact(
          factId: 'session_feedback_$now',
          scope: 'session',
          key: 'feedbackHint',
          value: feedbackHint.trim(),
          source: 'context_scope_hint',
          createdAt: now,
        ),
      );
    }
    if (followupPrompt.trim().isNotEmpty) {
      facts.add(
        PreferenceFact(
          factId: 'session_followup_$now',
          scope: 'session',
          key: 'followupPrompt',
          value: followupPrompt.trim(),
          source: 'answer_payload',
          createdAt: now,
        ),
      );
    }
    return facts.where((item) => item.value.isNotEmpty).toList(growable: false);
  }

  List<PreferenceFact> buildLongTermPreferenceFacts({
    required Object? seedFactsRaw,
    required List<Map<String, dynamic>> emergedTagMaps,
    required List<PreferenceFact> sessionFacts,
  }) {
    final seedFacts = _normalizeFacts(seedFactsRaw);
    if (emergedTagMaps.isEmpty) {
      return seedFacts;
    }
    final now = DateTime.now().toIso8601String();
    return <PreferenceFact>[
      ...seedFacts,
      ...emergedTagMaps.map(
        (item) => PreferenceFact(
          factId: 'long_term_${item['tag'] ?? item['key'] ?? now}_$now',
          scope: 'long_term',
          key: (item['tag'] ?? item['key'] ?? '').toString(),
          value: (item['value'] ?? item['label'] ?? '').toString(),
          source: 'diagnostics.emergedTags',
          createdAt: now,
        ),
      ),
      ...sessionFacts
          .where((item) => item.key == 'feedbackHint')
          .map(
            (item) => PreferenceFact(
              factId: 'long_term_feedback_${item.factId}',
              scope: 'long_term',
              key: item.key,
              value: item.value,
              source: item.source,
              createdAt: item.createdAt,
            ),
          ),
    ]
        .where((item) => item.key.isNotEmpty && item.value.isNotEmpty)
        .toList(growable: false);
  }

  List<PreferenceFact> _normalizeFacts(Object? raw) {
    final items = (raw as List?) ?? const <dynamic>[];
    return items
        .whereType<Map>()
        .map((item) => PreferenceFact.fromJson(item.cast<String, dynamic>()))
        .toList(growable: false);
  }

  AssistantTurnOutput? _tryParseAssistantTurn(String raw) {
    if (raw.trimLeft().isEmpty || !raw.trimLeft().startsWith('{')) return null;
    final decoded = _jsonDecodeFirst(raw);
    if (decoded is! Map) return null;
    return tryParseAssistantTurnOutput(decoded.cast<String, dynamic>());
  }

  Object? _jsonDecodeFirst(String text) {
    try {
      return jsonDecode(text);
    } catch (_) {
      return null;
    }
  }
}
