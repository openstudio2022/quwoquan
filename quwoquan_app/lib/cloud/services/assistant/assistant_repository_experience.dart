part of 'assistant_repository.dart';

/// Assistant entry, personal-data, and creation-assistance transport.
mixin _RemoteAssistantExperience on _RemoteAssistantRepositoryBase
    implements
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantCreationSuggestFacet {
  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async {
    // 失败关闭：policy 拉取失败不再合成 learningSyncEnabled=true 的本地
    // fallback；调用方必须按"学习同步关闭"处理。
    const path = AssistantApiMetadata.getPolicyPath;
    try {
      final uri = _assistantGetUri(path, {
        if (policyVersionHint.trim().isNotEmpty)
          'policyVersionHint': policyVersionHint.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getPolicyOperation,
          clientPageId: AssistantRequestPageIds.getPolicy,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId: AssistantApiMetadata.getPolicyOperation,
              ),
            );
      if (decoded.isEmpty) {
        throw const FormatException(
          'assistant policy snapshot response is empty',
        );
      }
      return AssistantPolicyView.fromJson(decoded);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    final snapshot = assistantContextSnapshotFromOpenContext(
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
          AssistantReportPageContextRequestWire(
            contextSnapshot: snapshot,
          ).toJson(),
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId: AssistantApiMetadata.reportPageContextOperation,
              ),
            );
      if (decoded.isEmpty) {
        throw const FormatException('page context response is empty');
      }
      final ack = PageContextAck.fromJson(decoded);
      if (!ack.accepted) {
        throw const FormatException('page context was not accepted');
      }
      return ack;
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantEntryPersonalizationView> getEntryPersonalization({
    required AssistantOpenContext context,
  }) async {
    // 失败不再伪造 personalized 数据；UI 层（half sheet）以自己的静态默认
    // 欢迎区作为空态展示。
    const path = AssistantApiMetadata.getEntryPersonalizationPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        'source': context.source.name,
        'pageType': assistantPageTypeForSource(context.source),
        if ((context.tab ?? '').trim().isNotEmpty) 'tab': context.tab!.trim(),
        if ((context.dimension ?? '').trim().isNotEmpty)
          'dimension': context.dimension!.trim(),
        if ((context.entityId ?? '').trim().isNotEmpty)
          'objectId': context.entityId!.trim(),
        if ((context.objectType ?? '').trim().isNotEmpty)
          'objectType': context.objectType!.trim(),
        'experienceLevel': context.experienceLevel.name,
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getEntryPersonalizationOperation,
          clientPageId: AssistantRequestPageIds.getEntryPersonalization,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId:
                    AssistantApiMetadata.getEntryPersonalizationOperation,
              ),
            );
      return AssistantEntryPersonalizationView.fromJson(decoded);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<SuggestedActionListView> getSuggestedActions({
    required AssistantOpenContext context,
  }) async {
    const path = AssistantApiMetadata.getSuggestedActionsPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        'pageType': assistantPageTypeForSource(context.source),
        if ((context.entityId ?? '').trim().isNotEmpty)
          'objectId': context.entityId!.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getSuggestedActionsOperation,
          clientPageId: AssistantRequestPageIds.getSuggestedActions,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId: AssistantApiMetadata.getSuggestedActionsOperation,
              ),
            );
      return SuggestedActionListView.fromJson(decoded);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    const path = AssistantApiMetadata.listAssistantTasksPath;
    try {
      final uri = _assistantGetUri(path, {
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
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
        ),
      );
      return rows
          .map(AssistantUserTaskView.fromJson)
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
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  }) async {
    const path = AssistantApiMetadata.listSkillsPath;
    try {
      final uri = _assistantGetUri(path, {'limit': '$limit'});
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listSkillsOperation,
          clientPageId: AssistantRequestPageIds.listSkills,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listSkillsOperation,
        ),
      );
      return rows
          .map(AssistantSkillCatalogItemView.fromJson)
          .where((row) => row.skillId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantCreationSuggestResponse> suggestCreationAssistance({
    required AssistantCreationSuggestRequest request,
  }) async {
    try {
      final response = await _httpClient.post(
        _assistantUri(AssistantApiMetadata.suggestCreationAssistancePath),
        headers: <String, String>{
          ..._headersForPersonalAssistantDialog(
            operationId:
                AssistantApiMetadata.suggestCreationAssistanceOperation,
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
              context: _personalAssistantDialogContext(
                operationId:
                    AssistantApiMetadata.suggestCreationAssistanceOperation,
              ),
            );
      return AssistantCreationSuggestResponse.fromJson(decoded);
    } catch (error) {
      // available=false + unavailableReason 是契约内合法的结构化不可用
      // 响应（创作助手为可选增强），记录后降级，不吞异常细节。
      developer.log(
        'creation assistance suggest failed',
        name: 'AssistantCreationSuggest',
        error: error,
      );
      return const AssistantCreationSuggestResponse(
        suggestedTagRefs: <String>[],
        suggestedHomepages: <AssistantSuggestedHomepageView>[],
        available: false,
        unavailableReason: 'request_failed',
      );
    }
  }
}
