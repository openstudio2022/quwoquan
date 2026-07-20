import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_card.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';

Widget _host(AuthorImpactSummary summary, {required bool isMine}) {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: AuthorImpactCard(
            summary: summary,
            isDark: false,
            isMine: isMine,
          ),
        ),
      ),
    ),
  );
}

/// 触发 InteractiveIntersectionText 中指定文本片段的 TapGestureRecognizer。
///
/// 内联 span 无法用屏幕坐标稳定命中（外层还有整行 CupertinoButton），
/// 这里遍历 InlineSpan 树按文本定位 recognizer 并直接触发，命中返回 true。
bool _tapSpanByText(WidgetTester tester, String text) {
  final richText = tester.widget<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
  var hit = false;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      final recognizer = span.recognizer;
      if (recognizer is TapGestureRecognizer && recognizer.onTap != null) {
        recognizer.onTap!();
        hit = true;
        return false;
      }
    }
    return true;
  });
  return hit;
}

TextSpan _spanByText(WidgetTester tester, String text) {
  final richText = tester.widget<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
  TextSpan? result;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      result = span;
      return false;
    }
    return true;
  });
  return result!;
}

void main() {
  group('AuthorImpactCard', () {
    testWidgets('mine 空摘要展示「我打动的人」鼓励发布空态，无事实行', (tester) async {
      await tester.pumpWidget(
        _host(AuthorImpactSummary(authorId: 'u1'), isMine: true),
      );

      expect(find.text(UITextConstants.profileImpactTitleMine), findsOneWidget);
      expect(find.byKey(AuthorImpactCard.emptyKey), findsOneWidget);
      expect(find.text('23人加入相关圈子'), findsNothing);
    });

    testWidgets('other 空摘要展示稳定空态，不再整卡消失', (tester) async {
      await tester.pumpWidget(
        _host(AuthorImpactSummary(authorId: 'u2'), isMine: false),
      );

      expect(find.byKey(AuthorImpactCard.cardKey), findsOneWidget);
      expect(find.byKey(AuthorImpactCard.emptyKey), findsOneWidget);
      expect(
        find.text(UITextConstants.profileImpactEmptyOther),
        findsOneWidget,
      );
    });

    testWidgets('other 非空摘要展示「TA打动的人」，主页只直出云侧 primaryText', (tester) async {
      final summary = AuthorImpactSummary(
        authorId: 'u2',
        total: 35,
        items: <AuthorImpactItem>[
          AuthorImpactItem(
            helpType: 'community',
            action: 'join',
            intersectionDimension: 'interest',
            source: 'source:circle_join',
            count: 23,
            primaryText: '23人加入相关圈子',
            subtitleText: '来自 AI 产品圈',
          ),
          AuthorImpactItem(
            helpType: 'decision',
            action: 'share',
            intersectionDimension: 'content',
            count: 12,
            primaryText: '12人转发了TA的内容',
            subtitleText: '来自内容转发',
          ),
        ],
      );

      await tester.pumpWidget(_host(summary, isMine: false));

      expect(
        find.text(UITextConstants.profileImpactTitleOther),
        findsOneWidget,
      );
      expect(find.byKey(AuthorImpactCard.emptyKey), findsNothing);
      expect(find.text('23人加入相关圈子'), findsOneWidget);
      expect(find.text('来自 AI 产品圈'), findsNothing);
      expect(find.text('12人转发了TA的内容'), findsOneWidget);
      expect(find.text('来自内容转发'), findsNothing);
    });

    testWidgets('影响事实行可点开查看可枚举来源说明', (tester) async {
      final summary = AuthorImpactSummary(
        authorId: 'u2',
        total: 23,
        items: <AuthorImpactItem>[
          AuthorImpactItem(
            helpType: 'community',
            action: 'join',
            intersectionDimension: 'interest',
            source: 'source:circle_join',
            count: 23,
            primaryText: '23人加入相关圈子',
            subtitleText: '来自 AI 产品圈',
          ),
        ],
      );

      await tester.pumpWidget(_host(summary, isMine: false));
      await tester.tap(find.text('23人加入相关圈子'));
      await tester.pumpAndSettle();

      expect(find.text('23人加入相关圈子'), findsWidgets);
      expect(find.textContaining('source:circle_join'), findsOneWidget);
      expect(
        find.textContaining(UITextConstants.impactEnumerableHintOther),
        findsWidgets,
      );
    });

    testWidgets('摘要区最多渲染前 3 条（规格：取前 3 条 displayText）', (tester) async {
      final summary = AuthorImpactSummary(
        authorId: 'u3',
        total: 40,
        items: <AuthorImpactItem>[
          for (var i = 0; i < 5; i++)
            AuthorImpactItem(
              helpType: 'kind$i',
              action: 'a',
              intersectionDimension: 'content',
              count: 10 - i,
              primaryText: '事实行 $i',
            ),
        ],
      );

      await tester.pumpWidget(_host(summary, isMine: true));

      expect(find.text('事实行 0'), findsOneWidget);
      expect(find.text('事实行 2'), findsOneWidget);
      expect(find.text('事实行 3'), findsNothing);
      expect(find.text('事实行 4'), findsNothing);
    });
  });

  group('AuthorImpactCard 统一交互（数字开明细 / 样本可点击 / 无样本降级）', () {
    testWidgets('数字片段点击进影响明细 sheet（target 缺省也可点击）', (tester) async {
      final summary = AuthorImpactSummary(
        authorId: 'u2',
        total: 23,
        items: <AuthorImpactItem>[
          AuthorImpactItem(
            helpType: 'community',
            action: 'join',
            intersectionDimension: 'interest',
            source: 'source:circle_join',
            count: 23,
            primaryText: '23人加入相关圈子',
            subtitleText: '来自 AI 产品圈',
            // 数字片段无 target：只开明细（消费方按 role==count 拦截），不导航。
            primarySpans: <IntersectionTextSpan>[
              IntersectionTextSpan(text: '23', role: 'count'),
              IntersectionTextSpan(text: '人加入相关圈子', role: 'plain'),
            ],
          ),
        ],
      );

      await tester.pumpWidget(_host(summary, isMine: false));
      // 统一交互蓝字采用低饱和 slogan-accent（浅色态），与全 App 交集语言同源，
      // 不再使用高饱和 iOS systemBlue（避免每条交集句都「喊」）。
      expect(
        _spanByText(tester, '23').style?.color,
        AppColors.profileSloganAccentLight,
      );
      expect(
        _spanByText(tester, '23').style?.fontWeight,
        AppTypography.regular,
      );
      // join(primarySpans.text) == primaryText（端不拼装结论句，G2）。
      expect(_tapSpanByText(tester, '23'), isTrue);
      await tester.pumpAndSettle();

      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetSourceLabel),
        findsOneWidget,
      );
      expect(find.textContaining('source:circle_join'), findsOneWidget);
      expect(
        find.textContaining(UITextConstants.impactEnumerableHintOther),
        findsWidgets,
      );
    });

    testWidgets('明细 sheet 中样本视觉可点击进对应对象主页', (tester) async {
      final behaviorRepo = MockBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        reporter: behaviorRepo,
        maxBatchSize: 1,
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);

      final summary = AuthorImpactSummary(
        authorId: 'u2',
        total: 23,
        items: <AuthorImpactItem>[
          AuthorImpactItem(
            helpType: 'community',
            action: 'join',
            intersectionDimension: 'interest',
            source: 'source:circle_join',
            count: 23,
            primaryText: '23人加入相关圈子',
            subtitleText: '来自 AI 产品圈',
            sampleVisuals: <IntersectionVisual>[
              IntersectionVisual(
                assetKind: 'avatar',
                displayName: '阿岚',
                target: IntersectionTarget(
                  objectId: 'u_alan',
                  objectKind: 'person',
                  routeId: 'userProfile',
                ),
              ),
            ],
          ),
        ],
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            behaviorRepositoryProvider.overrideWithValue(behaviorRepo),
            contentBehaviorTrackerProvider.overrideWithValue(tracker),
            profileQueryProvider.overrideWith(
              (ref, surface) => const MockUserProfileRepository(),
            ),
            authorImpactQueryProvider.overrideWithValue(
              const MockUserProfileRepository(),
            ),
          ],
          child: MaterialApp.router(
            routerConfig: GoRouter(
              initialLocation: '/',
              routes: <RouteBase>[
                GoRoute(
                  path: '/',
                  builder: (_, _) => Scaffold(
                    body: SingleChildScrollView(
                      child: AuthorImpactCard(
                        summary: summary,
                        isDark: false,
                        isMine: false,
                      ),
                    ),
                  ),
                ),
                GoRoute(
                  path: '/user/:username',
                  builder: (_, state) =>
                      Text('USER:${state.pathParameters['username']}'),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('23人加入相关圈子'));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('阿岚'));
      await tester.pumpAndSettle();

      expect(find.text('USER:u_alan'), findsOneWidget);
      expect(behaviorRepo.recorded.single.contentId, 'u_alan');
    });

    testWidgets('无样本 + 明细分页为空 → sheet 空态文案，不渲染样本簇与全量待补脚注', (tester) async {
      // 无 sampleVisuals 且云侧明细分页为空（Mock 仓库无命中 impact）→ 空态文案，
      // 既不回退样本簇也不展示「全量待补」脚注（不造假、不占位）。
      final summary = AuthorImpactSummary(
        authorId: 'u2',
        total: 12,
        items: <AuthorImpactItem>[
          AuthorImpactItem(
            helpType: 'decision',
            action: 'share',
            intersectionDimension: 'content',
            source: 'source:repost',
            count: 12,
            primaryText: '12人转发了TA的内容',
            subtitleText: '来自内容转发',
          ),
        ],
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileQueryProvider.overrideWith(
              (ref, surface) => const MockUserProfileRepository(),
            ),
            authorImpactQueryProvider.overrideWithValue(
              const MockUserProfileRepository(),
            ),
          ],
          child: _host(summary, isMine: false),
        ),
      );
      await tester.tap(find.text('12人转发了TA的内容'));
      await tester.pumpAndSettle();

      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetEmptyNote),
        findsOneWidget,
      );
      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetFullPendingNote),
        findsNothing,
      );
      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetNoSampleNote),
        findsNothing,
      );
      expect(find.byType(IntersectionVisualCluster), findsNothing);
    });
  });
}
