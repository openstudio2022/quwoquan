import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';

const _fixtureCircleId = 'fixture_circle_photo';

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
      expect(stats.raw.containsKey('memberCount'), isTrue);
      expect(stats.raw.containsKey('weeklyActiveCount'), isTrue);
      expect(stats.raw.containsKey('totalMembers'), isFalse);
      expect(stats.raw.containsKey('weeklyActive'), isFalse);
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
  });
}
