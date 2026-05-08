import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_group_wire_normalize.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class LocalCircleGroupSnapshotStore {
  LocalCircleGroupSnapshotStore({
    String? databasePath,
    DatabaseFactory? databaseFactory,
  }) : _databasePath = databasePath,
       _databaseFactory = databaseFactory;

  static final LocalCircleGroupSnapshotStore shared =
      LocalCircleGroupSnapshotStore();
  static bool _ffiInitialized = false;

  final String? _databasePath;
  final DatabaseFactory? _databaseFactory;
  final Map<String, Future<void>> _seedFutures = <String, Future<void>>{};
  Future<Database>? _databaseFuture;

  Future<void> ensureReady() async {
    await _database;
  }

  Future<bool> hasAnySnapshot(LocalSearchNamespace namespace) async {
    final database = await _database;
    final rows = await database.rawQuery(
      'SELECT COUNT(*) AS count FROM circle_group_snapshots WHERE namespace_key = ?',
      <Object?>[namespace.key],
    );
    return ((rows.first['count'] as num?)?.toInt() ?? 0) > 0;
  }

  Future<bool> ensureSeeded({
    required LocalSearchNamespace namespace,
    required CircleRepository circleRepository,
    int circleLimit = 12,
    int groupsPerCircle = 20,
  }) async {
    if (await hasAnySnapshot(namespace)) {
      return true;
    }
    final existing = _seedFutures[namespace.key];
    if (existing != null) {
      try {
        await existing;
        return true;
      } catch (_) {
        return false;
      }
    }
    final future = _seedFromRemote(
      namespace: namespace,
      circleRepository: circleRepository,
      circleLimit: circleLimit,
      groupsPerCircle: groupsPerCircle,
    );
    _seedFutures[namespace.key] = future;
    try {
      await future;
      return true;
    } catch (_) {
      return false;
    } finally {
      _seedFutures.remove(namespace.key);
    }
  }

  Future<void> upsertGroups({
    required LocalSearchNamespace namespace,
    required Iterable<Map<String, dynamic>> groups,
  }) async {
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    for (final group in groups) {
      final normalized = normalizeCircleGroupWireMap(
        Map<String, dynamic>.from(group),
        shape: CircleGroupWireShape.localSnapshotPersist,
        fallbackUpdatedAt: now,
      );
      final groupId = _string(normalized['groupId']);
      final circleId = _string(normalized['circleId']);
      if (groupId.isEmpty || circleId.isEmpty) {
        continue;
      }
      final searchableText = _searchableText(<Object?>[
        normalized['name'],
        normalized['description'],
        normalized['circleName'],
        normalized['groupType'],
        normalized['visibility'],
      ]);
      batch.insert('circle_group_snapshots', <String, Object?>{
        'namespace_key': namespace.key,
        'circle_id': circleId,
        'group_id': groupId,
        'name': _string(normalized['name']),
        'description': _string(normalized['description']),
        'circle_name': _string(normalized['circleName']),
        'group_type': _string(normalized['groupType']),
        'visibility': _string(normalized['visibility']),
        'conversation_id': _string(normalized['conversationId']),
        'member_count': (normalized['memberCount'] as num?)?.toInt() ?? 0,
        'searchable_text': searchableText,
        'payload_json': jsonEncode(normalized),
        'updated_at': _string(normalized['updatedAt']).isNotEmpty
            ? _string(normalized['updatedAt'])
            : now,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  Future<List<LocalCircleGroupSnapshotRecord>> searchGroups({
    required LocalSearchNamespace namespace,
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
        .map((row) => LocalCircleGroupSnapshotRecord.fromWireMap(
              _decodePayload(row['payload_json']),
            ))
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

  Future<void> deleteNamespace(LocalSearchNamespace namespace) async {
    final database = await _database;
    await database.delete(
      'circle_group_snapshots',
      where: 'namespace_key = ?',
      whereArgs: <Object?>[namespace.key],
    );
  }

  Future<void> _seedFromRemote({
    required LocalSearchNamespace namespace,
    required CircleRepository circleRepository,
    required int circleLimit,
    required int groupsPerCircle,
  }) async {
    final circles = await circleRepository.listCircles(limit: circleLimit);
    final snapshots = <Map<String, dynamic>>[];
    for (final circle in circles) {
      final circleId = _string(circle.id);
      if (circleId.isEmpty) {
        continue;
      }
      final circleName = _string(circle.name);
      try {
        final groups = await circleRepository.listCircleGroups(
          circleId,
          limit: groupsPerCircle,
        );
        for (final group in groups) {
          snapshots.add(<String, dynamic>{
            ...group.toMap(),
            'circleId': circleId,
            if (circleName.isNotEmpty) 'circleName': circleName,
          });
        }
      } catch (_) {}
    }
    await upsertGroups(namespace: namespace, groups: snapshots);
  }

  Map<String, dynamic> _decodePayload(Object? rawJson) {
    final text = _string(rawJson);
    if (text.isEmpty) {
      return const <String, dynamic>{};
    }
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) {
        return decoded.cast<String, dynamic>();
      }
    } catch (_) {}
    return const <String, dynamic>{};
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
    if (_databasePath != null && _databasePath.trim().isNotEmpty) {
      final path = _databasePath.trim();
      final lastSeparator = path.lastIndexOf(Platform.pathSeparator);
      if (lastSeparator > 0) {
        await Directory(
          path.substring(0, lastSeparator),
        ).create(recursive: true);
      }
      return path;
    }
    final factory = _databaseFactory;
    final basePath = factory != null
        ? await factory.getDatabasesPath()
        : await getDatabasesPath();
    await Directory(basePath).create(recursive: true);
    return '$basePath${Platform.pathSeparator}quwoquan_circle_group_snapshots.db';
  }

  void _configureFactory() {
    if (_databaseFactory != null || _ffiInitialized) {
      return;
    }
    if (Platform.isAndroid || Platform.isIOS) {
      _ffiInitialized = true;
      return;
    }
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
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

  String _matchedField(
    String query,
    LocalCircleGroupSnapshotRecord payload,
  ) {
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
