import 'package:quwoquan_app/assistant/skills/knowledge_qa_models.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';

class KnowledgeQaEngine {
  const KnowledgeQaEngine({required AssistantToolRegistry toolRegistry})
    : _toolRegistry = toolRegistry;

  final AssistantToolRegistry _toolRegistry;

  Future<KnowledgeQaReport> run({
    required String query,
    String domainId = '',
    String? primaryProvider,
    String retrievalToolName = '',
    List<String> backupProviders = const <String>[],
    int maxEvidence = 6,
  }) async {
    final resolvedToolName = _resolveRetrievalToolName(retrievalToolName);
    if (resolvedToolName.isEmpty) {
      return const KnowledgeQaReport(
        answer: '当前未配置可用的检索工具，无法完成知识问答。',
        conclusion: '当前未配置可用的检索工具，无法完成知识问答。',
        evidences: <KnowledgeQaEvidence>[],
        uncertainty: '缺少显式检索工具配置。',
        providersTried: <String>[],
        degraded: true,
      );
    }
    final plan = _buildPlan(
      query: query,
      domainId: domainId,
      primaryProvider: primaryProvider,
      backupProviders: backupProviders,
      maxEvidence: maxEvidence,
    );
    final providersTried = <String>[];
    final evidences = <KnowledgeQaEvidence>[];
    var degraded = false;

    final primary = await _search(
      resolvedToolName,
      plan.primaryProvider,
      plan.query,
      plan.maxEvidence,
    );
    providersTried.add(
      plan.primaryProvider.trim().isEmpty ? 'default' : plan.primaryProvider,
    );
    if (primary.success) {
      evidences.addAll(
        _extractEvidence(provider: plan.primaryProvider, payload: primary.data),
      );
      degraded = degraded || primary.degraded;
    } else {
      degraded = true;
    }

    final shouldSupplement = evidences.length < 2;
    if (shouldSupplement) {
      for (final provider in plan.backupProviders) {
        final backup = await _search(
          resolvedToolName,
          provider,
          plan.query,
          plan.maxEvidence,
        );
        providersTried.add(provider);
        if (backup.success) {
          evidences.addAll(
            _extractEvidence(payload: backup.data, provider: provider),
          );
        } else {
          degraded = true;
        }
      }
    }

    final deduped = _dedupeEvidence(
      evidences,
    ).take(maxEvidence).toList(growable: false);
    final uncertainty = _buildUncertainty(
      evidenceCount: deduped.length,
      providersTried: providersTried,
      degraded: degraded,
    );
    final conclusion = _buildConclusion(query: plan.query, evidences: deduped);
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
    required String domainId,
    required String? primaryProvider,
    required List<String> backupProviders,
    required int maxEvidence,
  }) {
    final provider = primaryProvider?.trim() ?? '';
    final normalizedBackups = <String>{
      for (final item in backupProviders)
        if (item.trim().isNotEmpty && item.trim() != provider) item.trim(),
    }.toList(growable: false);
    return KnowledgeQaPlan(
      query: query.trim(),
      domainId: domainId.trim(),
      primaryProvider: provider,
      backupProviders: normalizedBackups,
      maxEvidence: maxEvidence,
    );
  }

  Future<AssistantToolResult> _search(
    String toolName,
    String provider,
    String query,
    int count,
  ) async {
    final args = <String, dynamic>{'query': query, 'count': count};
    if (provider.trim().isNotEmpty) {
      args['provider'] = provider.trim();
    }
    final result = await _toolRegistry.execute(toolName, args);
    return AssistantToolResult.fromJson(result.toJson());
  }

  List<KnowledgeQaEvidence> _extractEvidence({
    required Map<String, dynamic>? payload,
    required String provider,
  }) {
    if (payload == null) return const <KnowledgeQaEvidence>[];
    final evidence = <KnowledgeQaEvidence>[];
    final results =
        (payload['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        (payload['results'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    for (final item in results) {
      evidence.add(
        KnowledgeQaEvidence(
          provider: provider,
          title: item['title']?.toString() ?? '',
          snippet:
              item['summary']?.toString() ??
              item['content']?.toString() ??
              item['snippet']?.toString() ??
              '',
          url: item['url']?.toString() ?? '',
        ),
      );
    }

    return evidence
        .where((e) => e.title.isNotEmpty || e.snippet.isNotEmpty)
        .toList(growable: false);
  }

  List<KnowledgeQaEvidence> _dedupeEvidence(
    List<KnowledgeQaEvidence> evidences,
  ) {
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
    required List<KnowledgeQaEvidence> evidences,
  }) {
    if (evidences.isEmpty) {
      return '';
    }
    final top = evidences.first;
    return top.snippet.isEmpty ? top.title : top.snippet;
  }

  String _buildUncertainty({
    required int evidenceCount,
    required List<String> providersTried,
    required bool degraded,
  }) {
    return '';
  }

  String _buildStructuredAnswer({
    required String conclusion,
    required List<KnowledgeQaEvidence> evidences,
    required String uncertainty,
  }) {
    return conclusion.trim();
  }

  String _resolveRetrievalToolName(String explicitToolName) {
    final trimmed = explicitToolName.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
    final tools = _toolRegistry.listTools();
    if (tools.length == 1) {
      return tools.single.name;
    }
    return '';
  }
}
