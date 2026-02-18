import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/tools/websearch_tool.dart';

class WebRetrievalProvider implements AssistentRetrievalProvider {
  WebRetrievalProvider({WebSearchTool? tool}) : _tool = tool ?? WebSearchTool();

  final WebSearchTool _tool;

  @override
  String get providerId => 'web';

  @override
  List<String> get capabilityIds => const <String>[
        AssistentCapabilityCatalog.webSearch,
      ];

  @override
  Future<AssistentRetrievalResult> retrieve(AssistentRetrievalRequest request) async {
    final result = await _tool.execute(<String, dynamic>{
      'query': request.query,
      if (request.providerHint != null && request.providerHint!.trim().isNotEmpty)
        'provider': request.providerHint,
      'count': request.maxItems,
    });
    if (!result.success) {
      return AssistentRetrievalResult(
        success: false,
        message: result.message,
        providersUsed: const <String>['web'],
        degraded: result.degraded,
        errorCode: result.errorCode.name,
      );
    }
    final summary = (result.data?['summary'] as String?)?.trim() ?? result.message;
    return AssistentRetrievalResult(
      success: true,
      message: result.message,
      items: <AssistentRetrievalItem>[
        AssistentRetrievalItem(
          content: summary,
          sourceType: 'web',
          sourceId: 'web_search',
          relevance: 0.8,
          metadata: <String, dynamic>{
            'provider': result.data?['provider'] ?? '',
          },
        ),
      ],
      providersUsed: const <String>['web'],
      coverageScore: summary.isNotEmpty ? 0.8 : 0.3,
      conflictScore: 0.0,
      degraded: result.degraded,
    );
  }
}

