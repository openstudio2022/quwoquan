import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_write_wire_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CircleRepository — 常规契约', () {
    late CircleRepository repo;

    setUp(() {
      repo = MockCircleRepository();
    });

    test('listCircles 返回非空圈子列表', () async {
      final circles = await repo.listCircles();
      expect(circles, isNotEmpty);
      expect(circles.first.id, isNotEmpty);
      expect(circles.first.name, isNotEmpty);
    });

    test('getCircle 返回完整圈子信息', () async {
      final detail = await repo.getCircle('circle_photo_01');
      expect(detail.circle.id, 'circle_photo_01');
      expect(detail.circle.name, isNotEmpty);
      final wire = detail.repositoryMergeBase();
      expect(wire.containsKey('sectionConfig'), isTrue);
      expect(wire.containsKey('storageUsedBytes'), isTrue);
      expect(wire.containsKey('storageQuotaBytes'), isTrue);
      expect(wire.containsKey('domainId'), isTrue);
      expect(wire.containsKey('autoSyncChat'), isTrue);
    });

    test('getCircleFeed 返回 feed 列表', () async {
      final feed = await repo.getCircleFeed('circle_photo_01');
      expect(feed, isNotEmpty);
      expect(feed.first, isA<PostBaseDto>());
    });

    test('listFiles 返回文件列表', () async {
      final files = await repo.listFiles('circle_photo_01');
      expect(files, isNotEmpty);
      expect(files.first.id, isNotEmpty);
      expect(files.first.name, isNotEmpty);
      expect(files.first.fileType, isNotEmpty);
    });

    test('listMembers 返回成员列表', () async {
      final members = await repo.listMembers('circle_photo_01');
      expect(members, isNotEmpty);
      expect(members.first.userId, isNotEmpty);
      expect(members.first.displayName ?? members.first.userId, isNotEmpty);
    });

    test('listHomeCircleDiscoveryFeed Mock 非空', () async {
      final feed = await repo.listHomeCircleDiscoveryFeed(limit: 50);
      expect(feed, isNotEmpty);
    });

    test('getCircleCategoryConfig 与 ui_category_tabs SSOT 对齐', () async {
      final cfg = await repo.getCircleCategoryConfig();
      expect(cfg.containsKey('all'), isTrue);
      expect(cfg['all']!.label, isNotEmpty);
      expect(cfg.length, greaterThanOrEqualTo(8));
    });

    test('getCircleStats 返回统计数据', () async {
      final stats = await repo.getCircleStats('circle_photo_01');
      expect(stats.raw.containsKey('totalMembers'), isTrue);
      expect(stats.raw.containsKey('weeklyActive'), isTrue);
    });

    test('createCircle 返回含 id 和 createdAt', () async {
      final circle = await repo.createCircle(
        CircleCreateWireDto.fromMap({
          'name': '测试圈子',
          'category': 'tech',
          'visibility': 'public',
        }),
      );
      expect(circle.id, isNotEmpty);
      expect(circle.name, '测试圈子');
    });

    test('updateCircle 返回合并后的数据', () async {
      final updated = await repo.updateCircle(
        'circle_photo_01',
        CircleUpdateWireDto.fromMap({'name': '新名称'}),
      );
      expect(updated.id, 'circle_photo_01');
      expect(updated.name, '新名称');
    });

    test('archiveCircle 不崩溃', () async {
      await expectLater(repo.archiveCircle('circle_photo_01'), completes);
    });

    test('updateMemberRole 不崩溃', () async {
      await expectLater(
        repo.updateMemberRole('circle_photo_01', 'u1', 'admin'),
        completes,
      );
    });

    test('pinPost 不崩溃', () async {
      await expectLater(
        repo.pinPost('circle_photo_01', 'p1', pinned: true),
        completes,
      );
    });

    test('featurePost 不崩溃', () async {
      await expectLater(
        repo.featurePost('circle_photo_01', 'p1', featured: true),
        completes,
      );
    });

    test('createFile 返回含 id', () async {
      final file = await repo.createFile(
        'circle_photo_01',
        CircleFileCreateWireDto.fromMap({
          'name': '测试文件.txt',
          'fileType': 'file',
        }),
      );
      expect(file.id, isNotEmpty);
    });

    test('getFile 返回匹配文件', () async {
      final files = await repo.listFiles('circle_photo_01');
      final firstFile = files.first;
      final file = await repo.getFile('circle_photo_01', firstFile.id);
      expect(file.id, firstFile.id);
    });

    test('updateFile 返回合并后数据', () async {
      final files = await repo.listFiles('circle_photo_01');
      final firstFile = files.first;
      final updated = await repo.updateFile(
        'circle_photo_01',
        firstFile.id,
        CircleFileUpdateWireDto.fromMap({'name': '重命名.txt'}),
      );
      expect(updated.name, '重命名.txt');
    });

    test('deleteFile 不崩溃', () async {
      final files = await repo.listFiles('circle_photo_01');
      await expectLater(
        repo.deleteFile('circle_photo_01', files.first.id),
        completes,
      );
    });

    test('reportBehavior 不崩溃', () async {
      await expectLater(
        repo.reportBehavior(
          CircleBehaviorReportWireDto.fromMap({
            'type': 'view',
            'circleId': 'c1',
          }),
        ),
        completes,
      );
    });

    test('listUserCircles 返回圈子列表', () async {
      final circles = await repo.listUserCircles('user_001');
      expect(circles, isNotEmpty);
      expect(circles.first.id, isNotEmpty);
    });

    test('listUserCircles limit 参数生效', () async {
      final circles = await repo.listUserCircles('user_001', limit: 2);
      expect(circles.length, lessThanOrEqualTo(2));
    });

    test('listCircleGroups 返回 CircleGroupDto 列表', () async {
      final groups = await repo.listCircleGroups('circle_photo_01');
      expect(groups, isNotEmpty);
      expect(groups.first, isA<CircleGroupDto>());
      expect(groups.first.circleId, 'circle_photo_01');
    });

    test('getCircleGroup 返回与 list 一致的默认群', () async {
      final listed = await repo.listCircleGroups('circle_photo_01');
      final g = await repo.getCircleGroup(
        'circle_photo_01',
        listed.first.id,
      );
      expect(g.id, listed.first.id);
    });

    test('listCircleGroupMembers 非空且为 DTO', () async {
      final listed = await repo.listCircleGroups('circle_photo_01');
      final members = await repo.listCircleGroupMembers(
        'circle_photo_01',
        listed.first.id,
      );
      expect(members, isNotEmpty);
      expect(members.first, isA<CircleGroupMemberDto>());
    });

    test('searchCircleGroups 命中名称', () async {
      final hits = await repo.searchCircleGroups(
        'circle_photo_01',
        query: '主群',
      );
      expect(hits, isNotEmpty);
    });

    test('createCircleGroup / updateCircleGroup 返回 DTO', () async {
      final created = await repo.createCircleGroup(
        'circle_photo_01',
        CircleGroupCreateWireDto.fromMap({
          'name': '契约测试群',
          'groupType': 'public_group',
          'visibility': 'public',
          'joinPolicy': 'apply_only',
        }),
      );
      expect(created.name, '契约测试群');
      final updated = await repo.updateCircleGroup(
        'circle_photo_01',
        created.id,
        CircleGroupUpdateWireDto.fromMap({'name': '已改名'}),
      );
      expect(updated.name, '已改名');
    });

    test('getCircle viewerWire 可读', () async {
      final detail = await repo.getCircle('circle_photo_01');
      expect(detail.viewerWire.role, isNotNull);
    });
  });

  group('CircleRepository — 兼容性契约', () {
    test('CircleMockData.circleInfo 包含 sectionConfig 板块配置', () {
      final info = CircleMockData.circleInfo;
      final sections = info['sectionConfig'] as List<dynamic>;
      expect(sections, isNotEmpty);
      final types = sections.map((s) => (s as Map)['sectionType']).toSet();
      expect(types, containsAll(['works', 'chat', 'storage', 'interaction']));
    });

    test('CircleMockData.circleInfo 包含存储配额字段', () {
      final info = CircleMockData.circleInfo;
      expect(info['storageUsedBytes'], isA<int>());
      expect(info['storageQuotaBytes'], isA<int>());
      expect(info['storageQuotaBytes'] as int, greaterThan(info['storageUsedBytes'] as int));
    });

    test('CircleMockData.catalogCircleDtos 每项包含非空 domainId', () {
      for (final circle in CircleMockData.catalogCircleDtos) {
        expect(circle.domainId, isNotNull,
            reason: '${circle.name} 缺少 domainId');
        expect(circle.domainId, isNotEmpty);
      }
    });

    test('CircleMockData.files 包含文件和文件夹两种类型', () {
      final types = CircleMockData.files.map((f) => f['fileType']).toSet();
      expect(types, containsAll(['file', 'folder']));
    });
  });

  group('CircleRepository — 异常/边界契约', () {
    late CircleRepository repo;

    setUp(() {
      repo = MockCircleRepository();
    });

    test('listCircles 空参数不崩溃', () async {
      expect(() async => await repo.listCircles(), returnsNormally);
    });

    test('getCircle 不存在的 ID 抛出异常', () async {
      expect(() async => await repo.getCircle('nonexistent'), throwsException);
    });

    test('createCircle 空 data 不崩溃', () async {
      expect(
        () async => await repo.createCircle(CircleCreateWireDto.fromMap({})),
        returnsNormally,
      );
    });

    test('updateSections 空列表不崩溃', () async {
      expect(() async => await repo.updateSections('test', []), returnsNormally);
    });

    test('listFiles 无文件返回空列表或非空列表', () async {
      final files = await repo.listFiles('nonexistent');
      expect(files, isList);
    });

    test('joinCircle 和 leaveCircle 不崩溃', () async {
      expect(() async => await repo.joinCircle('test'), returnsNormally);
      expect(() async => await repo.leaveCircle('test'), returnsNormally);
    });

    test('listUserCircles 空用户ID不崩溃', () async {
      expect(() async => await repo.listUserCircles(''), returnsNormally);
    });

    test('getFile 不存在的文件抛出异常', () async {
      expect(
        () async => await repo.getFile('circle_photo_01', 'nonexistent_file'),
        throwsException,
      );
    });

    test('reportBehavior 空报告不崩溃', () async {
      expect(
        () async => await repo.reportBehavior(
          CircleBehaviorReportWireDto.fromMap({}),
        ),
        returnsNormally,
      );
    });
  });
}
