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
    const path = AssistantApiMetadata.reportPageContextPath;
    try {
      final response = await _httpClient.post(
        _assistantUri(path),
        headers: <String, String>{
          ..._headersForPersonalAssistantDialog(
            operationId: AssistantApiMetadata.reportPageContextOperation,
            clientPageId: AssistantRequestPageIds.reportPageContext,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(
          ReportPageContextCommand(contextSnapshot: snapshot).toJson(),
        ),
      );
      final receipt = PageContextReceipt.fromJson(
        _decodeAssistantObject(
          response,
          operationId: AssistantApiMetadata.reportPageContextOperation,
        ),
      );
      if (!receipt.accepted) {
        throw const FormatException('page context was not accepted');
      }
      return receipt;
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) async {
    const path = AssistantApiMetadata.getAssistantEntryPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        'pageType': assistantPageTypeForSource(context.source).wireName,
        if ((context.entityId ?? '').trim().isNotEmpty)
          'objectId': context.entityId!.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getAssistantEntryOperation,
          clientPageId: AssistantRequestPageIds.getAssistantEntry,
        ),
      );
      return AssistantEntryResponse.fromJson(
        _decodeAssistantObject(
          response,
          operationId: AssistantApiMetadata.getAssistantEntryOperation,
        ),
      );
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    const path = AssistantApiMetadata.listAssistantTasksPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        'limit': '$limit',
        if (status != null && status.trim().isNotEmpty) 'status': status.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
          clientPageId: AssistantRequestPageIds.listAssistantTasks,
        ),
      );
      final slice = AssistantTaskSlice.fromJson(
        _decodeAssistantObject(
          response,
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
        ),
      );
      return slice.items
          .where((row) => row.taskId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<List<AssistantSkillCatalogItemProjection>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  }) async {
    final catalog = await _skillCatalog.listSkills(limit: limit);
    return catalog.items
        .where((row) => row.skillId.isNotEmpty)
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
