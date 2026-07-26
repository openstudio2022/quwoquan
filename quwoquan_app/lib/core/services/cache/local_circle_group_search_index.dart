import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class LocalCircleGroupSearchIndex {
  Future<bool> sync();

  Future<List<LocalCircleGroupSnapshotRecord>> searchGroups({
    required String query,
    int limit = 20,
  });
}

final class SqfliteLocalCircleGroupSearchIndex
    implements LocalCircleGroupSearchIndex {
  static const _syncInterval = Duration(minutes: 5);

  SqfliteLocalCircleGroupSearchIndex(
    this._store,
    this._personaContextLoader,
    this._circleQuery,
    this._circleGroupQuery,
  );

  final LocalCircleGroupSnapshotStore _store;
  final PersonaContextLoader _personaContextLoader;
  final CircleQueryReader _circleQuery;
  final CircleGroupQueryReader _circleGroupQuery;
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

  Future<bool> _refresh(LocalSearchNamespace namespace) async {
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
  Future<List<LocalCircleGroupSnapshotRecord>> searchGroups({
    required String query,
    int limit = 20,
  }) async {
    final namespace = await _resolveNamespace();
    return _store.searchGroups(
      namespace: namespace,
      query: query,
      limit: limit,
    );
  }

  Future<LocalSearchNamespace> _resolveNamespace() async {
    final context = await _personaContextLoader();
    return LocalSearchNamespace.fromActivePersonaContext(context);
  }
}
