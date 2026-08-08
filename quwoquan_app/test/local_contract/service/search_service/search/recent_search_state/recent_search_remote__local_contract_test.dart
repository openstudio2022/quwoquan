// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
// readiness_case: recent_search_state_list_recent_searches_app_local
// readiness_case: recent_search_state_upsert_recent_search_app_local
// readiness_case: recent_search_state_delete_recent_search_app_local
// readiness_case: recent_search_state_clear_recent_searches_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/recent_search_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('production Remote 单轨执行四个 RecentSearchState operations', () async {
    final executor = _RecordingExecutor();
    final remote = RemoteRecentSearchAdapter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final listed = await remote.listRecentSearches(
      ListRecentSearchesQuery(scope: 'all'),
    );
    final upserted = await remote.upsertRecentSearch(
      UpsertRecentSearchCommand(query: '城市漫步', scope: 'all'),
    );
    await remote.deleteRecentSearch(
      DeleteRecentSearchCommand(entryId: upserted.entryId),
    );
    await remote.clearRecentSearches(ClearRecentSearchesCommand(scope: 'all'));

    expect(listed, hasLength(1));
    expect(listed.single.entryId, 'recent-list-1');
    expect(upserted.entryId, 'recent-upsert-1');
    expect(upserted.query, '城市漫步');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.searchRecentSearchStateListRecentSearches,
      AppCloudOperationIds.searchRecentSearchStateUpsertRecentSearch,
      AppCloudOperationIds.searchRecentSearchStateDeleteRecentSearch,
      AppCloudOperationIds.searchRecentSearchStateClearRecentSearches,
    ]);
    expect(executor.clientPageIds, <String>[
      SearchRequestPageIds.listRecentSearches,
      SearchRequestPageIds.upsertRecentSearch,
      SearchRequestPageIds.deleteRecentSearch,
      SearchRequestPageIds.clearRecentSearches,
    ]);
    expect(executor.idempotencyKeys, <String?>[
      null,
      'recent-upsert',
      'recent-delete',
      'recent-clear',
    ]);
  });
}

CloudOperationInvocationContext _context(String clientPageId) =>
    CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.globalSearchLanding.id,
      routeId: AppUiSurfaces.globalSearchLanding.routeId,
      clientPageId: clientPageId,
      idempotencyKey: switch (clientPageId) {
        SearchRequestPageIds.upsertRecentSearch => 'recent-upsert',
        SearchRequestPageIds.deleteRecentSearch => 'recent-delete',
        SearchRequestPageIds.clearRecentSearches => 'recent-clear',
        _ => null,
      },
      actor: const CloudOperationActorContext(
        accountId: 'account-recent',
        personaId: 'persona-recent',
        deviceActorId: 'device-recent',
      ),
    );

final class _RecordingExecutor implements CloudOperationExecutor {
  final List<String> operationIds = <String>[];
  final List<String> clientPageIds = <String>[];
  final List<String?> idempotencyKeys = <String?>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    clientPageIds.add(context.clientPageId);
    idempotencyKeys.add(context.idempotencyKey);
    requestEncoder();
    return responseDecoder(switch (operation.canonicalOperationId) {
      AppCloudOperationIds.searchRecentSearchStateListRecentSearches =>
        <String, Object?>{
          'items': <Object?>[
            _entry(
              entryId: 'recent-list-1',
              query: '旅行摄影',
              updatedAt: '2026-08-08T01:00:00Z',
            ),
          ],
        },
      AppCloudOperationIds.searchRecentSearchStateUpsertRecentSearch => _entry(
        entryId: 'recent-upsert-1',
        query: '城市漫步',
        updatedAt: '2026-08-08T01:01:00Z',
      ),
      AppCloudOperationIds.searchRecentSearchStateDeleteRecentSearch ||
      AppCloudOperationIds.searchRecentSearchStateClearRecentSearches =>
        <String, Object?>{'status': 'ok'},
      _ => throw StateError(
        'unexpected operation ${operation.canonicalOperationId}',
      ),
    });
  }
}

Map<String, Object?> _entry({
  required String entryId,
  required String query,
  required String updatedAt,
}) => <String, Object?>{
  'entryId': entryId,
  'query': query,
  'scope': 'all',
  'updatedAt': updatedAt,
};
