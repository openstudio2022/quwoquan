part of 'assistant_repository.dart';

/// 全网搜索通过 [StartAssistantRun] 执行；本 mixin 不拥有搜索专用 HTTP 路由。
mixin _RemoteAssistantSearchRun
    on _RemoteAssistantRepositoryBase, _RemoteAssistantSessionRun
    implements AssistantSearchRunFacet {
  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    final normalizedQuery = query.trim();
    if (normalizedQuery.isEmpty) {
      throw ArgumentError.value(query, 'query', 'must not be empty');
    }
    final session = await _createAssistantSession(
      summary: normalizedQuery,
      clientRequestId: sessionClientRequestId,
      networkSurface: true,
    );
    final run = await _startAssistantRunIntent(
      sessionId: session.sessionId,
      clientRequestId: runClientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.search,
        search: AssistantSearchRunIntent(
          query: normalizedQuery,
          searchIntensity: searchIntensity,
          sourceSurfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          fromGlobalSearch: true,
        ),
      ),
      contextSnapshot: contextSnapshot,
      networkSurface: true,
    );
    await for (final event in _watchAssistantRunEvents(
      runId: run.runId,
      lastEventId: '',
      networkSurface: true,
    )) {
      if (_isAssistantTerminalStreamEvent(event)) {
        break;
      }
    }
    final terminalRun = await _core.getRun(
      runId: run.runId,
      networkSurface: true,
    );
    final snapshot = terminalRun.terminalSnapshot;
    if (snapshot == null) {
      throw const FormatException(
        'assistant search run completed without terminalSnapshot',
      );
    }
    if (snapshot.failure != null) {
      throw FormatException(
        'assistant search run failed: ${snapshot.failure!.code}',
      );
    }
    return snapshot;
  }
}
