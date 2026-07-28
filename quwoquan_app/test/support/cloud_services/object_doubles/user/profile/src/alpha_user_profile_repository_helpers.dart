part of '../alpha_user_profile_repository.dart';

PersonaManagementItemWireDto _personaDtoFromWire(Map<String, dynamic> json) {
  return PersonaManagementItemWireDto.fromMap(json);
}

/// JSON 编码前去掉 null，避免 PATCH 误传「显式 null」覆盖服务端字段。
Map<String, dynamic> _omitNullMapValues(Map<String, dynamic> source) {
  return Map<String, dynamic>.fromEntries(
    source.entries.where((e) => e.value != null),
  );
}

/// Mock 当前用户资料的唯一解析入口。
///
/// `MockUserProfileRepository`、alpha Persona Facet 等测试链路都必须复用它，
/// 避免再次出现「主页资料已更新，但 active persona 仍读旧静态 JSON」的双真相源。
SubAccountProfileWireDto resolveMockUserProfileWire(String userId) {
  for (final key in _mockProfileLookupKeys(userId)) {
    final overrideWire = MockUserProfileRepository._profileOverrides[key];
    if (overrideWire != null) {
      return overrideWire;
    }
  }
  for (final key in _mockProfileLookupKeys(userId)) {
    final contractWire = _contractProfileWireByUserId[key];
    if (contractWire != null) {
      return contractWire;
    }
  }
  final sharedProfileWire = AlphaFixtureUserResolver.profileWireFor(userId);
  if (sharedProfileWire != null) {
    return SubAccountProfileWireDto.fromMap(sharedProfileWire);
  }
  return SubAccountProfileWireDto.fromMap(_defaultProfile(userId));
}

ProfileEditSnapshotWireDto? _resolveMockProfileEditSnapshotWire(String userId) {
  for (final key in _mockProfileLookupKeys(userId)) {
    final overrideWire =
        MockUserProfileRepository._profileEditSnapshotOverrides[key];
    if (overrideWire != null) {
      return overrideWire;
    }
  }
  return null;
}

List<String> _mockProfileLookupKeys(String userId) {
  final keys = <String>[];
  void add(String value) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty && !keys.contains(trimmed)) {
      keys.add(trimmed);
    }
  }

  final trimmed = userId.trim();
  add(trimmed);
  if (trimmed.isNotEmpty) {
    add(AlphaFixtureUserResolver.resolveSubAccountId(trimmed));
    add(AlphaFixtureUserResolver.resolveUserId(trimmed));
  }
  if (trimmed.isEmpty ||
      AlphaFixtureUserResolver.isOwnerLikeSubAccountId(trimmed)) {
    add(AlphaFixtureUserResolver.currentUserVariantSubAccountId);
    add(AlphaFixtureUserResolver.currentUserVariantUserId);
  }
  return keys;
}

extension _ProfileEditSnapshotDataMockMerge on ProfileEditSnapshotData {
  ProfileEditSnapshotData copyWithPrivateFieldsFromWire(
    ProfileEditSnapshotWireDto wire,
  ) {
    return ProfileEditSnapshotData(
      ownerUserId: ownerUserId,
      subAccountId: subAccountId,
      avatarUrl: avatarUrl,
      avatarAssetId: wire.avatarAssetId,
      avatarVersion: avatarVersion,
      backgroundUrl: backgroundUrl,
      backgroundAssetId: wire.backgroundAssetId,
      nickname: nickname,
      gender: wire.gender,
      birthDate: wire.birthDate,
      region: wire.region,
      regionTagRef: wire.regionTagRef,
      userHandle: userHandle,
      bio: bio,
      occupationTagRef: occupationTagRef,
      interestTagRefs: interestTagRefs,
      phoneCredential: phoneCredential,
      qrCard: wire.qrCard == null
          ? qrCard
          : ProfileQrCardData.fromMap(wire.qrCard!),
    );
  }
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
