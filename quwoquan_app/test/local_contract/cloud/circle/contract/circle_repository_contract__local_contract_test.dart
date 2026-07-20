import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _fixtureCircleId = 'fixture_circle_photo';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CircleRepository — 读投影契约', () {
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

    test('getCircleStats 返回统计数据', () async {
      final stats = await repo.getCircleStats(_fixtureCircleId);
      expect(stats.raw.containsKey('memberCount'), isTrue);
      expect(stats.raw.containsKey('weeklyActiveCount'), isTrue);
      expect(stats.raw.containsKey('totalMembers'), isFalse);
      expect(stats.raw.containsKey('weeklyActive'), isFalse);
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
      // 与 metadata ui_config circle_sections 闭集一致（works/members/chat/storage）。
      expect(types, containsAll(['works', 'members', 'chat', 'storage']));
      expect(types, isNot(contains('interaction')));
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
  });

  group('Circle 生命周期命令 typed 契约', () {
    test('typed 命令拒绝空白标识与非法 sections', () {
      expect(() => CreateCircleCommand(name: '  '), throwsArgumentError);
      expect(() => UpdateCircleCommand(circleId: ''), throwsArgumentError);
      expect(
        () => UpdateCircleSectionsCommand(circleId: 'c1', sections: const []),
        throwsArgumentError,
      );
    });

    test('decodeCircleCommandResult 拒绝未知键与非法版本', () {
      expect(
        () => decodeCircleCommandResult(<String, Object?>{
          'circleId': 'c1',
          'version': 1,
          'status': 'active',
          'idempotentReplay': false,
          'unexpected': true,
        }),
        throwsFormatException,
      );
      expect(
        () => decodeCircleCommandResult(<String, Object?>{
          'circleId': 'c1',
          'version': 0,
          'status': 'active',
          'idempotentReplay': false,
        }),
        throwsFormatException,
      );
      final decoded = decodeCircleCommandResult(<String, Object?>{
        'circleId': 'c1',
        'version': 3,
        'status': 'archived',
        'idempotentReplay': true,
      });
      expect(decoded.status, CircleLifecycleStatus.archived);
      expect(decoded.idempotentReplay, isTrue);
    });
  });
}
