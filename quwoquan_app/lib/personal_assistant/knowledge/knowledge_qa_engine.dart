import 'package:quwoquan_app/personal_assistant/knowledge/knowledge_qa_models.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class KnowledgeQaEngine {
  const KnowledgeQaEngine({
    required AssistantToolRegistry toolRegistry,
  }) : _toolRegistry = toolRegistry;

  final AssistantToolRegistry _toolRegistry;

  Future<KnowledgeQaReport> run({
    required String query,
    String? primaryProvider,
    List<String> backupProviders = const <String>['brave', 'openclaw_proxy'],
    int maxEvidence = 6,
  }) async {
    final plan = _buildPlan(
      query: query,
      primaryProvider: primaryProvider,
      backupProviders: backupProviders,
      maxEvidence: maxEvidence,
    );
    final providersTried = <String>[];
    final evidences = <KnowledgeQaEvidence>[];
    var degraded = false;

    final primary = await _search(plan.primaryProvider, plan.query, plan.maxEvidence);
    providersTried.add(plan.primaryProvider);
    if (primary.success) {
      evidences.addAll(_extractEvidence(
        provider: plan.primaryProvider,
        payload: primary.data,
      ));
      degraded = degraded || primary.degraded;
    } else {
      degraded = true;
    }

    final shouldSupplement = evidences.length < 2;
    if (shouldSupplement) {
      for (final provider in plan.backupProviders) {
        final backup = await _search(provider, plan.query, plan.maxEvidence);
        providersTried.add(provider);
        if (backup.success) {
          evidences.addAll(_extractEvidence(
            provider: provider,
            payload: backup.data,
          ));
        } else {
          degraded = true;
        }
      }
    }

    final deduped = _dedupeEvidence(evidences).take(maxEvidence).toList(growable: false);
    final uncertainty = _buildUncertainty(
      domain: plan.domain,
      evidenceCount: deduped.length,
      providersTried: providersTried,
      degraded: degraded,
    );
    final conclusion = _buildConclusion(
      query: plan.query,
      domain: plan.domain,
      evidences: deduped,
    );
    final answer = _buildStructuredAnswer(
      conclusion: conclusion,
      evidences: deduped,
      uncertainty: uncertainty,
    );

    return KnowledgeQaReport(
      answer: answer,
      conclusion: conclusion,
      evidences: deduped,
      uncertainty: uncertainty,
      providersTried: providersTried,
      degraded: degraded || deduped.isEmpty,
    );
  }

  KnowledgeQaPlan _buildPlan({
    required String query,
    required String? primaryProvider,
    required List<String> backupProviders,
    required int maxEvidence,
  }) {
    final domain = _classifyDomain(query);
    final provider = (primaryProvider?.trim().isNotEmpty ?? false)
        ? primaryProvider!.trim()
        : _defaultProviderByDomain(domain);
    return KnowledgeQaPlan(
      query: query.trim(),
      domain: domain,
      primaryProvider: provider,
      backupProviders: backupProviders,
      maxEvidence: maxEvidence,
    );
  }

  KnowledgeQaDomain _classifyDomain(String query) {
    final text = query.toLowerCase();
    if (text.contains('财经') || text.contains('股票') || text.contains('基金') || text.contains('finance')) {
      return KnowledgeQaDomain.finance;
    }
    if (text.contains('天气') || text.contains('降雨') || text.contains('温度') || text.contains('weather')) {
      return KnowledgeQaDomain.weather;
    }
    if (text.contains('出行') || text.contains('行程') || text.contains('机票') || text.contains('旅行') || text.contains('travel')) {
      return KnowledgeQaDomain.travel;
    }
    if (text.contains('情感') || text.contains('关系') || text.contains('焦虑') || text.contains('emotion')) {
      return KnowledgeQaDomain.emotion;
    }
    if (text.contains('健康') || text.contains('疾病') || text.contains('用药') || text.contains('health')) {
      return KnowledgeQaDomain.health;
    }
    if (text.contains('易经') || text.contains('卜卦') || text.contains('divination')) {
      return KnowledgeQaDomain.divination;
    }
    return KnowledgeQaDomain.general;
  }

  String _defaultProviderByDomain(KnowledgeQaDomain domain) {
    switch (domain) {
      case KnowledgeQaDomain.weather:
      case KnowledgeQaDomain.travel:
        return 'brave';
      case KnowledgeQaDomain.finance:
      case KnowledgeQaDomain.health:
      case KnowledgeQaDomain.emotion:
      case KnowledgeQaDomain.divination:
      case KnowledgeQaDomain.general:
        return 'perplexity';
    }
  }

  Future<AssistantToolResult> _search(String provider, String query, int count) {
    return _toolRegistry.execute(
      'web_search',
      <String, dynamic>{
        'provider': provider,
        'query': query,
        'count': count,
      },
    );
  }

  List<KnowledgeQaEvidence> _extractEvidence({
    required String provider,
    required Map<String, dynamic>? payload,
  }) {
    if (payload == null) return const <KnowledgeQaEvidence>[];
    final raw = payload['raw'];
    if (raw is! Map) return const <KnowledgeQaEvidence>[];
    final map = raw.cast<String, dynamic>();
    final evidence = <KnowledgeQaEvidence>[];

    // Brave shape: web.results[]
    final web = map['web'];
    if (web is Map) {
      final results = web['results'];
      if (results is List) {
        for (final item in results.whereType<Map>()) {
          evidence.add(
            KnowledgeQaEvidence(
              provider: provider,
              title: item['title']?.toString() ?? '',
              snippet: item['description']?.toString() ?? item['snippet']?.toString() ?? '',
              url: item['url']?.toString() ?? '',
            ),
          );
        }
      }
    }

    // Perplexity shape: choices[].message.content
    final choices = map['choices'];
    if (choices is List) {
      for (final item in choices.whereType<Map>()) {
        final message = item['message'];
        if (message is Map) {
          final content = message['content']?.toString() ?? '';
          if (content.isNotEmpty) {
            evidence.add(
              KnowledgeQaEvidence(
                provider: provider,
                title: 'Perplexity synthesis',
                snippet: content,
                url: '',
              ),
            );
          }
        }
      }
    }

    // Generic common shape: results[]
    final results = map['results'];
    if (results is List) {
      for (final item in results.whereType<Map>()) {
        evidence.add(
          KnowledgeQaEvidence(
            provider: provider,
            title: item['title']?.toString() ?? '',
            snippet: item['content']?.toString() ?? item['snippet']?.toString() ?? '',
            url: item['url']?.toString() ?? '',
          ),
        );
      }
    }

    return evidence.where((e) => e.title.isNotEmpty || e.snippet.isNotEmpty).toList(growable: false);
  }

  List<KnowledgeQaEvidence> _dedupeEvidence(List<KnowledgeQaEvidence> evidences) {
    final result = <KnowledgeQaEvidence>[];
    final seen = <String>{};
    for (final evidence in evidences) {
      final key = '${evidence.title}__${evidence.url}__${evidence.snippet}';
      if (seen.contains(key)) continue;
      seen.add(key);
      result.add(evidence);
    }
    return result;
  }

  String _buildConclusion({
    required String query,
    required KnowledgeQaDomain domain,
    required List<KnowledgeQaEvidence> evidences,
  }) {
    if (evidences.isEmpty) {
      return '当前未检索到足够可信的信息，建议补充问题范围后再查询。';
    }
    final top = evidences.first;
    final domainLabel = _domainLabel(domain);
    return '$domainLabel问题「$query」的当前结论：${top.snippet.isEmpty ? top.title : top.snippet}';
  }

  String _buildUncertainty({
    required KnowledgeQaDomain domain,
    required int evidenceCount,
    required List<String> providersTried,
    required bool degraded,
  }) {
    final base = '已使用 ${providersTried.join('/')} 检索，证据条数 $evidenceCount。';
    if (degraded || evidenceCount < 2) {
      return '$base 交叉验证不足，请谨慎参考并建议二次确认。';
    }
    if (domain == KnowledgeQaDomain.health || domain == KnowledgeQaDomain.finance) {
      return '$base 属于高风险领域，建议以专业机构信息为准。';
    }
    return '$base 信息一致性良好。';
  }

  String _buildStructuredAnswer({
    required String conclusion,
    required List<KnowledgeQaEvidence> evidences,
    required String uncertainty,
  }) {
    final evidenceLines = evidences
        .take(3)
        .map((e) => '- [${e.provider}] ${e.title.isEmpty ? '摘要' : e.title}${e.url.isEmpty ? '' : ' (${e.url})'}')
        .join('\n');
    return '结论：$conclusion\n\n依据：\n$evidenceLines\n\n不确定性：$uncertainty';
  }

  String _domainLabel(KnowledgeQaDomain domain) {
    switch (domain) {
      case KnowledgeQaDomain.finance:
        return '财经';
      case KnowledgeQaDomain.weather:
        return '天气';
      case KnowledgeQaDomain.travel:
        return '出行';
      case KnowledgeQaDomain.emotion:
        return '情感';
      case KnowledgeQaDomain.health:
        return '健康';
      case KnowledgeQaDomain.divination:
        return '易经';
      case KnowledgeQaDomain.general:
        return '通用';
    }
  }
}

