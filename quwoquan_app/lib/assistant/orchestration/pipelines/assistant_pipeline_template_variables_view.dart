import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_prompt_keys.dart';

class AssistantPipelineTemplateVariablesView {
  const AssistantPipelineTemplateVariablesView._(this._raw);

  const AssistantPipelineTemplateVariablesView.empty()
    : _raw = const <String, dynamic>{};

  factory AssistantPipelineTemplateVariablesView.fromMap(
    Map<String, dynamic> raw,
  ) {
    return AssistantPipelineTemplateVariablesView._(
      Map<String, dynamic>.from(raw),
    );
  }

  final Map<String, dynamic> _raw;

  String get currentRuntimeStateJson =>
      _string(AssistantPipelinePromptKeys.currentRuntimeState);

  Map<String, dynamic> get currentRuntimeStateMap =>
      _decodedMap(currentRuntimeStateJson);

  String get dialogueContinuityJson =>
      _string(AssistantPipelinePromptKeys.dialogueContinuity);

  Map<String, dynamic> get dialogueContinuityMap =>
      _decodedMap(dialogueContinuityJson);

  Map<String, dynamic> get dialogueStateMap => _mapValue(
    currentRuntimeStateMap[AssistantPipelinePromptKeys.dialogueState],
  );

  List<Map<String, dynamic>> get recentDialogueRounds {
    final raw = _raw[AssistantPipelinePromptKeys.recentDialogueRounds];
    if (raw is String && raw.trim().isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          return decoded
              .whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false);
        }
      } catch (_) {
        return const <Map<String, dynamic>>[];
      }
    }
    if (raw is List) {
      return raw
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
    }
    return const <Map<String, dynamic>>[];
  }

  ContextContinuityMode get continuityMode => parseContextContinuityMode(
    _stringFromMap(
      dialogueContinuityMap,
      AssistantPipelinePromptKeys.continuityMode,
    ),
  );

  SearchIterationState get searchIterationState {
    final raw = _raw[AssistantPipelinePromptKeys.searchIterationState];
    if (raw is String && raw.trim().isNotEmpty) {
      final parsed = jsonDecode(raw);
      if (parsed is Map) {
        return SearchIterationState.fromJson(parsed.cast<String, dynamic>());
      }
    }
    if (raw is Map) {
      return SearchIterationState.fromJson(raw.cast<String, dynamic>());
    }
    return const SearchIterationState();
  }

  bool get hasContinuationCarryoverContext {
    if (continuityMode == ContextContinuityMode.unknown ||
        continuityMode == ContextContinuityMode.freshTopic) {
      return false;
    }
    return true;
  }

  List<String> get requiredTopicAnchors {
    final seen = <String>{};
    final anchors = <String>[];

    void collect(Iterable<Object?> values) {
      for (final raw in values) {
        final value = raw.toString().trim();
        if (!_isMeaningfulTopicAnchor(value) || !seen.add(value)) {
          continue;
        }
        anchors.add(value);
      }
    }

    final directAnchors = _raw['entityRefs'];
    if (directAnchors is Iterable) {
      collect(directAnchors);
    } else if (directAnchors is String && directAnchors.trim().isNotEmpty) {
      collect(directAnchors.split(','));
    }

    final searchPlans = _raw['searchPlans'];
    if (searchPlans is Iterable) {
      for (final item in searchPlans) {
        if (item is Map) {
          final taskAnchors = item['entityRefs'];
          if (taskAnchors is Iterable) {
            collect(taskAnchors);
          } else if (taskAnchors is String && taskAnchors.trim().isNotEmpty) {
            collect(taskAnchors.split(','));
          }
        }
      }
    }

    return anchors;
  }

  Map<String, dynamic> _decodedMap(String rawJson) {
    if (rawJson.trim().isEmpty) {
      return const <String, dynamic>{};
    }
    try {
      final decoded = jsonDecode(rawJson);
      if (decoded is Map) {
        return decoded.cast<String, dynamic>();
      }
    } catch (_) {
      return const <String, dynamic>{};
    }
    return const <String, dynamic>{};
  }

  Map<String, dynamic> _mapValue(Object? raw) {
    if (raw is Map) {
      return raw.cast<String, dynamic>();
    }
    return const <String, dynamic>{};
  }

  String _string(String key) => (_raw[key] as String?)?.trim() ?? '';

  String _stringFromMap(Map<String, dynamic> map, String key) =>
      (map[key] as String?)?.trim() ?? '';

  bool _isMeaningfulTopicAnchor(String value) {
    final normalized = value.trim();
    if (normalized.length >= 2 &&
        RegExp(r'[\u4e00-\u9fff]').hasMatch(normalized)) {
      return true;
    }
    return normalized.length >= 3 &&
        RegExp(r'[A-Za-z0-9]').hasMatch(normalized);
  }
}
