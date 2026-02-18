import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_provider.dart';

class ConversationRetrievalProvider implements AssistentRetrievalProvider {
  const ConversationRetrievalProvider(this._sessionManager);

  final AssistantSessionManager _sessionManager;

  @override
  String get providerId => 'conversation';

  @override
  List<String> get capabilityIds => const <String>[
        AssistentCapabilityCatalog.chatRecent,
      ];

  @override
  Future<AssistentRetrievalResult> retrieve(AssistentRetrievalRequest request) async {
    await _sessionManager.load();
    final sessionId = (request.contextScopeHint['sessionId'] as String?)?.trim() ?? 'default';
    final summary = _sessionManager.summarizeRecent(sessionId);
    if (summary.isEmpty) {
      return const AssistentRetrievalResult(
        success: false,
        message: '当前会话暂无可检索历史。',
        providersUsed: <String>['conversation'],
      );
    }
    return AssistentRetrievalResult(
      success: true,
      message: '已读取当前会话历史。',
      items: <AssistentRetrievalItem>[
        AssistentRetrievalItem(
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

