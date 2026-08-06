import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_group_local_search.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/conversation_avatar_search_index.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class SqfliteLocalCircleGroupSearchIndex
    implements CircleGroupLocalSearchIndex {
  static const _syncInterval = Duration(minutes: 5);

  SqfliteLocalCircleGroupSearchIndex(
    this._store,
    this._actorScopeLoader,
    this._circleQuery,
    this._circleGroupQuery,
  );

  final LocalCircleGroupSnapshotStore _store;
  final SearchActorScopeLoader _actorScopeLoader;
  final CircleQueryReader _circleQuery;
  final CircleGroupQueries _circleGroupQuery;
  final Map<String, DateTime> _lastSyncAttemptAt = <String, DateTime>{};
  final Map<String, bool> _lastSyncSucceeded = <String, bool>{};
  final Map<String, Future<bool>> _syncFutures = <String, Future<bool>>{};

  @override
  Future<bool> sync() async {
    final namespace = await _resolveNamespace();
    final existing = _syncFutures[namespace.key];
    if (existing != null) {
      return existing;
    }
    final now = DateTime.now();
    final lastAttemptAt = _lastSyncAttemptAt[namespace.key];
    if (lastAttemptAt != null &&
        now.difference(lastAttemptAt) < _syncInterval) {
      return _lastSyncSucceeded[namespace.key] ?? false;
    }

    _lastSyncAttemptAt[namespace.key] = now;
    final future = _refresh(namespace);
    _syncFutures[namespace.key] = future;
    try {
      return await future;
    } finally {
      _syncFutures.remove(namespace.key);
    }
  }

  Future<bool> _refresh(CircleLocalSearchScope namespace) async {
    try {
      final synced = await _store.ensureSeeded(
        namespace: namespace,
        circleQuery: _circleQuery,
        circleGroupQuery: _circleGroupQuery,
        forceRefresh: true,
      );
      _lastSyncSucceeded[namespace.key] = synced;
      return synced;
    } on Object {
      _lastSyncSucceeded[namespace.key] = false;
      rethrow;
    }
  }

  @override
  Future<List<CircleGroupLocalSearchHit>> searchGroups({
    required String query,
    int limit = 20,
  }) async {
    final namespace = await _resolveNamespace();
    final records = await _store.searchGroups(
      namespace: namespace,
      query: query,
      limit: limit,
    );
    return records
        .map(
          (record) => CircleGroupLocalSearchHit(
            groupId: record.groupId,
            circleId: record.circleId,
            name: record.name,
            description: record.description,
            circleName: record.circleName,
            groupType: record.groupType,
            memberCount: record.memberCount,
            highlightText: record.highlightText,
            matchedField: record.matchedField,
          ),
        )
        .toList(growable: false);
  }

  Future<CircleLocalSearchScope> _resolveNamespace() async {
    final scope = await _actorScopeLoader();
    return CircleLocalSearchScope.fromSearchActorScope(scope);
  }
}
