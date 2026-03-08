import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/personal_assistant/engine/domain_routing_catalog_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/event_detection_catalog_runtime.dart';

class DialogueRoundScript {
  const DialogueRoundScript({
    required this.domainId,
    required this.enabled,
    required this.currentStateId,
    required this.detectedEvent,
    required this.suggestedNextStateId,
    required this.nextStateCandidates,
    required this.requiredFieldsForNextState,
    required this.totalSubTotalRequired,
    required this.optionalEnrichment,
    required this.maxQuestionsPerTurn,
    required this.hardFailCodes,
    required this.passCriteriaRound,
    required this.statePromptExcerpt,
    required this.stateMachineExcerpt,
    required this.routingCatalogVersion,
    required this.eventCatalogVersion,
  });

  final String domainId;
  final bool enabled;
  final String currentStateId;
  final String detectedEvent;
  final String suggestedNextStateId;
  final List<String> nextStateCandidates;
  final List<String> requiredFieldsForNextState;
  final bool totalSubTotalRequired;
  final bool optionalEnrichment;
  final int maxQuestionsPerTurn;
  final List<String> hardFailCodes;
  final Map<String, dynamic> passCriteriaRound;
  final String statePromptExcerpt;
  final String stateMachineExcerpt;
  final String routingCatalogVersion;
  final String eventCatalogVersion;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'domainId': domainId,
      'enabled': enabled,
      'currentStateId': currentStateId,
      'detectedEvent': detectedEvent,
      'suggestedNextStateId': suggestedNextStateId,
      'nextStateCandidates': nextStateCandidates,
      'requiredFieldsForNextState': requiredFieldsForNextState,
      'totalSubTotalRequired': totalSubTotalRequired,
      'optionalEnrichment': optionalEnrichment,
      'maxQuestionsPerTurn': maxQuestionsPerTurn,
      'hardFailCodes': hardFailCodes,
      'passCriteriaRound': passCriteriaRound,
      'statePromptExcerpt': statePromptExcerpt,
      'stateMachineExcerpt': stateMachineExcerpt,
      'routingCatalogVersion': routingCatalogVersion,
      'eventCatalogVersion': eventCatalogVersion,
    };
  }
}

class _DomainDialogueAssets {
  const _DomainDialogueAssets({
    required this.transitionContract,
    required this.statePrompts,
    required this.stateMachine,
  });

  final Map<String, dynamic> transitionContract;
  final String statePrompts;
  final String stateMachine;
}

class DialogueStateRuntime {
  DialogueStateRuntime({
    DomainRoutingCatalogRuntime? routingCatalogRuntime,
    EventDetectionCatalogRuntime? eventCatalogRuntime,
  }) : _routingCatalogRuntime =
           routingCatalogRuntime ?? DomainRoutingCatalogRuntime(),
       _eventCatalogRuntime =
           eventCatalogRuntime ?? EventDetectionCatalogRuntime();

  final Map<String, _DomainDialogueAssets> _cache =
      <String, _DomainDialogueAssets>{};
  final Map<String, Future<_DomainDialogueAssets?>> _loading =
      <String, Future<_DomainDialogueAssets?>>{};
  final DomainRoutingCatalogRuntime _routingCatalogRuntime;
  final EventDetectionCatalogRuntime _eventCatalogRuntime;

