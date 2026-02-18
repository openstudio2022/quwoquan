import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_service.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class UnifiedRetrievalTool implements AssistantTool {
  const UnifiedRetrievalTool(this._retrievalService);

  final AssistentRetrievalService _retrievalService;

  @override
  String get name => 'unified_retrieval';

  @override
  String get description => 'Capability-gated retrieval across page/chat/memory/web.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final query = (arguments['query'] as String?)?.trim() ?? '';
    if (query.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing query',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }
    final requestedCapabilities = (arguments['requestedCapabilities'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final scopeHint = (arguments['contextScopeHint'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final privacyPolicy = (arguments['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
        (scopeHint['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};

    final result = await _retrievalService.retrieve(
      AssistentRetrievalRequest(
        query: query,
        requestedCapabilities: requestedCapabilities,
        contextScopeHint: scopeHint,
        privacyProfile: (arguments['privacyProfile'] as String?)?.trim().isNotEmpty == true
            ? (arguments['privacyProfile'] as String).trim()
            : 'default',
        privacyPolicy: privacyPolicy,
        providerHint: (arguments['providerHint'] as String?)?.trim(),
        maxItems: (arguments['maxItems'] as int?) ?? 6,
      ),
    );

    return AssistantToolResult(
      success: result.success,
      message: result.toAnswerSummary(),
      data: <String, dynamic>{
        'providersUsed': result.providersUsed,
        'coverageScore': result.coverageScore,
        'conflictScore': result.conflictScore,
        'queryPlan': result.queryPlan,
        'policyDecision': result.policyDecision,
        'roundTraces': result.roundTraces,
        'items': result.items
            .map(
              (item) => <String, dynamic>{
                'content': item.content,
                'sourceType': item.sourceType,
                'sourceId': item.sourceId,
                'relevance': item.relevance,
                'metadata': item.metadata,
              },
            )
            .toList(growable: false),
      },
      degraded: result.degraded,
      errorCode: result.success ? AssistantErrorCode.none : AssistantErrorCode.executionFailed,
    );
  }
}

