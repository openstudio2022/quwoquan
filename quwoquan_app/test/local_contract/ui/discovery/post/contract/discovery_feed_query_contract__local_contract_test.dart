import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

void main() {
  group('DiscoveryFeedQuery contract', () {
    test('moment rail maps to identity=moment without type', () {
      final query = toDiscoveryFeedQuery('moment');
      expect(query.identity, 'moment');
      expect(query.type, isNull);
      expect(
        query.channel,
        isNull,
        reason: '发现页浏览流走时间线具名查询，不携带频道路由',
      );
    });

    test('work format tabs map to identity=work with typed filters', () {
      expect(toDiscoveryFeedQuery('photo').type, 'image');
      expect(toDiscoveryFeedQuery('video').type, 'video');
      expect(toDiscoveryFeedQuery('article').type, 'article');
      expect(toDiscoveryFeedQuery('photo').identity, 'work');
      expect(toDiscoveryFeedQuery('photo').channel, isNull);
    });

    test('premium immersive source maps to channel routing (B3)', () {
      // 精品沉浸流数据源经 channel=premium 路由服务端 premium_stream
      // fail-closed 池；禁止携带 identity/type 落入浏览流。
      final query = toDiscoveryFeedQuery('premium');
      expect(query.channel, 'premium');
      expect(query.identity, isNull);
      expect(query.type, isNull);
    });

    test('home channels map to channel routing without identity/type', () {
      // B1/B16 收口：首页频道一律 channel 语义，禁止携带 identity/type
      // （identity/type 会把请求引到 PostReader 时间流，绕过推荐引擎）。
      for (final channelId in [
        'following',
        'recommend',
        'campus',
        'travel',
        'photography',
        'tech',
        'car',
      ]) {
        final query = toDiscoveryFeedQuery(channelId);
        expect(query.channel, channelId, reason: '$channelId 必须走频道路由');
        expect(query.identity, isNull, reason: '$channelId 不得携带 identity');
        expect(query.type, isNull, reason: '$channelId 不得携带 type');
      }
    });

    test('generated home_channels feed_query is channel-routed', () {
      // metadata 真相源守护：codegen 出的 home_channels 默认 fallback 必须已
      // 切换到 channel 语义（identity/type 从频道 feed_query 中退场）。
      expect(ContentUIConfig.homeChannels, isNotEmpty);
      for (final channel in ContentUIConfig.homeChannels) {
        expect(
          channel.feedQuery['channel'],
          channel.id,
          reason: '${channel.id} 的 feed_query.channel 必须等于频道 id',
        );
        expect(
          channel.feedQuery.containsKey('identity'),
          isFalse,
          reason: '${channel.id} 的 feed_query 不得再声明 identity',
        );
        expect(
          channel.feedQuery.containsKey('type'),
          isFalse,
          reason: '${channel.id} 的 feed_query 不得再声明 type',
        );
      }
    });
  });
}
