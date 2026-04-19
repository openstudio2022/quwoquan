import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_models.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_provider.dart';

class ConversationRetrievalProvider implements AssistantRetrievalProvider {
  const ConversationRetrievalProvider(this._sessionManager);

  final AssistantSessionManager _sessionManager;

  @override
  String get providerId => 'conversation';

  @override
  List<String> get capabilityIds => const <String>[
    AssistantCapabilityCatalog.chatRecent,
  ];

  @override
  Future<AssistantRetrievalResult> retrieve(
    AssistantRetrievalRequest request,
  ) async {
    await _sessionManager.load();
    final sessionId =
        (request.contextScopeHint['sessionId'] as String?)?.trim() ?? 'default';
    final summary = _sessionManager.summarizeRecent(sessionId);
    if (summary.isEmpty) {
      return const AssistantRetrievalResult(
        success: false,
        message: '当前会话暂无可检索历史。',
        providersUsed: <String>['conversation'],
      );
    }
    return AssistantRetrievalResult(
      success: true,
      message: '已读取当前会话历史。',
      items: <AssistantRetrievalItem>[
        AssistantRetrievalItem(
          content: summary,
          sourceType: 'conversation',
          sourceId: sessionId,
          relevance: 0.75,
        ),
      ],
      providersUsed: const <String>['conversation'],
      coverageScore: 0.75,
      conflictScore: 0.0,
    );
  }
}
