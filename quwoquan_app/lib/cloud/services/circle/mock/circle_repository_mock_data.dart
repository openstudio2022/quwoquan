part of '../circle_repository.dart';

/// Mock 详情 wire：在 [CircleDto.toMap] 上补齐 UI/Mock 仍消费的别名键与主圈视角字段。
Map<String, dynamic> _mockCircleDetailWireFromDto(CircleDto d) {
  final w = Map<String, dynamic>.from(d.toMap());
  final contractRow = CircleContractSeedHelpers.circleRowById(d.id);
  w['categoryId'] = d.category;
  final cover = (d.coverUrl ?? '').trim();
  if (cover.isNotEmpty) {
    w['cover'] = cover;
    w['avatar'] = cover;
    w['avatarUrl'] = cover;
  }
  if (d.description != null && d.description!.isNotEmpty) {
    w['desc'] = d.description;
  }
  if (contractRow != null) {
    final role = (contractRow['role'] ?? '').toString().trim();
    final joinStatus = (contractRow['joinStatus'] ?? '').toString().trim();
    if (role.isNotEmpty) {
      w['role'] = role;
    }
    if (joinStatus.isNotEmpty) {
      w['joinStatus'] = joinStatus;
    }
    if (contractRow['isFollowed'] is bool) {
      w['isFollowed'] = contractRow['isFollowed'] as bool;
    }
  } else {
    w.putIfAbsent('role', () => 'member');
    w.putIfAbsent('joinStatus', () => 'none');
    w.putIfAbsent('isFollowed', () => false);
  }
  // 与 metadata ui_config circle_sections 闭集一致（works/members/chat/storage），
  // 不下发生产 UI 不存在的板块，避免 Mock 与 Remote 形态漂移。
  final sectionConfig = w['sectionConfig'];
  if (sectionConfig is! List || sectionConfig.isEmpty) {
    w['sectionConfig'] = const <Map<String, dynamic>>[
      {'sectionType': 'works', 'visible': true, 'order': 0},
      {'sectionType': 'members', 'visible': true, 'order': 1},
      {'sectionType': 'chat', 'visible': true, 'order': 2},
      {'sectionType': 'storage', 'visible': true, 'order': 3},
    ];
  }
  w.putIfAbsent('storageUsedBytes', () => 0);
  w.putIfAbsent('storageQuotaBytes', () => 1073741824);
  w.putIfAbsent('autoSyncChat', () => true);
  return w;
}
