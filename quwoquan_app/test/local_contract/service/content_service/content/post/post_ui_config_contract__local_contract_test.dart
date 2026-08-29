import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/content_media_viewer_policy_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 契约测试：ContentUIConfig — 覆盖 mock.yaml ui_config_scenarios
///
/// 确保 codegen 输出与 ui_config.yaml 元数据一致。
void main() {
  group('ContentUIConfig — home_channels contract', () {
    // 频道是运营资产：端 meta 默认（发布自带 fallback），云侧可远程覆盖。
    // 本组锁定首页默认频道集与有限模板类型，防止视频书退回独立壳层入口。
    test('home_channels — exactly 8 default channels', () {
      expect(ContentUIConfig.homeChannels.length, equals(8));
    });

    test('home_channels ids: 关注/推荐/视频书/校园/旅行/摄影/科技/车友', () {
      expect(
        ContentUIConfig.homeChannels.map((channel) => channel.id).toList(),
        equals(<String>[
          'following',
          'recommend',
          'featured',
          'campus',
          'travel',
          'photography',
          'tech',
          'car',
        ]),
      );
    });

    test(
      'home_channels order is monotonic 0..7 matching declared sequence',
      () {
        final ordered = <HomeChannelConfig>[...ContentUIConfig.homeChannels]
          ..sort((a, b) => a.order.compareTo(b.order));
        expect(
          ordered.map((c) => c.order).toList(),
          equals(<int>[0, 1, 2, 3, 4, 5, 6, 7]),
          reason: 'order 必须连续单调，运营调序仅改 order 即生效',
        );
        expect(
          ordered.map((c) => c.id).toList(),
          equals(<String>[
            'following',
            'recommend',
            'featured',
            'campus',
            'travel',
            'photography',
            'tech',
            'car',
          ]),
        );
      },
    );

    test('home_channels templates belong to the finite template set', () {
      // 端只实现有限频道模板类型，运营选模板+配参数，不做无限动态布局。
      const allowedTemplates = <String>{
        'single_column_relations',
        'single_column_multiform',
        'premium_immersive',
      };
      for (final channel in ContentUIConfig.homeChannels) {
        expect(
          allowedTemplates.contains(channel.template),
          isTrue,
          reason: '频道 ${channel.id} 模板 ${channel.template} 不在有限模板集',
        );
      }
    });

    test(
      'home_channels layout policies use single-column multiform discovery',
      () {
        const allowedLayoutTemplates = <String>{
          'singleColumnRelations',
          'singleColumnMultiForm',
          'immersivePremiumStream',
        };
        const allowedIntersectionPolicies = <String>{
          'none',
          'spotlightSegment',
          'campusSpotlight',
          'segmentInsert',
          'inlineOnly',
        };
        const allowedCardPolicies = <String>{
          'richRelation',
          'compactVisual',
          'articleFullSpan',
          'richMultiForm',
          'premiumImmersive',
        };

        for (final channel in ContentUIConfig.homeChannels) {
          expect(
            allowedLayoutTemplates.contains(channel.layoutTemplate),
            isTrue,
            reason: '频道 ${channel.id} layoutTemplate 不在有限集合',
          );
          expect(
            channel.phoneColumns,
            inInclusiveRange(1, 2),
            reason: '手机端只允许单列或双列',
          );
          expect(
            allowedIntersectionPolicies.contains(
              channel.intersectionModulePolicy,
            ),
            isTrue,
            reason: '频道 ${channel.id} 交集模块策略非法',
          );
          expect(
            allowedCardPolicies.contains(channel.contentCardPolicy),
            isTrue,
            reason: '频道 ${channel.id} 卡片策略非法',
          );
        }

        final following = ContentUIConfig.homeChannels.firstWhere(
          (c) => c.id == 'following',
        );
        expect(following.phoneColumns, equals(1));
        expect(following.layoutTemplate, equals('singleColumnRelations'));

        final featured = ContentUIConfig.homeChannels.firstWhere(
          (channel) => channel.id == 'featured',
        );
        expect(featured.template, equals('premium_immersive'));
        expect(featured.layoutTemplate, equals('immersivePremiumStream'));
        expect(featured.contentCardPolicy, equals('premiumImmersive'));
        expect(featured.feedQuery['channel'], equals('premium'));

        for (final id in <String>[
          'recommend',
          'campus',
          'travel',
          'photography',
          'tech',
          'car',
        ]) {
          final channel = ContentUIConfig.homeChannels.firstWhere(
            (c) => c.id == id,
          );
          expect(channel.phoneColumns, equals(1), reason: '$id 手机端为单列多形态流');
          expect(channel.contentCardPolicy, equals('richMultiForm'));
        }
      },
    );

    test('following channel uses channel-routed relations template', () {
      final following = ContentUIConfig.homeChannels.firstWhere(
        (c) => c.id == 'following',
      );
      expect(following.template, equals('single_column_relations'));
      expect(following.feedQuery['channel'], equals('following'));
      expect(following.feedQuery.containsKey('identity'), isFalse);
      expect(following.feedQuery.containsKey('type'), isFalse);
    });

    test(
      'each channel has non-empty labelKey + feedQuery + resolvable moodCopy',
      () {
        for (final channel in ContentUIConfig.homeChannels) {
          expect(
            channel.labelKey,
            isNotEmpty,
            reason: '频道 ${channel.id} 缺 labelKey',
          );
          expect(
            channel.feedQuery,
            isNotEmpty,
            reason: '频道 ${channel.id} 缺 feedQuery',
          );
          // moodCopyKey 必须可被端文案解析器解析（端只读展示、不本地拼）。
          final mood = UITextConstants.homeChannelMoodCopy(channel.moodCopyKey);
          expect(
            mood,
            isNotEmpty,
            reason:
                '频道 ${channel.id} 的 moodCopyKey ${channel.moodCopyKey} 无法解析',
          );
        }
      },
    );
  });

  group('ContentUIConfig — ui_config_scenarios contract', () {
    test('discovery_tabs_count — exactly 4 tabs defined', () {
      expect(ContentUIConfig.discoveryTabs.length, equals(4));
    });

    test('discovery tabs have correct ids: photo, video, moment, article', () {
      final ids = ContentUIConfig.discoveryTabs.map((t) => t.id).toList();
      expect(ids, containsAll(['photo', 'video', 'moment', 'article']));
    });

    test('discovery_tabs_order: photo → video → moment → article', () {
      // Tab order defines the display order in DiscoveryPage's TabBar.
      // Changing this order is a UI regression that MUST be caught by this test.
      final ids = ContentUIConfig.discoveryTabs.map((t) => t.id).toList();
      expect(
        ids.indexOf('photo'),
        lessThan(ids.indexOf('video')),
        reason: 'photo tab must appear before video',
      );
      expect(
        ids.indexOf('video'),
        lessThan(ids.indexOf('moment')),
        reason: 'video tab must appear before moment',
      );
      expect(
        ids.indexOf('moment'),
        lessThan(ids.indexOf('article')),
        reason: 'moment tab must appear before article',
      );
    });

    test('photo tab uses waterfall_grid layout', () {
      final photoTab = ContentUIConfig.discoveryTabs.firstWhere(
        (t) => t.id == 'photo',
      );
      expect(photoTab.layout, equals('waterfall_grid'));
      expect(photoTab.contentType, equals('image'));
    });

    test('video tab uses full_width_vertical_pager layout', () {
      final videoTab = ContentUIConfig.discoveryTabs.firstWhere(
        (t) => t.id == 'video',
      );
      expect(videoTab.layout, equals('full_width_vertical_pager'));
      expect(videoTab.contentType, equals('video'));
    });

    test('moment tab uses list_with_optional_media layout', () {
      final momentTab = ContentUIConfig.discoveryTabs.firstWhere(
        (t) => t.id == 'moment',
      );
      expect(momentTab.layout, equals('list_with_optional_media'));
      expect(momentTab.contentType, equals('micro'));
    });

    test('article tab uses list_with_cover layout', () {
      final articleTab = ContentUIConfig.discoveryTabs.firstWhere(
        (t) => t.id == 'article',
      );
      expect(articleTab.layout, equals('list_with_cover'));
      expect(articleTab.contentType, equals('article'));
    });

    test('feature_flags_complete — required flags present', () {
      expect(
        ContentUIConfig.featureFlags.containsKey('enable_helper_read'),
        isTrue,
      );
      expect(
        ContentUIConfig.featureFlags.containsKey('enable_behavior_tracking'),
        isTrue,
      );
      expect(
        ContentUIConfig.featureFlags.containsKey('enable_photo_waterfall'),
        isTrue,
      );
      expect(
        ContentUIConfig.featureFlags.containsKey(
          'enable_identity_based_surfaces',
        ),
        isTrue,
      );
    });

    test('article book feature flags present', () {
      expect(
        ContentUIConfig.featureFlags.containsKey('enable_article_book_reader'),
        isTrue,
      );
      expect(
        ContentUIConfig.featureFlags['enable_article_page_curl'],
        isTrue,
        reason: 'page curl 是文章阅读默认交互，禁用只能来自显式 runtime override',
      );
      expect(
        ContentUIConfig.featureFlags.containsKey(
          'enable_article_distribution_profiles',
        ),
        isTrue,
      );
    });

    test('feature flags all have bool defaults', () {
      for (final entry in ContentUIConfig.featureFlags.entries) {
        expect(
          entry.value,
          isA<bool>(),
          reason: '${entry.key} must have a bool default',
        );
      }
    });

    test('card_config_all_types — emptyStates has feed_empty key', () {
      expect(ContentUIConfig.emptyStates.containsKey('feed_empty'), isTrue);
    });

    test('each tab has a non-empty labelKey and icon', () {
      for (final tab in ContentUIConfig.discoveryTabs) {
        expect(
          tab.labelKey,
          isNotEmpty,
          reason: 'Tab ${tab.id} must have a labelKey',
        );
        expect(tab.icon, isNotEmpty, reason: 'Tab ${tab.id} must have an icon');
      }
    });

    test('feature_flags no duplicates — all keys are unique', () {
      final keys = ContentUIConfig.featureFlags.keys.toList();
      final uniqueKeys = keys.toSet();
      expect(
        keys.length,
        equals(uniqueKeys.length),
        reason: 'feature_flags keys must be unique',
      );
    });

    test('discovery rails order: moment → work', () {
      final ids = ContentUIConfig.discoveryRails
          .map((rail) => rail.id)
          .toList();
      expect(ids, equals(<String>['moment', 'work']));
    });

    test('creation identity filters expose all / moment / work', () {
      final ids = ContentUIConfig.creationIdentityFilters
          .map((filter) => filter.id)
          .toList();
      expect(ids, equals(<String>['all', 'moment', 'work']));
    });

    test('work format filters expose all / image / video / article', () {
      final ids = ContentUIConfig.workFormatFilters
          .map((filter) => filter.id)
          .toList();
      expect(ids, equals(<String>['all', 'image', 'video', 'article']));
      final article = ContentUIConfig.workFormatFilters.firstWhere(
        (filter) => filter.id == 'article',
      );
      expect(article.contentType, 'article');
      expect(article.labelKey, 'work_format_article');
    });

    test('media playback public port mirrors viewer policy values', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final policy = container.read(contentMediaViewerPolicyProvider);
      expect(policy.workFormatFilters.map((filter) => filter.id), <String>[
        'all',
        'image',
        'video',
        'article',
      ]);
      expect(
        policy.articleDarkPaperDefaultTheme,
        ContentUIConfig.articleDarkPaperDefaultTheme,
      );
      expect(
        policy.articlePaperThemeOptions.map((option) => option.id),
        ContentUIConfig.articlePaperThemeOptions.map((option) => option.id),
      );
    });

    test('article template configs freeze five book presets', () {
      final ids = ContentUIConfig.articleTemplateConfigs
          .map((config) => config.id)
          .toSet();
      expect(
        ids,
        equals(<String>{'gentle', 'ritual', 'diffuse', 'journal', 'tech'}),
      );
    });

    test(
      'article distribution profiles cover follow list and circle dual column',
      () {
        final ids = ContentUIConfig.articleDistributionProfiles
            .map((profile) => profile.id)
            .toList();
        expect(
          ids,
          containsAll(<String>[
            'follow_list_with_optional_cover',
            'circle_dual_column_with_optional_cover',
          ]),
        );
      },
    );

    test('article reader profiles freeze full screen stage and top nav page fraction', () {
      final ids = ContentUIConfig.articleReaderProfiles
          .map((profile) => profile.id)
          .toList();
      expect(
        ids,
        containsAll(<String>[
          'full_screen_book_stage',
          'top_nav_with_page_fraction',
        ]),
      );
      final fullScreen = ContentUIConfig.articleReaderProfiles.firstWhere(
        (profile) => profile.id == 'full_screen_book_stage',
      );
      expect(fullScreen.pageIndicatorAnchor, equals('top_after_back'));
      expect(fullScreen.supportsPageCurl, isTrue);
    });

    test('article template recommendations cover核心圈子频道', () {
      final tech = ContentUIConfig.articleTemplateRecommendations.firstWhere(
        (entry) => entry.categoryId == 'tech',
      );
      final humanity = ContentUIConfig.articleTemplateRecommendations
          .firstWhere((entry) => entry.categoryId == 'humanity');
      expect(
        tech.recommendedArticleTemplates,
        containsAll(<String>['tech', 'diffuse']),
      );
      expect(
        humanity.recommendedArticleTemplates,
        containsAll(<String>['journal', 'ritual']),
      );
    });
  });
}
