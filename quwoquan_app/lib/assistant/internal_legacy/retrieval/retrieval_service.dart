import 'dart:async';

import 'package:quwoquan_app/assistant/internal_legacy/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/assistant/internal_legacy/retrieval/privacy_policy.dart';
import 'package:quwoquan_app/assistant/internal_legacy/retrieval/retrieval_provider.dart';
import 'package:quwoquan_app/assistant/internal_legacy/retrieval/retrieval_router.dart';

class AssistantRetrievalService {
  AssistantRetrievalService({
    required AssistantRetrievalRouter router,
    required List<AssistantRetrievalProvider> providers,
  }) : _router = router,
       _providers = <String, AssistantRetrievalProvider>{
         for (final provider in providers) provider.providerId: provider,
       };

  final AssistantRetrievalRouter _router;
  final Map<String, AssistantRetrievalProvider> _providers;

  Future<AssistantRetrievalResult> retrieve(
    AssistantRetrievalRequest request,
  ) async {
    final policy = AssistantPrivacyPolicy.fromInputs(
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
        for (final entry in _providers.entries)
          entry.key: entry.value.capabilityIds,
      },
    );

    final allItems = <AssistantRetrievalItem>[];
    final providersUsed = <String>[];
    final roundTraces = <Map<String, dynamic>>[];
    var degraded = false;
    var errorCode = '';

