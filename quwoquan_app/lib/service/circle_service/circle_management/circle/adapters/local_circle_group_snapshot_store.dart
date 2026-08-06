import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_group_local_search.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:sqflite/sqflite.dart';

class LocalCircleGroupSnapshotStore {
  LocalCircleGroupSnapshotStore({
    required LocalDatabasePathResolver databasePathResolver,
    String? databasePath,
    DatabaseFactory? databaseFactory,
  }) : this._internal(
         databasePathResolver: databasePathResolver,
         databasePath: databasePath,
         databaseFactory: databaseFactory,
       );

  LocalCircleGroupSnapshotStore._internal({
    required this._databasePathResolver,
    this._databasePath,
    this._databaseFactory,
  });

  static bool _ffiInitialized = false;

  final LocalDatabasePathResolver _databasePathResolver;
  final String? _databasePath;
  final DatabaseFactory? _databaseFactory;
  final Map<String, Future<void>> _seedFutures = <String, Future<void>>{};
  int _activeOperationCount = 0;
  Completer<void>? _idleCompleter;
  Future<Database>? _databaseFuture;

  Future<void> ensureReady() async {
    await _database;
  }

  Future<void> waitUntilIdle() async {
    await _idleCompleter?.future;
  }

  Future<void> close() async {
    final databaseFuture = _databaseFuture;
    _databaseFuture = null;
    if (databaseFuture == null) {
      return;
    }
    final database = await databaseFuture;
    if (database.isOpen) {
      await database.close();
    }
  }

  Future<bool> hasAnySnapshot(CircleLocalSearchScope namespace) async {
    final database = await _database;
    final rows = await database.rawQuery(
      'SELECT COUNT(*) AS count FROM circle_group_snapshots WHERE namespace_key = ?',
      <Object?>[namespace.key],
    );
    return ((rows.first['count'] as num?)?.toInt() ?? 0) > 0;
  }

  Future<bool> ensureSeeded({
    required CircleLocalSearchScope namespace,
    required CircleQueryReader circleQuery,
    required CircleGroupQueries circleGroupQuery,
    int circleLimit = 12,
    int groupsPerCircle = 20,
    bool forceRefresh = false,
  }) async {
    _beginOperation();
    try {
      if (!forceRefresh && await hasAnySnapshot(namespace)) {
        return true;
      }
      final existing = _seedFutures[namespace.key];
      if (existing != null) {
        await existing;
        return true;
      }
      final future = _seedFromRemote(
        namespace: namespace,
        circleQuery: circleQuery,
        circleGroupQuery: circleGroupQuery,
        circleLimit: circleLimit,
        groupsPerCircle: groupsPerCircle,
      );
      _seedFutures[namespace.key] = future;
      try {
        await future;
        return true;
      } finally {
        _seedFutures.remove(namespace.key);
      }
    } finally {
      _endOperation();
    }
  }

  void _beginOperation() {
    if (_activeOperationCount == 0) {
      _idleCompleter = Completer<void>();
    }
    _activeOperationCount += 1;
  }

  void _endOperation() {
    _activeOperationCount -= 1;
    if (_activeOperationCount == 0) {
      _idleCompleter?.complete();
      _idleCompleter = null;
    }
  }

