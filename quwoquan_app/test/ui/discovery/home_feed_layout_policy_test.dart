import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_layout_policy.dart';

const _recommend = HomeChannelConfig(
  id: 'recommend',
  labelKey: 'home_tab_recommend',
  template: 'single_column_multiform',
  layoutTemplate: 'singleColumnMultiForm',
  phoneColumns: 1,
  supportsFullSpanModules: false,
  intersectionModulePolicy: 'inlineOnly',
  contentCardPolicy: 'richMultiForm',
  feedQuery: <String, String>{'category': 'micro', 'identity': 'moment'},
  moodCopyKey: 'home_mood_recommend',
  order: 1,
);

const _following = HomeChannelConfig(
  id: 'following',
  labelKey: 'home_tab_following',
  template: 'single_column_relations',
  layoutTemplate: 'singleColumnRelations',
  phoneColumns: 1,
  supportsFullSpanModules: false,
  intersectionModulePolicy: 'none',
  contentCardPolicy: 'richRelation',
  feedQuery: <String, String>{'category': 'following', 'identity': 'moment'},
  moodCopyKey: 'home_mood_following',
  order: 0,
);

void main() {
  group('HomeFeedLayoutPolicy', () {
    testWidgets('手机端推荐频道使用单列多形态内容流', (tester) async {
      late int columns;
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: MediaQuery(
            data: const MediaQueryData(size: Size(390, 844)),
            child: Builder(
              builder: (context) {
                columns = HomeFeedLayoutPolicy.fromChannel(
                  _recommend,
                  fallbackTemplate: _recommend.template,
                ).columnsFor(context);
                return const SizedBox.shrink();
              },
            ),
          ),
        ),
      );
      expect(columns, equals(1));
    });

    testWidgets('关注频道始终单列', (tester) async {
      late int columns;
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: MediaQuery(
            data: const MediaQueryData(size: Size(768, 1024)),
            child: Builder(
              builder: (context) {
                columns = HomeFeedLayoutPolicy.fromChannel(
                  _following,
                  fallbackTemplate: _following.template,
                ).columnsFor(context);
                return const SizedBox.shrink();
              },
            ),
          ),
        ),
      );
      expect(columns, equals(1));
    });

    test('template 缺新字段时降级到单列多形态策略', () {
      final policy = HomeFeedLayoutPolicy.fromTemplateFallback(
        'intersection_rail_masonry',
      );
      expect(policy.phoneColumns, equals(1));
      expect(policy.hasIntersectionSpotlight, isFalse);
      expect(policy.usesCompactDiscoveryCards, isFalse);
      expect(policy.contentCardPolicy, 'richMultiForm');
    });
  });
}
