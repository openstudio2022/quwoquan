import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/privacy_policy.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_router.dart';

class AssistentRetrievalService {
  AssistentRetrievalService({
    required AssistentRetrievalRouter router,
    required List<AssistentRetrievalProvider> providers,
  })  : _router = router,
        _providers = <String, AssistentRetrievalProvider>{
          for (final provider in providers) provider.providerId: provider,
        };

  final AssistentRetrievalRouter _router;
  final Map<String, AssistentRetrievalProvider> _providers;

  Future<AssistentRetrievalResult> retrieve(AssistentRetrievalRequest request) async {
    final policy = AssistentPrivacyPolicy.fromInputs(
      privacyProfile: request.privacyProfile,
      contextScopeHint: <String, dynamic>{
        ...request.contextScopeHint,
        'privacyPolicy': request.privacyPolicy,
      },
      fallbackCapabilities: request.requestedCapabilities,
    );
    final decision = _router.decide(
      request: request,
      providerCapabilities: <String, List<String>>{
        for (final entry in _providers.entries) entry.key: entry.value.capabilityIds,
      },
    );

    final allItems = <AssistentRetrievalItem>[];
    final providersUsed = <String>[];
    final roundTraces = <Map<String, dynamic>>[];
    var degraded = false;
    var errorCode = '';

    final rounds = decision.maxRounds < 1 ? 1 : decision.maxRounds;
    for (var round = 1; round <= rounds; round++) {
      var hasNewEvidence = false;
      final roundProviders = <String>[];
      var roundNewEvidence = 0;
      for (final providerId in decision.providerSequence) {
        if (!policy.allowsProvider(providerId)) continue;
        if (providerId == 'web' && !policy.allowsWebRound(round)) continue;
        final provider = _providers[providerId];
        if (provider == null) continue;
        final queryForRound = providerId == 'web'
            ? policy.sanitizeQueryForWeb(_queryForRound(request.query, round))
            : _queryForRound(request.query, round);
        final response = await provider.retrieve(
          AssistentRetrievalRequest(
            query: queryForRound,
            requestedCapabilities: decision.capabilitySequence,
            contextScopeHint: request.contextScopeHint,
            privacyProfile: request.privacyProfile,
            privacyPolicy: request.privacyPolicy,
            providerHint: request.providerHint,
            round: round,
            maxItems: request.maxItems,
          ),
        );
        providersUsed.add(providerId);
        roundProviders.add(providerId);
        if (response.items.isNotEmpty) {
          hasNewEvidence = true;
          roundNewEvidence += response.items.length;
          allItems.addAll(response.items);
        }
        degraded = degraded || response.degraded;
        if (!response.success && response.errorCode.isNotEmpty) {
          errorCode = response.errorCode;
        }
      }

      final deduped = _dedupeItems(allItems);
      final coverage = _coverageScore(deduped);
      final shouldStop = coverage >= 0.75 || !hasNewEvidence;
      roundTraces.add(<String, dynamic>{
        'round': round,
        'providers': roundProviders,
        'newEvidenceCount': roundNewEvidence,
        'coverageScore': coverage,
        'stopReason': shouldStop ? (coverage >= 0.75 ? 'coverage_enough' : 'no_new_evidence') : '',
      });
      if (shouldStop) {
      final message = deduped.isEmpty
          ? '检索未找到足够信息。'
          : '检索完成。';
        return AssistentRetrievalResult(
          success: deduped.isNotEmpty,
          message: message,
          items: deduped,
          providersUsed: providersUsed,
          coverageScore: coverage,
          conflictScore: _conflictScore(deduped),
          degraded: degraded,
          errorCode: errorCode,
          nextRoundRecommended: !shouldStop,
          queryPlan: <String, dynamic>{
            'providerSequence': decision.providerSequence,
            'capabilitySequence': decision.capabilitySequence,
            'maxRounds': rounds,
          },
          policyDecision: <String, dynamic>{
            'privacyProfile': request.privacyProfile,
            'webAccessMode': policy.webAccessMode,
            'redactBeforeWeb': policy.redactBeforeWeb,
            'decisionReasons': decision.decisionReasons,
          },
          roundTraces: roundTraces,
        );
      }
    }

    final deduped = _dedupeItems(allItems);
    return AssistentRetrievalResult(
      success: deduped.isNotEmpty,
      message: deduped.isEmpty ? '检索完成但信息不足。' : '检索达到轮次上限，返回当前最优结果。',
      items: deduped,
      providersUsed: providersUsed,
      coverageScore: _coverageScore(deduped),
      conflictScore: _conflictScore(deduped),
      degraded: degraded,
      errorCode: errorCode,
      nextRoundRecommended: false,
      queryPlan: <String, dynamic>{
        'providerSequence': decision.providerSequence,
        'capabilitySequence': decision.capabilitySequence,
        'maxRounds': rounds,
      },
      policyDecision: <String, dynamic>{
        'privacyProfile': request.privacyProfile,
        'webAccessMode': policy.webAccessMode,
        'redactBeforeWeb': policy.redactBeforeWeb,
        'decisionReasons': decision.decisionReasons,
      },
      roundTraces: roundTraces,
    );
  }

  String _queryForRound(String query, int round) {
    if (round <= 1) return query;
    if (query.contains('最新')) return query;
    return '$query 最新';
  }

  List<AssistentRetrievalItem> _dedupeItems(List<AssistentRetrievalItem> items) {
    final seen = <String>{};
    final result = <AssistentRetrievalItem>[];
    for (final item in items) {
      final key = '${item.sourceType}:${item.sourceId}:${item.content}';
      if (seen.contains(key)) continue;
      seen.add(key);
      result.add(item);
    }
    return result;
  }

  double _coverageScore(List<AssistentRetrievalItem> items) {
    if (items.isEmpty) return 0.0;
    if (items.length >= 4) return 1.0;
    return items.length / 4.0;
  }

  double _conflictScore(List<AssistentRetrievalItem> items) {
    if (items.isEmpty) return 1.0;
    return 0.0;
  }
}