    final rounds = decision.maxRounds < 1 ? 1 : decision.maxRounds;
    for (var round = 1; round <= rounds; round++) {
      var hasNewEvidence = false;
      final roundProviders = <String>[];
      var roundNewEvidence = 0;

      // 构建本轮所有查询词：主查询 + queryVariants（仅第1轮使用 variants）
      final queriesToRun = <String>[];
      final baseQuery = round <= 1
          ? request.query
          : _queryForRound(request.query, round);
      queriesToRun.add(baseQuery);
      if (round == 1 && request.queryVariants.isNotEmpty) {
        for (final v in request.queryVariants) {
          if (v.trim().isNotEmpty && v.trim() != baseQuery.trim()) {
            queriesToRun.add(v.trim());
          }
        }
      }

      for (final providerId in decision.providerSequence) {
        if (!policy.allowsProvider(providerId)) continue;
        if (providerId == 'web' && !policy.allowsWebRound(round)) continue;
        final provider = _providers[providerId];
        if (provider == null) continue;

        if (providerId == 'web' && queriesToRun.length > 1) {
          // Layer 2: 并发执行所有查询词
          final futures = queriesToRun
              .map((q) {
                final sanitized = policy.sanitizeQueryForWeb(q);
                return provider.retrieve(
                  AssistantRetrievalRequest(
                    query: sanitized,
                    requestedCapabilities: decision.capabilitySequence,
                    contextScopeHint: request.contextScopeHint,
                    privacyProfile: request.privacyProfile,
                    privacyPolicy: request.privacyPolicy,
                    providerHint: request.providerHint,
                    round: round,
                    maxItems: request.maxItems,
                  ),
                );
              })
              .toList(growable: false);
          final responses = await Future.wait(futures, eagerError: false);
          providersUsed.add(providerId);
          roundProviders.add(providerId);
          for (final response in responses) {
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
        } else {
          // 单查询路径（非 web provider 或 variants 为空）
          final queryForRound = providerId == 'web'
              ? policy.sanitizeQueryForWeb(baseQuery)
              : baseQuery;
          final response = await provider.retrieve(
            AssistantRetrievalRequest(
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
      }

      final deduped = _dedupeItems(allItems);
      // Layer 3: 综合质量评分（权威0.4 + 时效0.35 + 覆盖0.25）
      final qScore = _computeQualityScore(deduped);
      final shouldStop = qScore >= 0.65 || !hasNewEvidence;
      roundTraces.add(<String, dynamic>{
        'round': round,
        'providers': roundProviders,
        'queries': queriesToRun,
        'newEvidenceCount': roundNewEvidence,
        'coverageScore': _coverageScore(deduped),
        'qualityScore': qScore,
        'stopReason': shouldStop
            ? (qScore >= 0.65 ? 'quality_enough' : 'no_new_evidence')
            : '',
      });
      if (shouldStop) {
        final message = deduped.isEmpty ? '检索未找到足够信息。' : '检索完成。';
        final refs = _buildAllReferences(deduped);
        final authScore = _authorityScore(deduped);
        final authCount = _authoritativeCount(deduped);
        return AssistantRetrievalResult(
          success: deduped.isNotEmpty,
          message: message,
          items: deduped,
          providersUsed: providersUsed,
          coverageScore: _coverageScore(deduped),
          conflictScore: _conflictScore(deduped),
          degraded: degraded,
          errorCode: errorCode,
          nextRoundRecommended: !shouldStop,
          queryPlan: <String, dynamic>{
            'providerSequence': decision.providerSequence,
            'capabilitySequence': decision.capabilitySequence,
            'maxRounds': rounds,
            'queriesUsed': queriesToRun,
          },
          policyDecision: <String, dynamic>{
            'privacyProfile': request.privacyProfile,
            'webAccessMode': policy.webAccessMode,
            'redactBeforeWeb': policy.redactBeforeWeb,
            'decisionReasons': decision.decisionReasons,
          },
          roundTraces: roundTraces,
          qualityScore: qScore,
          authorityScore: authScore,
          authoritativeCount: authCount,
          totalReferencesSearched: allItems.length,
          allReferences: refs,
        );
      }
    }

    final deduped = _dedupeItems(allItems);
    final qScore = _computeQualityScore(deduped);
    final refs = _buildAllReferences(deduped);
    return AssistantRetrievalResult(
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
      qualityScore: qScore,
      authorityScore: _authorityScore(deduped),
      authoritativeCount: _authoritativeCount(deduped),
      totalReferencesSearched: allItems.length,
      allReferences: refs,
    );
  }

  String _queryForRound(String query, int round) {
    if (round <= 1) return query;
    if (query.contains('最新')) return query;
    return '$query 最新';
  }

  List<AssistantRetrievalItem> _dedupeItems(
    List<AssistantRetrievalItem> items,
  ) {
    final seen = <String>{};
    final result = <AssistantRetrievalItem>[];
    for (final item in items) {
      final key = '${item.sourceType}:${item.sourceId}:${item.content}';
      if (seen.contains(key)) continue;
      seen.add(key);
      result.add(item);
    }
    return result;
  }

  /// Layer 3: 综合质量评分 = 权威性(0.4) + 时效性(0.35) + 覆盖量(0.25)
  double _computeQualityScore(List<AssistantRetrievalItem> items) {
    if (items.isEmpty) return 0.0;
    final authScore = _authorityScore(items);
    // 时效性：若元数据中有 authorityScore 则用；否则用覆盖数量近似
    // 此处简化：authority 作为权威+时效的联合代理，覆盖量占 0.25
    final freshScore = authScore > 0 ? 1.0 : 0.3; // 有权威来源则认为时效性 ok
    final coverScore = (items.length / 4.0).clamp(0.0, 1.0);
    return authScore * 0.4 + freshScore * 0.35 + coverScore * 0.25;
  }

  double _coverageScore(List<AssistantRetrievalItem> items) {
    if (items.isEmpty) return 0.0;
    if (items.length >= 4) return 1.0;
    return items.length / 4.0;
  }

  double _conflictScore(List<AssistantRetrievalItem> items) {
    if (items.isEmpty) return 1.0;
    return 0.0;
  }

  double _authorityScore(List<AssistantRetrievalItem> items) {
    if (items.isEmpty) return 0.0;
    var score = 0.0;
    for (final item in items) {
      final auth = item.metadata['authorityScore'];
      if (auth is num) score += auth.toDouble();
    }
    return (score / items.length).clamp(0.0, 1.0);
  }

  int _authoritativeCount(List<AssistantRetrievalItem> items) {
    return items.where((item) {
      final auth = item.metadata['authorityScore'];
      return auth is num && auth > 0;
    }).length;
  }

  /// 构建全量参考资料列表，权威来源标记 cited=true
  List<Map<String, dynamic>> _buildAllReferences(
    List<AssistantRetrievalItem> items,
  ) {
    return items
        .take(8)
        .map((item) {
          final isAuth =
              (item.metadata['authorityScore'] as num?)?.toDouble() != null &&
              (item.metadata['authorityScore'] as num).toDouble() > 0;
          return <String, dynamic>{
            'title': item.metadata['title'] ?? item.sourceId,
            'url': item.metadata['url'] ?? item.sourceId,
            'snippet': item.content.length > 120
                ? item.content.substring(0, 120)
                : item.content,
            'sourceType': item.sourceType,
            'cited': isAuth,
            'authorityScore': item.metadata['authorityScore'] ?? 0.0,
          };
        })
        .toList(growable: false);
  }
}