  Future<DialogueRoundScript> buildRoundScript({
    required String domainId,
    required String userQuery,
    required Map<String, dynamic> contextScopeHint,
    bool forceRefreshCatalog = false,
  }) async {
    await _routingCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    await _eventCatalogRuntime.ensureLoaded(forceRefresh: forceRefreshCatalog);
    if (forceRefreshCatalog) {
      _cache.clear();
      _loading.clear();
    }
    if (domainId.isEmpty || domainId == 'global') {
      return _fallbackScript(
        domainId: domainId,
        reasonState: 'S0_ENTRY_INTENT_CAPTURE',
      );
    }
    final assets = await _ensureDomainAssets(
      domainId: domainId,
      contextScopeHint: contextScopeHint,
    );
    if (assets == null) {
      return _fallbackScript(
        domainId: domainId,
        reasonState: 'S0_ENTRY_INTENT_CAPTURE',
      );
    }
    final contract = assets.transitionContract;
    final selectedRoutingCatalog = _routingCatalogRuntime
        .resolveCatalogForRequest(contextScopeHint);
    final selectedEventCatalog = _eventCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    final stateIds =
        (contract['stateIds'] as List?)?.whereType<String>().toList(
          growable: false,
        ) ??
        const <String>[];
    final currentStateId = _resolveCurrentState(
      contextScopeHint: contextScopeHint,
      allowedStateIds: stateIds,
    );
    final detectedEvent = _detectEvent(
      domainId: domainId,
      userQuery: userQuery,
      stateBefore: currentStateId,
      contextScopeHint: contextScopeHint,
    );
    final transitions =
        (contract['transitions'] as List?)?.whereType<Map>().toList(
          growable: false,
        ) ??
        const <Map>[];
    final nextStateCandidates = transitions
        .where((item) => (item['from']?.toString() ?? '') == currentStateId)
        .map((item) => (item['to']?.toString() ?? '').trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final suggestedNextStateId = _resolveNextState(
      transitions: transitions,
      currentStateId: currentStateId,
      detectedEvent: detectedEvent,
      fallback: nextStateCandidates.isNotEmpty
          ? nextStateCandidates.first
          : currentStateId,
    );
    final requiredFieldsByState =
        (contract['requiredFieldsByState'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final requiredFieldsForNextState =
        (requiredFieldsByState[suggestedNextStateId] as List?)
            ?.whereType<String>()
            .toList(growable: false) ??
        const <String>[];
    final globalRules =
        (contract['globalRules'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final enrichmentPolicy =
        (globalRules['enrichmentPolicy'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final optionalEnrichment = enrichmentPolicy['mustBeOptional'] == true;
    final maxQuestionsPerTurn =
        (enrichmentPolicy['maxQuestionsPerTurn'] as num?)?.toInt() ?? 2;
    final passCriteriaRound =
        ((contract['passCriteria'] as Map?)?['roundPass'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final hardFailCodes =
        (contract['hardFailCodes'] as List?)?.whereType<String>().toList(
          growable: false,
        ) ??
        const <String>[];
    return DialogueRoundScript(
      domainId: domainId,
      enabled: true,
      currentStateId: currentStateId,
      detectedEvent: detectedEvent,
      suggestedNextStateId: suggestedNextStateId,
      nextStateCandidates: nextStateCandidates,
      requiredFieldsForNextState: requiredFieldsForNextState,
      totalSubTotalRequired: true,
      optionalEnrichment: optionalEnrichment,
      maxQuestionsPerTurn: maxQuestionsPerTurn,
      hardFailCodes: hardFailCodes,
      passCriteriaRound: passCriteriaRound,
      statePromptExcerpt: _extractStateSection(
        markdown: assets.statePrompts,
        stateId: suggestedNextStateId,
      ),
      stateMachineExcerpt: _extractStateSection(
        markdown: assets.stateMachine,
        stateId: suggestedNextStateId,
      ),
      routingCatalogVersion: selectedRoutingCatalog.version,
      eventCatalogVersion: selectedEventCatalog.version,
    );
  }

  Future<_DomainDialogueAssets?> _ensureDomainAssets({
    required String domainId,
    required Map<String, dynamic> contextScopeHint,
  }) async {
    final selectedRoutingCatalog = _routingCatalogRuntime
        .resolveCatalogForRequest(contextScopeHint);
    final fallbackPath = 'assets/personal_assistant/skills/$domainId/dialogue';
    final selectedRule = selectedRoutingCatalog.rules.firstWhere(
      (rule) => rule.domainId == domainId,
      orElse: () => DomainRoutingRule(
        domainId: domainId,
        enabled: true,
        priority: 0,
        intentKeywords: const <String>[],
        dialoguePath: fallbackPath,
      ),
    );
    final basePath = selectedRule.dialoguePath.trim().isNotEmpty
        ? selectedRule.dialoguePath.trim()
        : fallbackPath;
    final cacheKey = '$domainId@$basePath';
    final cached = _cache[cacheKey];
    if (cached != null) return cached;
    _loading[cacheKey] ??= _loadDomainAssets(basePath);
    final loaded = await _loading[cacheKey];
    if (loaded != null) _cache[cacheKey] = loaded;
    return loaded;
  }

  Future<_DomainDialogueAssets?> _loadDomainAssets(String base) async {
    try {
      final transitionContractRaw = await _loadText(
        '$base/state_transition_contract.json',
      );
      final statePromptsRaw = await _loadText('$base/state_prompts.md');
      final stateMachineRaw = await _loadText('$base/state_machine.md');
      final decoded = jsonDecode(transitionContractRaw);
      if (decoded is! Map) return null;
      return _DomainDialogueAssets(
        transitionContract: decoded.cast<String, dynamic>(),
        statePrompts: statePromptsRaw,
        stateMachine: stateMachineRaw,
      );
    } catch (_) {
      return null;
    }
  }

  Future<String> _loadText(String path) async {
    try {
      return await rootBundle.loadString(path);
    } catch (_) {
      final file = File(path);
      if (await file.exists()) {
        return await file.readAsString();
      }
      rethrow;
    }
  }

  String _resolveCurrentState({
    required Map<String, dynamic> contextScopeHint,
    required List<String> allowedStateIds,
  }) {
    final dialogueHint =
        (contextScopeHint['dialogueState'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final fromHint = (dialogueHint['currentStateId'] as String?)?.trim() ?? '';
    if (fromHint.isNotEmpty && allowedStateIds.contains(fromHint)) {
      return fromHint;
    }
    final fromScope =
        (contextScopeHint['currentStateId'] as String?)?.trim() ?? '';
    if (fromScope.isNotEmpty && allowedStateIds.contains(fromScope)) {
      return fromScope;
    }
    return allowedStateIds.isNotEmpty
        ? allowedStateIds.first
        : 'S0_ENTRY_INTENT_CAPTURE';
  }

  String _resolveNextState({
    required List<Map> transitions,
    required String currentStateId,
    required String detectedEvent,
    required String fallback,
  }) {
    for (final item in transitions) {
      final from = (item['from']?.toString() ?? '').trim();
      final event = (item['event']?.toString() ?? '').trim();
      final to = (item['to']?.toString() ?? '').trim();
      if (from == currentStateId && event == detectedEvent && to.isNotEmpty) {
        return to;
      }
    }
    return fallback;
  }

  String _detectEvent({
    required String domainId,
    required String userQuery,
    required String stateBefore,
    required Map<String, dynamic> contextScopeHint,
  }) {
    final eventCatalog = _eventCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    final text = userQuery.trim();
    if (text.isEmpty) return eventCatalog.emptyTextEvent;
    final rules = <EventDetectionRule>[
      ...(eventCatalog.domainRules[domainId] ?? const <EventDetectionRule>[]),
      ...eventCatalog.globalRules,
    ]..sort((a, b) => b.priority.compareTo(a.priority));
    for (final rule in rules) {
      if (rule.stateBeforeIn.isNotEmpty &&
          !rule.stateBeforeIn.contains(stateBefore)) {
        continue;
      }
      if (_containsAny(text, rule.keywords)) {
        return rule.event;
      }
    }
    return eventCatalog.defaultEvent;
  }

  bool _containsAny(String source, List<String> candidates) {
    for (final item in candidates) {
      if (source.contains(item)) return true;
    }
    return false;
  }

  String _extractStateSection({
    required String markdown,
    required String stateId,
  }) {
    if (markdown.trim().isEmpty) return '';
    final patterns = <String>['## $stateId', '### $stateId'];
    int start = -1;
    for (final pattern in patterns) {
      start = markdown.indexOf(pattern);
      if (start >= 0) break;
    }
    if (start < 0) {
      return markdown.length <= 1200 ? markdown : markdown.substring(0, 1200);
    }
    final tail = markdown.substring(start);
    final match = RegExp(r'\n##\s+S[0-9A-Z_]+').firstMatch(tail.substring(1));
    if (match == null) {
      return tail.length <= 1200 ? tail : tail.substring(0, 1200);
    }
    final end = match.start + 1;
    final section = tail.substring(0, end);
    return section.length <= 1200 ? section : section.substring(0, 1200);
  }

  DialogueRoundScript _fallbackScript({
    required String domainId,
    required String reasonState,
  }) {
    return DialogueRoundScript(
      domainId: domainId,
      enabled: false,
      currentStateId: reasonState,
      detectedEvent: 'E_USER_QUERY_RECEIVED',
      suggestedNextStateId: reasonState,
      nextStateCandidates: const <String>[],
      requiredFieldsForNextState: const <String>[],
      totalSubTotalRequired: true,
      optionalEnrichment: true,
      maxQuestionsPerTurn: 2,
      hardFailCodes: const <String>[],
      passCriteriaRound: const <String, dynamic>{},
      statePromptExcerpt: '',
      stateMachineExcerpt: '',
      routingCatalogVersion: '',
      eventCatalogVersion: '',
    );
  }
}
