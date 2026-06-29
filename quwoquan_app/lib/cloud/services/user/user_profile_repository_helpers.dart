part of 'user_profile_repository.dart';

PersonaDto _personaDtoFromWire(Map<String, dynamic> json) {
  final m = Map<String, dynamic>.from(json);
  m.putIfAbsent('id', () => '');
  m.putIfAbsent('userId', () => '');
  m.putIfAbsent('displayName', () => '');
  m.putIfAbsent('createdAt', () => '');
  m.putIfAbsent('updatedAt', () => '');
  return PersonaDto.fromJson(m);
}

List<ProfileInteractionActivityViewData> _interactionViewDataListFromWires(
  Iterable<Map<String, dynamic>> wires, {
  required int limit,
}) {
  final items = wires
      .map(
        (m) =>
            ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
              ProfileInteractionActivityWireDto.fromMap(m),
            ),
      )
      .toList(growable: false);
  final sorted = [...items]
    ..sort((a, b) {
      final aTime = a.createdAt;
      final bTime = b.createdAt;
      if (aTime == null && bTime == null) {
        return a.activityId.compareTo(b.activityId);
      }
      if (aTime == null) return 1;
      if (bTime == null) return -1;
      return bTime.compareTo(aTime);
    });
  return sorted.take(limit).toList(growable: false);
}

/// JSON 编码前去掉 null，避免 PATCH 误传「显式 null」覆盖服务端字段。
Map<String, dynamic> _omitNullMapValues(Map<String, dynamic> source) {
  return Map<String, dynamic>.fromEntries(
    source.entries.where((e) => e.value != null),
  );
}

/// Mock 当前用户资料的唯一解析入口。
///
/// `MockUserProfileRepository`、`MockUserRepository` 等 mock 链路都必须复用它，
/// 避免再次出现「主页资料已更新，但 active persona 仍读旧静态 JSON」的双真相源。
SubAccountProfileWireDto resolveMockUserProfileWire(String userId) {
  final overrideWire = MockUserProfileRepository._profileOverrides[userId];
  if (overrideWire != null) {
    return overrideWire;
  }
  final contractWire = _contractProfileWireByUserId[userId];
  if (contractWire != null) {
    return contractWire;
  }
  final creatorWire = PrefabUserResolver.creatorProfileWireFor(userId);
  if (creatorWire != null) {
    return SubAccountProfileWireDto.fromMap(creatorWire);
  }
  return SubAccountProfileWireDto.fromMap(_defaultProfile(userId));
}

int _decodeCursorOffset(String? cursor) {
  return int.tryParse((cursor ?? '').trim()) ?? 0;
}

CursorPage<T> _paginateItems<T>(
  List<T> items, {
  required String? cursor,
  required int limit,
}) {
  final safeLimit = limit <= 0 ? CloudApiDefaults.pageLimit : limit;
  final start = _decodeCursorOffset(cursor).clamp(0, items.length);
  final end = (start + safeLimit).clamp(0, items.length);
  final pageItems = items.sublist(start, end);
  final nextCursor = end >= items.length ? null : '$end';
  return CursorPage<T>(
    items: pageItems,
    nextCursor: nextCursor,
    totalCount: items.length,
  );
}

String _normalizeSearchQuery(String? query) {
  return (query ?? '').trim().toLowerCase();
}

List<Map<String, dynamic>> _filterRelationWiresByQuery(
  Iterable<Map<String, dynamic>> wires, {
  String? query,
}) {
  final normalizedQuery = _normalizeSearchQuery(query);
  if (normalizedQuery.isEmpty) {
    return wires.toList(growable: false);
  }
  return wires
      .where((row) {
        final displayName = (row['displayName'] ?? '').toString().toLowerCase();
        final username = (row['username'] ?? '').toString().toLowerCase();
        final userHandle = (row['userHandle'] ?? '').toString().toLowerCase();
        return displayName.contains(normalizedQuery) ||
            username.contains(normalizedQuery) ||
            userHandle.contains(normalizedQuery);
      })
      .toList(growable: false);
}

List<CircleDto> _filterCirclesByQuery(
  Iterable<CircleDto> circles, {
  String? query,
}) {
  final normalizedQuery = _normalizeSearchQuery(query);
  if (normalizedQuery.isEmpty) {
    return circles.toList(growable: false);
  }
  return circles
      .where((circle) {
        final name = circle.name.toLowerCase();
        final description = (circle.description ?? '').toLowerCase();
        return name.contains(normalizedQuery) ||
            description.contains(normalizedQuery);
      })
      .toList(growable: false);
}
