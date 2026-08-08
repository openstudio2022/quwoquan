import 'package:flutter/cupertino.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_icon_resolver.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_reason_chip.dart';

import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// A4 / N5：内容卡交集理由位 / post 作者信任徽标口径一致（云侧主结论句直出，G2 端不本地
/// 拼装）+ 渲染归一（统一 [IntersectionTypeIcon] + 可点击 [InteractiveIntersectionText]）。
Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

const String _validPrimaryText = '联系人林清越等2人赞过《川西雪山和校园摄影路线》';

IntersectionTarget _actorTarget() => intersectionTargetFixture(
  objectType: 'user',
  objectId: 'u_lin',
  objectKind: 'person',
  routeId: 'userProfile',
);

IntersectionTarget _objectTarget() => intersectionTargetFixture(
  objectType: 'post',
  objectId: 'post_snow_route',
  objectKind: 'content',
  routeId: 'workBrowser',
);

List<IntersectionTextSpan> _validPrimarySpans() => <IntersectionTextSpan>[
  intersectionTextSpanFixture(text: '联系人', role: 'plain'),
  intersectionTextSpanFixture(
    text: '林清越',
    role: 'object',
    target: _actorTarget(),
  ),
  intersectionTextSpanFixture(text: '等', role: 'plain'),
  intersectionTextSpanFixture(
    text: '2',
    role: 'count',
    target: intersectionTargetFixture(
      objectType: 'dimension',
      objectId: 'content',
      objectKind: 'dimension',
      routeId: 'myIntersections',
    ),
  ),
  intersectionTextSpanFixture(text: '人赞过', role: 'plain'),
  intersectionTextSpanFixture(
    text: '《川西雪山和校园摄影路线》',
    role: 'object',
    target: _objectTarget(),
  ),
];

IntersectionReason _reason({
  String primaryText = _validPrimaryText,
  String connectionSummary = '',
  String weightTier = '',
  List<IntersectionTextSpan>? primarySpans,
  String iconKey = '',
  String source = 'coCommented',
  String dimension = 'content',
  String intersectionId = 'ix_chip',
  String intersectionClass = 'fact',
  String actionTargetId = 'post_snow_route',
  String objectKind = 'content',
  String displayBinding = 'explicit_link',
}) {
  return intersectionReasonFixture(
    dimension: dimension,
    source: source,
    iconKey: iconKey,
    primaryText: primaryText,
    connectionSummary: connectionSummary,
    weightTier: weightTier,
    primarySpans: primarySpans ?? _validPrimarySpans(),
    intersectionId: intersectionId,
    intersectionClass: intersectionClass,
    actionTargetId: actionTargetId,
    objectKind: objectKind,
    displayBinding: displayBinding,
    actorEvidenceTotalCount: 2,
    actorEvidenceCompleteness: 'complete',
    representativeActor: intersectionRepresentativeActorFixture(
      actorId: 'u_lin',
      displayName: '林清越',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: _actorTarget(),
    ),
  );
}

TextSpan _spanByText(RichText richText, String text) {
  TextSpan? found;
  void visit(InlineSpan span) {
    if (found != null) return;
    if (span is TextSpan) {
      if (span.text == text) {
        found = span;
        return;
      }
      final children = span.children;
      if (children != null) {
        for (final child in children) {
          visit(child);
        }
      }
    }
  }

  visit(richText.text);
  return found!;
}

Widget _routedChip(Widget chip, {required ContentBehaviorTracker tracker}) {
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (context, state) => Center(child: chip),
      ),
      GoRoute(
        path: '/user/:userHandle',
        builder: (context, state) => const Text('user-profile-route'),
      ),
    ],
  );
  return ProviderScope(
    overrides: [contentBehaviorTrackerProvider.overrideWithValue(tracker)],
    child: CupertinoApp.router(routerConfig: router),
  );
}

