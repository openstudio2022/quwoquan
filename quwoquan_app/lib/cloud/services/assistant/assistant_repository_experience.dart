part of 'assistant_repository.dart';

/// Assistant entry、PageContext、TaskView 与 creation intent 的单轨 transport。
mixin _RemoteAssistantExperience on _RemoteAssistantRepositoryBase
    implements
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantCreationRunFacet {
  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    final snapshot = pageContextSnapshotFromOpenContext(
      context,
      userAction: userAction,
    );
    final receipt = await _core.reportPageContext(snapshot);
    if (!receipt.accepted) {
      throw const FormatException('page context was not accepted');
    }
    return receipt;
  }

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) async {
    return _core.getEntry(
      query: AssistantEntryQuery(
        pageType: assistantPageTypeForSource(context.source).wireName,
        objectId: (context.entityId ?? '').trim().isEmpty
            ? null
            : context.entityId!.trim(),
      ),
    );
  }

  @override
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    final normalizedStatus = status?.trim();
    final slice = await _core.listTasks(
      limit: limit,
      status: normalizedStatus == null || normalizedStatus.isEmpty
          ? null
          : normalizedStatus,
    );
    return slice.items
        .where((row) => row.taskId.isNotEmpty)
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  }) {
    return _startAssistantRunIntent(
      sessionId: sessionId,
      clientRequestId: clientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.creationAssistance,
        creationAssistance: intent,
      ),
      contextSnapshot: contextSnapshot,
    );
  }
}
