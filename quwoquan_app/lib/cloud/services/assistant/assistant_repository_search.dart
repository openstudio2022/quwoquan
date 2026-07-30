part of 'assistant_repository.dart';

/// Xiaoqu network-search transport.
mixin _RemoteAssistantXiaoquSearch on _RemoteAssistantRepositoryBase
    implements AssistantXiaoquSearchFacet {
  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    // 不再本地合成"假搜索摘要"；空 query、非 2xx、解码失败或空回显一律抛
    // 结构化 CloudException，由消费页走错误态。
    const path = AssistantApiMetadata.searchXiaoquResultsPath;
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      throw CloudErrorMapper.fromException(
        ArgumentError.value(query, 'query', 'must not be empty'),
        requestPath: path,
      );
    }
    try {
      final uri = _assistantUri(path);
      final response = await _httpClient.post(
        uri,
        headers: <String, String>{
          ..._headersForNetworkResults(
            operationId: AssistantApiMetadata.searchXiaoquResultsOperation,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(
          AssistantSearchXiaoquRequestWire(
            userQuery: trimmedQuery,
            searchIntensity: searchIntensity,
            sourceSurfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
            fromGlobalSearch: true,
            contextSnapshot: contextSnapshot,
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
              context: _networkResultsContext(
                operationId: AssistantApiMetadata.searchXiaoquResultsOperation,
              ),
            );
      final result = AssistantSearchResultView.fromJson(decoded);
      if (result.queryEcho.isEmpty &&
          (result.summary?.trim().isEmpty ?? true)) {
        throw const FormatException(
          'xiaoqu search result is missing queryEcho and summary',
        );
      }
      return result;
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }
}
