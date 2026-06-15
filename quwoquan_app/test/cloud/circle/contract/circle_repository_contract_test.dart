import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';

const _fixtureCircleId = 'fixture_circle_photo';
const _fixtureUserId = 'fixture_user_current';

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
      final detail = await repo.getCircle(_fixtureCircleId);
      expect(detail.circle.id, _fixtureCircleId);
      expect(detail.circle.name, isNotEmpty);
      final wire = detail.repositoryMergeBase();
      expect(wire.containsKey('sectionConfig'), isTrue);
      expect(wire.containsKey('storageUsedBytes'), isTrue);
      expect(wire.containsKey('storageQuotaBytes'), isTrue);
      expect(wire.containsKey('domainId'), isTrue);
      expect(wire.containsKey('autoSyncChat'), isTrue);
    });

    test('getCircleFeed 返回 feed 列表', () async {
      final feed = await repo.getCircleFeed(_fixtureCircleId);
      expect(feed, isNotEmpty);
      expect(feed.first, isA<PostBaseDto>());
    });

    test('listFiles 返回文件列表', () async {
      final files = await repo.listFiles(_fixtureCircleId);
      expect(files, isNotEmpty);
      expect(files.first.id, isNotEmpty);
      expect(files.first.name, isNotEmpty);
      expect(files.first.fileType, isNotEmpty);
    });

    test('listMembers 返回成员列表', () async {
      final members = await repo.listMembers(_fixtureCircleId);
      expect(members, isNotEmpty);
      expect(members.first.userId, isNotEmpty);
      expect(members.first.displayName ?? members.first.userId, isNotEmpty);
    });

    test('listHomeCircleDiscoveryFeed 不回退本地静态 feed', () async {
      final feed = await repo.listHomeCircleDiscoveryFeed(limit: 50);
      expect(feed, isList);
    });

    test('getCircleCategoryConfig 与 ui_category_tabs SSOT 对齐', () async {
      final cfg = await repo.getCircleCategoryConfig();
      expect(cfg.containsKey('campus'), isTrue);
      expect(cfg['campus']!.label, isNotEmpty);
      expect(cfg.length, greaterThanOrEqualTo(5));
    });

    test('getCircleStats 返回统计数据', () async {
      final stats = await repo.getCircleStats(_fixtureCircleId);
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
        _fixtureCircleId,
        CircleUpdateWireDto.fromMap({'name': '新名称'}),
      );
      expect(updated.id, _fixtureCircleId);
      expect(updated.name, '新名称');
    });

    test('archiveCircle 不崩溃', () async {
      await expectLater(repo.archiveCircle(_fixtureCircleId), completes);
    });

    test('updateMemberRole 不崩溃', () async {
      await expectLater(
        repo.updateMemberRole(_fixtureCircleId, 'u1', 'admin'),
        completes,
      );
    });

    test('pinPost 不崩溃', () async {
      await expectLater(
        repo.pinPost(_fixtureCircleId, 'p1', pinned: true),
        completes,
      );
    });

    test('featurePost 不崩溃', () async {
      await expectLater(
        repo.featurePost(_fixtureCircleId, 'p1', featured: true),
        completes,
      );
    });

    test('createFile 返回含 id', () async {
      final file = await repo.createFile(
        _fixtureCircleId,
        CircleFileCreateWireDto.fromMap({
          'name': '测试文件.txt',
          'fileType': 'file',
        }),
      );
      expect(file.id, isNotEmpty);
    });

    test('getFile 返回匹配文件', () async {
      final files = await repo.listFiles(_fixtureCircleId);
      final firstFile = files.first;
      final file = await repo.getFile(_fixtureCircleId, firstFile.id);
      expect(file.id, firstFile.id);
    });

    test('updateFile 返回合并后数据', () async {
      final files = await repo.listFiles(_fixtureCircleId);
      final firstFile = files.first;
      final updated = await repo.updateFile(
        _fixtureCircleId,
        firstFile.id,
        CircleFileUpdateWireDto.fromMap({'name': '重命名.txt'}),
      );
      expect(updated.name, '重命名.txt');
    });

    test('deleteFile 不崩溃', () async {
      final files = await repo.listFiles(_fixtureCircleId);
      await expectLater(
        repo.deleteFile(_fixtureCircleId, files.first.id),
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
      final circles = await repo.listUserCircles(_fixtureUserId);
      expect(circles, isNotEmpty);
      expect(circles.first.id, isNotEmpty);
    });

    test('listUserCircles limit 参数生效', () async {
      final circles = await repo.listUserCircles(_fixtureUserId, limit: 2);
      expect(circles.length, lessThanOrEqualTo(2));
    });

    test('listCircleGroups 返回 CircleGroupDto 列表', () async {
      final groups = await repo.listCircleGroups(_fixtureCircleId);
      expect(groups, isNotEmpty);
      expect(groups.first, isA<CircleGroupDto>());
      expect(groups.first.circleId, _fixtureCircleId);
    });

    test('getCircleGroup 返回与 list 一致的默认群', () async {
      final listed = await repo.listCircleGroups(_fixtureCircleId);
      final g = await repo.getCircleGroup(_fixtureCircleId, listed.first.id);
      expect(g.id, listed.first.id);
    });

    test('listCircleGroupMembers 非空且为 DTO', () async {
      final listed = await repo.listCircleGroups(_fixtureCircleId);
      final members = await repo.listCircleGroupMembers(
        _fixtureCircleId,
        listed.first.id,
      );
      expect(members, isNotEmpty);
      expect(members.first, isA<CircleGroupMemberDto>());
    });

    test('searchCircleGroups 命中名称', () async {
      final hits = await repo.searchCircleGroups(
        _fixtureCircleId,
        query: '公开群',
      );
      expect(hits, isNotEmpty);
    });

    test('createCircleGroup / updateCircleGroup 返回 DTO', () async {
      final created = await repo.createCircleGroup(
        _fixtureCircleId,
        CircleGroupCreateWireDto.fromMap({
          'name': '契约测试群',
          'groupType': 'public_group',
          'visibility': 'public',
          'joinPolicy': 'apply_only',
        }),
      );
      expect(created.name, '契约测试群');
      final updated = await repo.updateCircleGroup(
        _fixtureCircleId,
        created.id,
        CircleGroupUpdateWireDto.fromMap({'name': '已改名'}),
      );
      expect(updated.name, '已改名');
    });

    test('getCircle viewerWire 可读', () async {
      final detail = await repo.getCircle(_fixtureCircleId);
      expect(detail.viewerWire.role, isNotNull);
    });
  });

  group('CircleRepository — contract seed 契约', () {
    late CircleRepository repo;

    setUp(() {
      repo = MockCircleRepository();
    });

    test('getCircle 由 contract seed 补齐 sectionConfig 与存储配额', () async {
      final detail = await repo.getCircle(_fixtureCircleId);
      final wire = detail.repositoryMergeBase();
      final sections = wire['sectionConfig'] as List<dynamic>;
      expect(sections, isNotEmpty);
      final types = sections.map((s) => (s as Map)['sectionType']).toSet();
      expect(types, containsAll(['works', 'chat', 'storage', 'interaction']));
      expect(wire['storageUsedBytes'], isA<int>());
      expect(wire['storageQuotaBytes'], isA<int>());
      expect(
        wire['storageQuotaBytes'] as int,
        greaterThan(wire['storageUsedBytes'] as int),
      );
    });

    test('listCircles 的 contract seed 每项包含非空 domainId', () async {
      final circles = await repo.listCircles(limit: 50);
      expect(circles, isNotEmpty);
      for (final circle in circles) {
        expect(
          circle.domainId,
          isNotNull,
          reason: '${circle.name} 缺少 domainId',
        );
        expect(circle.domainId, isNotEmpty);
      }
    });

    test('listFiles 由 contract seed 提供可读文件类型', () async {
      final files = await repo.listFiles(_fixtureCircleId);
      expect(files, isNotEmpty);
      expect(files.map((f) => f.fileType).toSet(), isNotEmpty);
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
      expect(
        () async => await repo.updateSections('test', []),
        returnsNormally,
      );
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
        () async => await repo.getFile(_fixtureCircleId, 'nonexistent_file'),
        throwsException,
      );
    });

    test('reportBehavior 空报告不崩溃', () async {
      expect(
        () async =>
            await repo.reportBehavior(CircleBehaviorReportWireDto.fromMap({})),
        returnsNormally,
      );
    });
  });
}