void main() {
  group('IntersectionReasonChip.primaryText 唯一口径（云侧主结论句直出）', () {
    test('取首条完整 SVO 理由的 primaryText', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[_reason()]),
        _validPrimaryText,
      );
    });

    test('primaryText 缺省 → null，不用 connectionSummary 兜底', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          _reason(
            primaryText: '',
            primarySpans: const <IntersectionTextSpan>[],
            connectionSummary: '你和 TA 都来自同一校园',
          ),
        ]),
        isNull,
      );
    });

    test('零内部词：合格主句不出现「个交集点」', () {
      final text = IntersectionReasonChip.primaryText(<IntersectionReason>[
        _reason(),
      ]);
      expect(text, isNotNull);
      expect(text!.contains('个交集点'), isFalse);
    });

    test('null / 空列表 → null（不展示）', () {
      expect(IntersectionReasonChip.primaryText(null), isNull);
      expect(
        IntersectionReasonChip.primaryText(const <IntersectionReason>[]),
        isNull,
      );
    });

    test('无可展示结论句 → null（不展示）', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          intersectionReasonFixture(dimension: 'relationship'),
        ]),
        isNull,
      );
    });

    test('host_implicit 内容卡省略当前内容宾语，但必须传入当前 post context', () {
      final reason = _reason(
        displayBinding: 'host_implicit',
        primaryText: '联系人林清越等2人赞过',
        primarySpans: <IntersectionTextSpan>[
          intersectionTextSpanFixture(text: '联系人', role: 'plain'),
          intersectionTextSpanFixture(
            text: '林清越',
            role: 'object',
            target: _actorTarget(),
          ),
          intersectionTextSpanFixture(text: '等', role: 'plain'),
          intersectionTextSpanFixture(
            text: '2',
            role: 'count',
            target: intersectionTargetFixture(
              objectType: 'dimension',
              objectId: 'content',
              objectKind: 'dimension',
              routeId: 'myIntersections',
            ),
          ),
          intersectionTextSpanFixture(text: '人赞过', role: 'plain'),
        ],
      );

      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[reason]),
        isNull,
      );
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          reason,
        ], contextObjectTarget: _objectTarget()),
        '联系人林清越等2人赞过',
      );
    });

    test('explicit_link 不允许在宿主内容卡渲染可点击 self-target', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          _reason(),
        ], contextObjectTarget: _objectTarget()),
        isNull,
      );
    });
  });

  group('IntersectionReasonChip.fromReasons 构造口径', () {
    testWidgets('有主结论句 → 渲染云侧 primaryText', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(),
      ], isDark: false);
      expect(widget, isNotNull);
      await tester.pumpWidget(_wrap(widget!));
      expect(find.text(_validPrimaryText), findsOneWidget);
    });

    test('无来源 → 返回 null（调用方不插入，保证四口径一致）', () {
      expect(IntersectionReasonChip.fromReasons(null, isDark: false), isNull);
    });
  });

  // ── N5：槽①图标归一到统一 IntersectionTypeIcon（删本组件第二套 kind switch）──
  group('IntersectionReasonChip 图标归一', () {
    testWidgets('渲染统一 IntersectionTypeIcon（语义来自 iconKey/sourceRef/dimension）', (
      tester,
    ) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(source: 'sharedFollowees'),
      ], isDark: false);

      await tester.pumpWidget(_wrap(widget!));

      expect(find.byType(IntersectionTypeIcon), findsOneWidget);
      expect(find.byKey(IntersectionReasonChip.iconKey), findsOneWidget);
    });
  });

  group('IntersectionReasonChip.weightTier 轻重分化', () {
    Future<TextStyle?> baseStyleOf(WidgetTester tester) async {
      final richText = tester.widget<InteractiveIntersectionText>(
        find.byKey(IntersectionReasonChip.textKey),
      );
      return richText.baseStyle;
    }

    testWidgets('heavy 展示完整蓝色理由行', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(weightTier: 'heavy'),
      ], isDark: false);

      await tester.pumpWidget(_wrap(widget!));

      final style = await baseStyleOf(tester);
      expect(
        style?.color,
        AppColors.iosAccent(tester.element(find.text(_validPrimaryText))),
      );
      expect(style?.fontWeight, AppTypography.medium);
    });

    testWidgets('空 weightTier 按 heavy 兜底', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(),
      ], isDark: false);

      await tester.pumpWidget(_wrap(widget!));

      final style = await baseStyleOf(tester);
      expect(
        style?.color,
        AppColors.iosAccent(tester.element(find.text(_validPrimaryText))),
      );
      expect(style?.fontWeight, AppTypography.medium);
    });

    testWidgets('未知 weightTier 按 heavy 兜底', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(weightTier: 'future-tier'),
      ], isDark: false);

      await tester.pumpWidget(_wrap(widget!));

      final style = await baseStyleOf(tester);
      expect(
        style?.color,
        AppColors.iosAccent(tester.element(find.text(_validPrimaryText))),
      );
      expect(style?.fontWeight, AppTypography.medium);
    });

    testWidgets('light 展示灰色弱化形态', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(weightTier: 'light'),
      ], isDark: false);

      await tester.pumpWidget(_wrap(widget!));

      final style = await baseStyleOf(tester);
      expect(
        style?.color,
        AppColors.iosSecondaryLabel(
          tester.element(find.text(_validPrimaryText)),
        ),
      );
      expect(style?.fontWeight, AppTypography.regular);
    });
  });

  // ── N5：spans 非空时对象片段可点击 → 统一导航 + tag_click 归因（非降级 click）──
  group('IntersectionReasonChip 可点击片段', () {
    testWidgets('点击对象 span → 经统一导航跳转 + trackTagClick 全归因回流', (tester) async {
      final repo = RecordingContentBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        reporter: repo,
        maxBatchSize: 1,
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);
      final widget = IntersectionReasonChip.fromReasons(
        <IntersectionReason>[
          _reason(intersectionId: 'ix_chip', intersectionClass: 'fact'),
        ],
        isDark: false,
        referralSource: ReferralSource.authorProfile,
      );

      await tester.pumpWidget(_routedChip(widget!, tracker: tracker));
      await tester.pumpAndSettle();

      // 富文本子 span 不被 find.text 命中，定位 span recognizer 直接触发（点对象名）。
      final richText = tester.widget<RichText>(
        find.descendant(
          of: find.byType(InteractiveIntersectionText),
          matching: find.byType(RichText),
        ),
      );
      final nameSpan = _spanByText(richText, '林清越');
      (nameSpan.recognizer! as TapGestureRecognizer).onTap!();
      await tester.pumpAndSettle();
      await tracker.flush();

      // 导航命中目标路由（对象片段进对象页，旅程无断点）。
      expect(find.text('user-profile-route'), findsOneWidget);

      // 埋点保 tag_click 语义（未降级 click，保推荐 1.8 权重）+ 完整交集归因。
      final tagClicks = repo.recorded
          .where((e) => e.action == BehaviorEventType.tagClick)
          .toList(growable: false);
      expect(tagClicks, hasLength(1));
      final event = tagClicks.single;
      expect(event.contentId, 'u_lin');
      expect(event.referralSource, ReferralSource.authorProfile);
      expect(event.intersectionId, 'ix_chip');
      expect(event.intersectionDimension, 'content');
      expect(event.intersectionSourceRef, 'coCommented');
      expect(event.intersectionClass, 'fact');
    });
  });

  testWidgets('双主题均渲染只读文案', (tester) async {
    for (final isDark in const <bool>[false, true]) {
      await tester.pumpWidget(
        _wrap(
          IntersectionReasonChip(
            text: _validPrimaryText,
            isDark: isDark,
            reason: _reason(),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(find.text(_validPrimaryText), findsOneWidget);
    }
  });

  test('IntersectionIconResolver 闭集仍解析 sharedFollowees → people 图标（归一证据）', () {
    expect(
      IntersectionIconResolver.resolve(sourceRef: 'sharedFollowees'),
      CupertinoIcons.person_2_fill,
    );
  });
}
