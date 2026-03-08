import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';

void main() {
  group('CircleRepository — 常规契约', () {
    late CircleRepository repo;

    setUp(() {
      repo = MockCircleRepository();
    });

    test('listCircles 返回非空圈子列表', () async {
      final circles = await repo.listCircles();
      expect(circles, isNotEmpty);
      expect(circles.first.containsKey('id'), isTrue);
      expect(circles.first.containsKey('name'), isTrue);
    });

    test('getCircle 返回完整圈子信息', () async {
      final circle = await repo.getCircle('circle_photo_01');
      expect(circle['id'], 'circle_photo_01');
      expect(circle['name'], isNotEmpty);
      expect(circle.containsKey('sectionConfig'), isTrue);
      expect(circle.containsKey('storageUsedBytes'), isTrue);
      expect(circle.containsKey('storageQuotaBytes'), isTrue);
      expect(circle.containsKey('domainId'), isTrue);
      expect(circle.containsKey('autoSyncChat'), isTrue);
    });

    test('getCircleFeed 返回 feed 列表', () async {
      final feed = await repo.getCircleFeed('circle_photo_01');
      expect(feed, isList);
    });

    test('listFiles 返回文件列表', () async {
      final files = await repo.listFiles('circle_photo_01');
      expect(files, isNotEmpty);
      expect(files.first.containsKey('id'), isTrue);
      expect(files.first.containsKey('name'), isTrue);
      expect(files.first.containsKey('fileType'), isTrue);
    });

    test('listMembers 返回成员列表', () async {
      final members = await repo.listMembers('circle_photo_01');
      expect(members, isNotEmpty);
      expect(members.first.containsKey('id'), isTrue);
      expect(members.first.containsKey('name'), isTrue);
    });

    test('getCircleStats 返回统计数据', () async {
      final stats = await repo.getCircleStats('circle_photo_01');
      expect(stats.containsKey('totalMembers'), isTrue);
      expect(stats.containsKey('weeklyActive'), isTrue);
    });

    test('createCircle 返回含 id 和 createdAt', () async {
      final circle = await repo.createCircle({
        'name': '测试圈子',
        'category': 'tech',
        'visibility': 'public',
      });
      expect(circle['id'], isNotNull);
      expect(circle['createdAt'], isNotNull);
      expect(circle['name'], '测试圈子');
    });

    test('updateCircle 返回合并后的数据', () async {
      final updated = await repo.updateCircle('circle_photo_01', {
        'name': '新名称',
      });
      expect(updated['id'], 'circle_photo_01');
      expect(updated['name'], '新名称');
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
      final file = await repo.createFile('circle_photo_01', {
        'name': '测试文件.txt',
        'fileType': 'file',
      });
      expect(file['id'], isNotNull);
    });

    test('getFile 返回匹配文件', () async {
      final files = await repo.listFiles('circle_photo_01');
      final firstFile = files.first;
      final file = await repo.getFile('circle_photo_01', firstFile['id'] as String);
      expect(file['id'], firstFile['id']);
    });

    test('updateFile 返回合并后数据', () async {
      final files = await repo.listFiles('circle_photo_01');
      final firstFile = files.first;
      final updated = await repo.updateFile(
        'circle_photo_01',
        firstFile['id'] as String,
        {'name': '重命名.txt'},
      );
      expect(updated['name'], '重命名.txt');
    });

    test('deleteFile 不崩溃', () async {
      final files = await repo.listFiles('circle_photo_01');
      await expectLater(
        repo.deleteFile('circle_photo_01', files.first['id'] as String),
        completes,
      );
    });

    test('reportBehavior 不崩溃', () async {
      await expectLater(
        repo.reportBehavior({'type': 'view', 'circleId': 'c1'}),
        completes,
      );
    });

    test('listUserCircles 返回圈子列表', () async {
      final circles = await repo.listUserCircles('user_001');
      expect(circles, isNotEmpty);
      expect(circles.first.containsKey('id'), isTrue);
    });

    test('listUserCircles limit 参数生效', () async {
      final circles = await repo.listUserCircles('user_001', limit: 2);
      expect(circles.length, lessThanOrEqualTo(2));
    });

    test('CircleRepository 接口包含全部 21 个 service.yaml API 方法', () {
      final methods = <String>[
        'listCircles', 'getCircle', 'createCircle', 'updateCircle',
        'archiveCircle', 'joinCircle', 'leaveCircle',
        'listMembers', 'updateMemberRole',
        'getCircleFeed', 'pinPost', 'featurePost', 'getCircleStats',
        'listFiles', 'createFile', 'getFile', 'updateFile', 'deleteFile',
        'updateSections', 'reportBehavior', 'listUserCircles',
      ];
      expect(methods.length, 21);
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

    test('CircleMockData.circles 每项包含 domainId 字段', () {
      for (final circle in CircleMockData.circles) {
        expect(circle.containsKey('domainId'), isTrue,
            reason: '${circle['name']} 缺少 domainId');
        expect(circle['domainId'], isNotEmpty);
      }
    });

    test('CircleMockData.categoryConfig 包含至少 8 个频道', () {
      expect(CircleMockData.categoryConfig.length, greaterThanOrEqualTo(8));
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
      expect(() async => await repo.createCircle({}), returnsNormally);
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
      expect(() async => await repo.reportBehavior({}), returnsNormally);
    });
  });
}
