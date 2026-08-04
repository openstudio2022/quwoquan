import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/circle/circle_management/circle/circle_query_typed_double.dart';

const _fixtureCircleId = 'fixture_circle_photo';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CircleQueryReader — alpha fixture 读投影契约', () {
    late CircleQueryReader reader;

    setUp(() {
      reader = AlphaCircleQueryReader();
    });

    test('list 返回非空圈子列表', () async {
      final circles = await reader.list(const CircleListQuery());
      expect(circles.items, isNotEmpty);
      expect(circles.items.first.id, isNotEmpty);
      expect(circles.items.first.name, isNotEmpty);
    });

    test('get 返回完整纯投影', () async {
      final detail = await reader.get(
        const CircleDetailQuery(circleId: _fixtureCircleId),
      );
      expect(detail.id, _fixtureCircleId);
      expect(detail.name, isNotEmpty);
      expect(detail.domainId, isNotEmpty);
      expect(detail.autoSyncChat, isTrue);
    });

    test('feed 返回纯内容投影', () async {
      final feed = await reader.feed(
        const CircleFeedQuery(circleId: _fixtureCircleId),
      );
      expect(feed.items, isNotEmpty);
      expect(feed.items.first.postId, isNotEmpty);
    });

    test('discovery feed 使用同一 fixture bundle', () async {
      final feed = await (reader as CircleDiscoveryFeedQueryReader)
          .listDiscoveryFeed(const CircleDiscoveryFeedQuery(limit: 50));
      expect(feed.items, isNotEmpty);
    });

    test('stats 只返回 canonical wire 字段', () async {
      final stats = await reader.stats(
        const CircleStatsQuery(circleId: _fixtureCircleId),
      );
      expect(stats.circleId, _fixtureCircleId);
      expect(stats.memberCount, greaterThanOrEqualTo(0));
      expect(stats.weeklyActiveCount, greaterThanOrEqualTo(0));
      expect(stats.likeCount, greaterThanOrEqualTo(0));
      expect(stats.storageUsedBytes, greaterThanOrEqualTo(0));
    });

    test('impact 保留结构化交叉信息', () async {
      final impact = await reader.impact(
        const CircleImpactQuery(circleId: _fixtureCircleId),
      );
      expect(impact.items, isNotEmpty);
      expect(impact.items.single.primarySpans, isNotEmpty);
      expect(impact.items.single.representativeActor, isNotNull);
    });
  });

  group('CircleQueryReader — fixture 完整性', () {
    late CircleQueryReader reader;

    setUp(() {
      reader = AlphaCircleQueryReader();
    });

    test('list fixture 每项包含非空 domainId', () async {
      final circles = await reader.list(const CircleListQuery(limit: 50));
      expect(circles.items, isNotEmpty);
      for (final circle in circles.items) {
        expect(
          circle.domainId,
          isNotNull,
          reason: '${circle.name} 缺少 domainId',
        );
        expect(circle.domainId, isNotEmpty);
      }
    });
  });

  group('CircleQueryReader — 异常/边界契约', () {
    late CircleQueryReader reader;

    setUp(() {
      reader = AlphaCircleQueryReader();
    });

    test('list 空参数不崩溃', () async {
      expect(
        () async => await reader.list(const CircleListQuery()),
        returnsNormally,
      );
    });

    test('get 不存在的 ID 抛出异常', () async {
      expect(
        () async => await reader.get(const CircleDetailQuery(circleId: 'none')),
        throwsA(isA<StateError>()),
      );
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
      expect(decoded.status, CircleStatus.archived);
      expect(decoded.idempotentReplay, isTrue);
    });
  });
}
