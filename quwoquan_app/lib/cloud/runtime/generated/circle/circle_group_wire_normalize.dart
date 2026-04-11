/// 群组搜索命中与本地快照共用的 wire 行归一化（单一实现，避免 search / snapshot 分叉）。
///
/// 语义对齐原 [`search_repository`] `_normalizeCircleGroupPayload` 与
/// [`local_circle_group_snapshot_store`] `_normalizeGroup`。

enum CircleGroupWireShape {
  /// 全局搜索 / `_circleGroupHit`：保留 `matchedField`、`highlightText`，`memberCount` 保持 wire 原样。
  searchHit,

  /// 本地 SQLite 快照行：补齐 `updatedAt`、`groupType`、`visibility` 等持久化列。
  localSnapshotPersist,
}

String _cgTrim(Object? value) => value?.toString().trim() ?? '';

String _cgFirstNonEmpty(Iterable<Object?> values) {
  for (final value in values) {
    final text = _cgTrim(value);
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}

/// 归一化群组相关 Map（id 别名、circleName、展示字段等）。
///
/// [fallbackUpdatedAt] 在 [CircleGroupWireShape.localSnapshotPersist] 下必填。
Map<String, dynamic> normalizeCircleGroupWireMap(
  Map<String, dynamic> raw, {
  required CircleGroupWireShape shape,
  String? fallbackUpdatedAt,
}) {
  final circleId = _cgFirstNonEmpty(<Object?>[
    raw['circleId'],
    raw['circle_id'],
  ]);
  final groupId = _cgFirstNonEmpty(<Object?>[
    raw['groupId'],
    raw['circleGroupId'],
    raw['group_id'],
    raw['id'],
    raw['_id'],
  ]);
  switch (shape) {
    case CircleGroupWireShape.searchHit:
      final name = _cgFirstNonEmpty(<Object?>[
        raw['name'],
        raw['title'],
        raw['highlightText'],
        groupId,
      ]);
      final description = _cgFirstNonEmpty(<Object?>[
        raw['description'],
        raw['summary'],
      ]);
      final circleName = _cgFirstNonEmpty(<Object?>[
        raw['circleName'],
        raw['circle_name'],
        raw['circleDisplayName'],
      ]);
      return <String, dynamic>{
        ...raw,
        'circleId': circleId,
        'groupId': groupId,
        'name': name,
        'description': description,
        'circleName': circleName,
        'memberCount': raw['memberCount'],
        'matchedField': raw['matchedField'],
        'highlightText': raw['highlightText'] ?? name,
      };

    case CircleGroupWireShape.localSnapshotPersist:
      final name = _cgFirstNonEmpty(<Object?>[
        raw['name'],
        raw['title'],
        groupId,
      ]);
      final fu = fallbackUpdatedAt ?? '';
      return <String, dynamic>{
        ...raw,
        'circleId': circleId,
        'groupId': groupId,
        'name': name,
        'description': _cgTrim(raw['description']),
        'circleName': _cgFirstNonEmpty(<Object?>[
          raw['circleName'],
          raw['circle_name'],
          raw['circleDisplayName'],
        ]),
        'groupType': _cgFirstNonEmpty(<Object?>[
          raw['groupType'],
          raw['kind'],
        ]),
        'visibility': _cgTrim(raw['visibility']),
        'conversationId': _cgTrim(raw['conversationId']),
        'memberCount': (raw['memberCount'] as num?)?.toInt() ?? 0,
        'updatedAt': _cgFirstNonEmpty(<Object?>[
          raw['updatedAt'],
          raw['lastActiveAt'],
          fu,
        ]),
      };
  }
}