  Future<void> upsertGroups({
    required CircleLocalSearchScope namespace,
    required Iterable<LocalCircleGroupSnapshotRecord> groups,
  }) async {
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    for (final group in groups) {
      batch.insert(
        'circle_group_snapshots',
        _snapshotRow(namespace: namespace, group: group, now: now),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
    }
    await batch.commit(noResult: true);
  }

  Future<void> _replaceGroups({
    required CircleLocalSearchScope namespace,
    required Iterable<LocalCircleGroupSnapshotRecord> groups,
  }) async {
    final database = await _database;
    final snapshots = groups.toList(growable: false);
    final now = DateTime.now().toIso8601String();
    await database.transaction((transaction) async {
      await transaction.delete(
        'circle_group_snapshots',
        where: 'namespace_key = ?',
        whereArgs: <Object?>[namespace.key],
      );
      final batch = transaction.batch();
      for (final group in snapshots) {
        batch.insert(
          'circle_group_snapshots',
          _snapshotRow(namespace: namespace, group: group, now: now),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      await batch.commit(noResult: true);
    });
  }

  Map<String, Object?> _snapshotRow({
    required CircleLocalSearchScope namespace,
    required LocalCircleGroupSnapshotRecord group,
    required String now,
  }) {
    if (group.groupId.trim().isEmpty ||
        group.circleId.trim().isEmpty ||
        group.name.trim().isEmpty ||
        group.groupType.trim().isEmpty ||
        group.visibility.trim().isEmpty) {
      throw const FormatException('CircleGroup snapshot identity is invalid');
    }
    final searchableText = _searchableText(<Object?>[
      group.name,
      group.description,
      group.circleName,
      group.groupType,
      group.visibility,
    ]);
    return <String, Object?>{
      'namespace_key': namespace.key,
      'circle_id': group.circleId,
      'group_id': group.groupId,
      'name': group.name,
      'description': group.description,
      'circle_name': group.circleName,
      'group_type': group.groupType,
      'visibility': group.visibility,
      'conversation_id': group.conversationId,
      'member_count': group.memberCount,
      'searchable_text': searchableText,
      'payload_json': jsonEncode(group.toStorageMap()),
      'updated_at': group.updatedAt.isNotEmpty ? group.updatedAt : now,
    };
  }

  Future<List<LocalCircleGroupSnapshotRecord>> searchGroups({
    required CircleLocalSearchScope namespace,
    required String query,
    int limit = 20,
  }) async {
    final normalizedQuery = _normalize(query);
    if (normalizedQuery == null) {
      return const <LocalCircleGroupSnapshotRecord>[];
    }
    final database = await _database;
    final rows = await database.rawQuery(
      '''
      SELECT payload_json
      FROM circle_group_snapshots
      WHERE namespace_key = ?
        AND searchable_text LIKE ?
      ORDER BY updated_at DESC
      LIMIT ?
      ''',
      <Object?>[namespace.key, '%$normalizedQuery%', limit],
    );
    return rows
        .map(
          (row) => LocalCircleGroupSnapshotRecord.fromStorageMap(
            _decodePayload(row['payload_json']),
          ),
        )
        .where((item) => item.groupId.isNotEmpty && item.circleId.isNotEmpty)
        .map((item) {
          final matchedField = _matchedField(query, item);
          return item.copyWith(
            matchedField: matchedField,
            highlightText: _highlightText(item, matchedField),
          );
        })
        .toList(growable: false);
  }

  Future<void> deleteNamespace(CircleLocalSearchScope namespace) async {
    final database = await _database;
    await database.delete(
      'circle_group_snapshots',
      where: 'namespace_key = ?',
      whereArgs: <Object?>[namespace.key],
    );
  }

  /// 不可逆账号终态专用：等待现有 seed 完成后清除全部本地圈子群投影。
  Future<void> clearAllNamespaces() async {
    await waitUntilIdle();
    final database = await _database;
    await database.delete('circle_group_snapshots');
    final rows = await database.rawQuery(
      'SELECT COUNT(*) AS count FROM circle_group_snapshots',
    );
    if (((rows.first['count'] as num?)?.toInt() ?? 0) != 0) {
      throw StateError('local circle snapshot cleanup left residual rows');
    }
  }

  Future<void> _seedFromRemote({
    required CircleLocalSearchScope namespace,
    required CircleQueryReader circleQuery,
    required CircleGroupQueries circleGroupQuery,
    required int circleLimit,
    required int groupsPerCircle,
  }) async {
    final circles = (await circleQuery.list(
      CircleListQuery(limit: circleLimit),
    )).items;
    final snapshots = <LocalCircleGroupSnapshotRecord>[];
    for (final circle in circles) {
      final circleId = _string(circle.id);
      if (circleId.isEmpty) {
        continue;
      }
      final circleName = _string(circle.name);
      final groups = await circleGroupQuery.list(
        CircleGroupListQuery(circleId: circleId, limit: groupsPerCircle),
      );
      for (final group in groups.items) {
        snapshots.add(
          LocalCircleGroupSnapshotRecord.fromGroupSlice(
            group,
            circleName: circleName,
          ),
        );
      }
    }
    await _replaceGroups(namespace: namespace, groups: snapshots);
  }

  Map<String, Object?> _decodePayload(Object? rawJson) {
    final text = _string(rawJson);
    if (text.isEmpty) {
      return const <String, dynamic>{};
    }
    final decoded = jsonDecode(text);
    if (decoded is! Map) {
      throw const FormatException(
        'CircleGroup snapshot payload must be a JSON object',
      );
    }
    return decoded.cast<String, Object?>();
  }

  Future<Database> get _database async {
    return _databaseFuture ??= _openDatabase();
  }

  Future<Database> _openDatabase() async {
    _configureFactory();
    final path = await _resolveDatabasePath();
    final factory = _databaseFactory;
    if (factory != null) {
      return factory.openDatabase(
        path,
        options: OpenDatabaseOptions(version: 1, onCreate: _onCreate),
      );
    }
    return openDatabase(path, version: 1, onCreate: _onCreate);
  }

  Future<String> _resolveDatabasePath() async {
    final factory = _databaseFactory;
    return _databasePathResolver.resolve(
      explicitPath: _databasePath,
      fileName: 'quwoquan_circle_group_snapshots.db',
      loadDefaultDirectory: () =>
          factory != null ? factory.getDatabasesPath() : getDatabasesPath(),
    );
  }

  void _configureFactory() {
    if (_databaseFactory != null || _ffiInitialized) {
      return;
    }
    // 移动端 / macOS 使用 sqflite 插件原生实现；VM 单测通过构造函数注入 databaseFactory。
    _ffiInitialized = true;
  }

  Future<void> _onCreate(Database database, int version) async {
    await database.execute('''
      CREATE TABLE circle_group_snapshots (
        namespace_key TEXT NOT NULL,
        circle_id TEXT NOT NULL,
        group_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        circle_name TEXT NOT NULL,
        group_type TEXT NOT NULL,
        visibility TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        member_count INTEGER NOT NULL DEFAULT 0,
        searchable_text TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace_key, circle_id, group_id)
      )
    ''');
    await database.execute(
      'CREATE INDEX idx_circle_group_snapshot_namespace_updated ON circle_group_snapshots(namespace_key, updated_at DESC)',
    );
  }

  String _matchedField(String query, LocalCircleGroupSnapshotRecord payload) {
    final normalizedQuery = _normalize(query);
    if (normalizedQuery == null) {
      return '';
    }
    for (final entry in <String, String>{
      'name': payload.name,
      'description': payload.description,
      'circleName': payload.circleName,
    }.entries) {
      final value = _normalize(entry.value);
      if (value != null && value.contains(normalizedQuery)) {
        return entry.key;
      }
    }
    return '';
  }

  String _highlightText(
    LocalCircleGroupSnapshotRecord payload,
    String matchedField,
  ) {
    switch (matchedField) {
      case 'description':
        return payload.description;
      case 'circleName':
        return payload.circleName;
      case 'name':
      default:
        return payload.name;
    }
  }

  String _searchableText(List<Object?> values) {
    return values
        .map((item) => _normalize(item?.toString()) ?? '')
        .where((item) => item.isNotEmpty)
        .join(' ');
  }

  String _string(Object? value) {
    return value?.toString().trim() ?? '';
  }

  String? _normalize(String? value) {
    final normalized = value?.trim().toLowerCase();
    if (normalized == null || normalized.isEmpty) {
      return null;
    }
    return normalized;
  }
}
