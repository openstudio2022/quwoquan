import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/links/share_attribution.dart';

void main() {
  group('ShareAttribution', () {
    test('forShareEvent 生成非空 share_id 并保留传入 UTM', () {
      final a = ShareAttribution.forShareEvent(
        utmSource: ShareAttribution.sourceApp,
        utmMedium: ShareAttribution.mediumSocial,
        utmCampaign: 'launch_w1',
        referral: 'home_feed',
      );

      expect(a.shareId, isNotEmpty);
      expect(a.shareId, startsWith('shr_'));
      expect(a.utmSource, ShareAttribution.sourceApp);
      expect(a.utmMedium, ShareAttribution.mediumSocial);
      expect(a.utmCampaign, 'launch_w1');
      expect(a.referral, 'home_feed');
    });

    test('两次生成 share_id 不同', () {
      final a = ShareAttribution.forShareEvent(
        utmSource: ShareAttribution.sourceApp,
        utmMedium: ShareAttribution.mediumSocial,
      );
      final b = ShareAttribution.forShareEvent(
        utmSource: ShareAttribution.sourceApp,
        utmMedium: ShareAttribution.mediumSocial,
      );
      expect(a.shareId, isNot(b.shareId));
    });

    test('applyTo 向 https 链接追加归因参数且保留原 query', () {
      final a = ShareAttribution(
        shareId: 'shr_x',
        utmSource: 'app',
        utmMedium: 'social',
      );
      final result = a.applyTo('https://quwoquan.com/post/p1?scope=public');
      final uri = Uri.parse(result);

      expect(uri.queryParameters['scope'], 'public');
      expect(uri.queryParameters[ShareAttribution.keyShareId], 'shr_x');
      expect(uri.queryParameters[ShareAttribution.keyUtmSource], 'app');
      expect(uri.queryParameters[ShareAttribution.keyUtmMedium], 'social');
    });

    test('applyTo 仅省略可选空字段', () {
      final a = ShareAttribution(
        shareId: 'shr_x',
        utmSource: 'app',
        utmMedium: 'social',
      );
      final uri = Uri.parse(a.applyTo('https://quwoquan.com/post/p1'));
      expect(uri.queryParameters.containsKey(ShareAttribution.keyUtmCampaign),
          isFalse);
      expect(uri.queryParameters.containsKey(ShareAttribution.keyReferral),
          isFalse);
    });

    test('applyTo 不修改 scheme 深链与空串', () {
      final a = ShareAttribution.forShareEvent(
        utmSource: 'app',
        utmMedium: 'social',
      );
      expect(a.applyTo('quwoquan://content/content/post/p1'),
          'quwoquan://content/content/post/p1');
      expect(a.applyTo(''), '');
    });
  });
}
