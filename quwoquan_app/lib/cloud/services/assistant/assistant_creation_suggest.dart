part of 'assistant_repository.dart';

abstract class AssistantConversationRepository {
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) {
    throw UnimplementedError('createAssistantConversation');
  }

  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) {
    throw UnimplementedError('getAssistantConversation');
  }

  Future<AssistantTurnEnvelopeWire> createAssistantTurn({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) {
    throw UnimplementedError('createAssistantTurn');
  }

  Future<AssistantTurnEnvelopeWire> getAssistantTurn({required String turnId}) {
    throw UnimplementedError('getAssistantTurn');
  }

  Stream<AssistantStreamEventWire> streamAssistantTurn({
    required String turnId,
  }) {
    throw UnimplementedError('streamAssistantTurn');
  }
}

abstract class AssistantSkillSubscriptionRepository {
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = _kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  });

  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
  });

  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
  });
}

Future<AssistantCreationSuggestResponse> mockSuggestCreationAssistance(
  List<SkillSubscriptionWire> subscriptions, {
  required AssistantCreationSuggestRequest request,
}) async {
  final enabled = subscriptions.any(
    (item) => item.skillId == 'creation_assistant' && item.status == 'active',
  );
  if (!enabled) {
    return const AssistantCreationSuggestResponse(
      suggestedTagRefs: <String>[],
      suggestedHomepages: <AssistantSuggestedHomepageView>[],
      available: false,
      unavailableReason: 'skill_not_enabled',
    );
  }
  final text = <String?>[
    request.draftTitle,
    request.draftSummary,
    request.bodyDigest,
  ].whereType<String>().join(' ');
  final tagRefs = <String>{
    if (text.contains('九寨') || text.contains('旅行')) 'Topic/旅行',
    if (text.contains('摄影') || text.contains('照片')) 'Topic/摄影',
  }.toList(growable: false);
  return AssistantCreationSuggestResponse(
    suggestedTagRefs: tagRefs,
    suggestedHomepages: <AssistantSuggestedHomepageView>[
      if ((request.primaryHomepageId ?? '').trim().isNotEmpty)
        AssistantSuggestedHomepageView(
          id: request.primaryHomepageId!.trim(),
          type: 'homepage',
          displayName: request.primaryHomepageId!.trim(),
          reason: '已作为主关联主页',
        ),
    ],
    suggestedTitle:
        (request.draftTitle ?? '').trim().isEmpty &&
            (request.primaryHomepageId ?? '').trim().isNotEmpty
        ? '我和${request.primaryHomepageId!.trim()}有关的一次发现'
        : null,
    suggestedSummary: (request.draftSummary ?? '').trim().isEmpty
        ? (request.bodyDigest ?? '').trim()
        : null,
    available: true,
  );
}

Future<AssistantCreationSuggestResponse> remoteSuggestCreationAssistance(
  RemoteAssistantRepository repository, {
  required AssistantCreationSuggestRequest request,
}) async {
  try {
    final response = await repository._httpClient.post(
      repository._assistantUri(
        AssistantApiMetadata.suggestCreationAssistancePath,
      ),
      headers: <String, String>{
        ...repository._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.suggestCreationAssistanceOperation,
          clientPageId: AssistantRequestPageIds.suggestCreationAssistance,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(request.toJson()),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      return const AssistantCreationSuggestResponse(
        suggestedTagRefs: <String>[],
        suggestedHomepages: <AssistantSuggestedHomepageView>[],
        available: false,
        unavailableReason: 'request_failed',
      );
    }
    final decoded = response.body.trim().isEmpty
        ? <String, dynamic>{}
        : CloudResponseDecoder.asObject(
            jsonDecode(response.body),
            context: repository._personalAssistantDialogContext(
              operationId:
                  AssistantApiMetadata.suggestCreationAssistanceOperation,
            ),
          );
    return AssistantCreationSuggestResponse.fromJson(decoded);
  } catch (_) {
    return const AssistantCreationSuggestResponse(
      suggestedTagRefs: <String>[],
      suggestedHomepages: <AssistantSuggestedHomepageView>[],
      available: false,
      unavailableReason: 'request_failed',
    );
  }
}
