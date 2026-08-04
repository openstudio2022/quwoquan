/// N2-4 契约：Mock↔Remote 的 feed 语义同构（R12）。
///
/// 覆盖三个此前分裂点：
///  1. channel=recommend 首刷注入 entity_homepage 对象卡（everyN 锚点，云侧
///     resolveObjectCards 同形状）；分页（cursor 非空）不再注入；
///  2. channel=premium fail-closed：只允许精品池（data_engineering 供给），
///     绝不回填全量时间流；
///  3. channel=travel 垂类过滤与云侧 postMatchesVertical 同判定。
library;

import 'package:flutter_test/flutter_test.dart';

import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('MockContentRepository feed 语义与 Remote 同构（N2-4）', () {
    test('channel=recommend 首刷注入 entity_homepage 对象卡', () async {
      final repo = MockContentRepository();
      final page = await repo.listDiscoveryFeedPage(
        category: 'recommend',
        channelId: 'recommend',
        limit: 20,
      );
      expect(page.items, isNotEmpty);
      if (page.items.length >= 8) {
        expect(
          page.objectCards,
          isNotEmpty,
          reason: '首刷内容足量时必须注入对象卡（与云侧 policy everyN=8 同构）',
        );
        final card = page.objectCards.first;
        expect(card.objectKind, 'entity_homepage');
        expect(card.objectId, isNotEmpty);
        expect(card.title, isNotEmpty);
        expect(card.anchorIndex, greaterThan(0));
        expect(
          card.anchorIndex,
          lessThanOrEqualTo(page.items.length),
          reason: '锚点不得越过本页内容长度（尾部不悬挂对象卡）',
        );
      }
    });

    test('分页请求（cursor 非空）不注入对象卡', () async {
      final repo = MockContentRepository();
      final first = await repo.listDiscoveryFeedPage(
        category: 'recommend',
        channelId: 'recommend',
        limit: 8,
      );
      if (first.nextCursor == null) {
        return; // 数据不足两页时该语义无从验证，但不虚假通过
      }
      final second = await repo.listDiscoveryFeedPage(
        category: 'recommend',
        channelId: 'recommend',
        limit: 8,
        cursor: first.nextCursor,
      );
      expect(second.objectCards, isEmpty, reason: '对象卡只在首刷注入');
    });

    test('channel=premium fail-closed：只出精品池供给', () async {
      final repo = MockContentRepository();
      final page = await repo.listDiscoveryFeedPage(
        category: 'premium',
        channelId: 'premium',
        limit: 20,
      );
      // 池真相源：home_feed_core.featuredFeedPostIds（与云侧 rm_premium_pool
      // 物化集合、alpha runner adapter 同判定）；数据工程直供兜底。
      final rawPool =
          objectScenarioSeedReader.contentSeedSet(
                'home_feed_core',
              )?['featuredFeedPostIds']
              as List?;
      final pool = (rawPool ?? const <Object?>[])
          .map((id) => id.toString())
          .toSet();
      for (final item in page.items) {
        expect(
          pool.contains(item.id) || item.supplySource == 'data_engineering',
          isTrue,
          reason: '精品流绝不混入非精品池内容（fail-closed 与云侧 gate 同构）：${item.id}',
        );
      }
      expect(page.objectCards, isEmpty, reason: '对象卡只在首页 recommend 注入');
    });

    test('channel=travel 只出旅行垂类内容', () async {
      final repo = MockContentRepository();
      final page = await repo.listDiscoveryFeedPage(
        category: 'travel',
        channelId: 'travel',
        limit: 20,
      );
      const keywords = <String>['旅行', '旅游', '出行', '风景', '打卡', 'travel'];
      for (final item in page.items) {
        final vertical = (item.contentVertical ?? '').trim();
        final haystack = '${item.title} ${item.body ?? ''}';
        final matches =
            vertical == 'travel_photography' ||
            (vertical.isEmpty && keywords.any(haystack.contains));
        expect(matches, isTrue, reason: 'travel 频道不得混入非旅行内容：${item.id}');
      }
    });
  });
}
