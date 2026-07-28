import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// T2：对象页统一交集卡口径（V5 · primaryText 单通道 / 全局验收 G2）。
/// - 无 primaryText → 不展示；
/// - 主句唯一来源为 IntersectionReason.primaryText；
/// - primarySpans 只作为同一句话的可交互投影；
/// - affinity 只能显示推荐辅助，不伪装事实；
/// - 折叠、旅程高亮与全部入口按 reason 维度工作。
IntersectionReason _reason({
  required String id,
  required String primaryText,
  String source = '',
  String dimension = 'relationship',
  String intersectionClass = 'fact',
  String confidenceLabel = '',
  String connectionSummary = '',
  List<IntersectionTextSpan>? primarySpans,
  List<IntersectionVisual> sampleVisuals = const <IntersectionVisual>[],
  List<IntersectionPoint> intersectionPoints = const <IntersectionPoint>[],
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
}) {
  final actorTarget = IntersectionTarget(
    objectType: 'user',
    objectId: 'u_lin',
    objectKind: 'person',
    routeId: 'userProfile',
  );
  final objectTarget = IntersectionTarget(
    objectType: 'post',
    objectId: 'post_$id',
    objectKind: 'content',
    routeId: 'workBrowser',
  );
  return IntersectionReason(
    intersectionId: id,
    source: source,
    dimension: dimension,
    primaryText: primaryText,
    intersectionClass: intersectionClass,
    confidenceLabel: confidenceLabel,
    connectionSummary: connectionSummary,
    primarySpans:
        primarySpans ??
        <IntersectionTextSpan>[
          IntersectionTextSpan(
            text: primaryText.trim(),
            role: 'object',
            target: objectTarget,
          ),
        ],
    sampleVisuals: sampleVisuals,
    intersectionPoints: intersectionPoints,
    actionHints: actionHints,
    actionTargetId: 'post_$id',
    objectKind: 'content',
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'u_lin',
      displayName: '林清越',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: actorTarget,
    ),
  );
}

void main() {
  group('ObjectIntersectionCard.fromReasons（G2 primaryText 口径）', () {
    test('reasons 为 null → 返回 null（不展示）', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: ObjectHomepageText.objectMyIntersectionsTitle,
          reasons: null,
          isDark: false,
        ),
        isNull,
      );
    });

    test('reasons 为空或无 primaryText → 返回 null', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: ObjectHomepageText.objectMyIntersectionsTitle,
          reasons: const <IntersectionReason>[],
          isDark: false,
        ),
        isNull,
      );
      expect(
        ObjectIntersectionCard.fromReasons(
          title: ObjectHomepageText.objectMyIntersectionsTitle,
          reasons: <IntersectionReason>[
            _reason(id: 'blank', primaryText: '   '),
          ],
          isDark: false,
        ),
        isNull,
      );
    });

    testWidgets('主句只读 primaryText，不从 intersectionPoints 拼 label/count/sample', (
      tester,
    ) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        reasons: <IntersectionReason>[
          _reason(
            id: 'ix_primary',
            primaryText: '4 位共同关注的人正在这里讨论',
            connectionSummary: '最近有你关注的人参与讨论',
            intersectionPoints: <IntersectionPoint>[
              IntersectionPoint(
                pointId: 'archive_point',
                label: '共同关注',
                displayText: '共同关注',
                count: 4,
                sampleText: '林清越',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(
        find.text(ObjectHomepageText.objectMyIntersectionsTitle),
        findsOneWidget,
      );
      expect(find.text('4 位共同关注的人正在这里讨论'), findsOneWidget);
      expect(find.text('最近有你关注的人参与讨论'), findsOneWidget);
      expect(find.text('共同关注 4'), findsNothing);
      expect(find.text('林清越'), findsNothing);
    });

    testWidgets('primarySpans 与 primaryText 同句展示，点击行回传原 reason 归因对象', (
      tester,
    ) async {
      IntersectionReason? tapped;
      final reason = _reason(
        id: 'ix_spans',
        primaryText: '联系人林清越等3人赞过《川西雪山和校园摄影路线》',
        primarySpans: <IntersectionTextSpan>[
          IntersectionTextSpan(text: '联系人', role: 'plain'),
          IntersectionTextSpan(
            text: '林清越',
            role: 'object',
            target: IntersectionTarget(
              objectType: 'user',
              objectId: 'u_lin',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
          IntersectionTextSpan(text: '等', role: 'plain'),
          IntersectionTextSpan(
            text: '3',
            role: 'count',
            target: IntersectionTarget(
              objectType: 'dimension',
              objectId: 'content',
              objectKind: 'dimension',
              routeId: 'myIntersections',
            ),
          ),
          IntersectionTextSpan(text: '人赞过', role: 'plain'),
          IntersectionTextSpan(
            text: '《川西雪山和校园摄影路线》',
            role: 'object',
            target: IntersectionTarget(
              objectType: 'post',
              objectId: 'post_ix_spans',
              objectKind: 'content',
              routeId: 'workBrowser',
            ),
          ),
        ],
      );
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        reasons: <IntersectionReason>[reason],
        isDark: false,
        onReasonTap: (r) => tapped = r,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.textContaining('林清越'), findsOneWidget);
      await tester.tap(find.textContaining('林清越'));
      await tester.pump();

      expect(tapped, same(reason));
    });

    testWidgets('sampleVisuals 统一头像簇在深浅色紧凑宽度均无溢出', (tester) async {
      for (final brightness in <Brightness>[
        Brightness.light,
        Brightness.dark,
      ]) {
        final card = ObjectIntersectionCard.fromReasons(
          title: ObjectHomepageText.objectMyIntersectionsTitle,
          reasons: <IntersectionReason>[
            _reason(
              id: 'ix_visuals_${brightness.name}',
              primaryText: '共同关注的人正在讨论这条路线',
              sampleVisuals: <IntersectionVisual>[
                IntersectionVisual(assetKind: 'avatar', displayName: '林清越'),
                IntersectionVisual(assetKind: 'avatar', displayName: '周屿'),
                IntersectionVisual(
                  assetKind: 'circleAvatar',
                  displayName: '校园摄影圈',
                ),
                IntersectionVisual(assetKind: 'avatar', displayName: '顾川'),
              ],
            ),
          ],
          isDark: brightness == Brightness.dark,
        );

        await tester.pumpWidget(
          CupertinoApp(
            theme: CupertinoThemeData(brightness: brightness),
            home: MediaQuery(
              data: const MediaQueryData(size: Size(320, 568)),
              child: SizedBox(width: 320, child: card),
            ),
          ),
        );
        await tester.pump();

        expect(find.byType(IntersectionVisualCluster), findsOneWidget);
        expect(find.text('+1'), findsOneWidget);
        expect(find.textContaining('共同关注的人'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('affinity 只显示推荐辅助文案，不伪装成事实计数', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        reasons: <IntersectionReason>[
          _reason(
            id: 'ix_affinity',
            primaryText: '这个圈子的讨论与你最近关注的主题相关',
            dimension: 'interest',
            intersectionClass: 'affinity',
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('这个圈子的讨论与你最近关注的主题相关'), findsOneWidget);
      expect(
        find.text(DiscoveryFeedText.intersectionAffinityLabel),
        findsOneWidget,
      );
      expect(find.textContaining('共同关注'), findsNothing);
    });

    testWidgets('就地展开：默认 inlineExpandCount 条 reason，点击展开余下理由', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        inlineExpandCount: 2,
        reasons: <IntersectionReason>[
          _reason(id: 'r1', primaryText: '第一条交集事实'),
          _reason(id: 'r2', primaryText: '第二条交集事实'),
          _reason(id: 'r3', primaryText: '第三条交集事实'),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      expect(find.text('第一条交集事实'), findsOneWidget);
      expect(find.text('第二条交集事实'), findsOneWidget);
      expect(find.text('第三条交集事实'), findsNothing);

      await tester.tap(find.text(DiscoveryFeedText.intersectionExpandMore));
      await tester.pumpAndSettle();
      expect(find.text('第三条交集事实'), findsOneWidget);
    });

    testWidgets('旅程高亮：highlightKind 命中折叠区 reason 时自动展开', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        inlineExpandCount: 1,
        highlightKind: 'coCommented',
        reasons: <IntersectionReason>[
          _reason(id: 'r1', primaryText: '第一条交集事实', source: 'sharedFollowees'),
          _reason(id: 'r2', primaryText: '共同讨论正在升温', source: 'coCommented'),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      await tester.pumpAndSettle();
      expect(find.text('共同讨论正在升温'), findsOneWidget);
    });

    testWidgets('展开更多两段式：先展开，再进入全部连接', (tester) async {
      var openedAll = false;
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        inlineExpandCount: 1,
        moreLabel: '全部连接',
        onMoreTap: () => openedAll = true,
        reasons: <IntersectionReason>[
          _reason(id: 'r1', primaryText: '第一条交集事实'),
          _reason(id: 'r2', primaryText: '第二条交集事实'),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      await tester.pumpAndSettle();

      expect(find.text('第一条交集事实'), findsOneWidget);
      expect(find.text('第二条交集事实'), findsNothing);
      expect(
        find.text(DiscoveryFeedText.intersectionExpandMore),
        findsOneWidget,
      );

      await tester.tap(find.text(DiscoveryFeedText.intersectionExpandMore));
      await tester.pumpAndSettle();

      expect(find.text('第二条交集事实'), findsOneWidget);
      expect(find.text('全部连接'), findsOneWidget);
      expect(openedAll, isFalse);

      await tester.tap(find.text('全部连接'));
      await tester.pump();

      expect(openedAll, isTrue);
    });

    testWidgets('可执行 navigate actionHint 展示 pill 并回调', (tester) async {
      IntersectionActionHint? tapped;
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        reasons: <IntersectionReason>[
          _reason(
            id: 'ix_action',
            primaryText: '联系人林清越赞过《川西雪山和校园摄影路线》',
            actionHints: <IntersectionActionHint>[
              IntersectionActionHint(
                actionKey: 'open_object',
                label: '查看对象',
                dispatch: 'navigate',
                targetAvailability: 'available',
                target: IntersectionTarget(
                  objectType: 'homepage',
                  objectId: 'entity_1',
                  objectKind: 'place',
                  routeId: 'homepageDetail',
                ),
                isPrimary: true,
              ),
            ],
          ),
        ],
        isDark: false,
        onActionHintTap: (_, hint) => tapped = hint,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('查看对象'), findsOneWidget);
      await tester.tap(find.text('查看对象'));
      await tester.pump();

      expect(tapped?.actionKey, 'open_object');
    });

    testWidgets(
      'navigate+login 门行动显示为可执行入口（门交承接页）；deferred/connect 无真实 handler 不显示',
      (tester) async {
        final card = ObjectIntersectionCard.fromReasons(
          title: ObjectHomepageText.objectMyIntersectionsTitle,
          reasons: <IntersectionReason>[
            _reason(
              id: 'ix_dead_actions',
              primaryText: '联系人林清越赞过《川西雪山和校园摄影路线》',
              connectionSummary: '有可查看的共同证据',
              actionHints: <IntersectionActionHint>[
                IntersectionActionHint(
                  actionKey: 'follow_person',
                  label: '关注TA',
                  dispatch: 'navigate',
                  requiredGates: const <String>['login'],
                  targetAvailability: 'available',
                  target: IntersectionTarget(
                    objectType: 'user',
                    objectId: 'u1',
                    objectKind: 'person',
                    routeId: 'userProfile',
                  ),
                  isPrimary: true,
                ),
                IntersectionActionHint(
                  actionKey: 'join_trip',
                  label: '加入同行',
                  dispatch: 'companion',
                  targetAvailability: 'deferred',
                  target: IntersectionTarget(
                    objectId: 'trip_1',
                    objectKind: 'trip',
                  ),
                ),
                IntersectionActionHint(
                  actionKey: 'start_voice_room',
                  label: '进语音房',
                  dispatch: 'connect',
                  targetAvailability: 'available',
                ),
              ],
            ),
          ],
          isDark: false,
        );

        await tester.pumpWidget(CupertinoApp(home: card!));

        // 关注带 login 门但 dispatch=navigate：登录门交承接页 + AuthContinuation 续接
        // （§15），交集卡必须保留关注入口（不因 login 门隐藏，否则登录用户也看不到入口）；
        // 行动优先取代安静副句（auxiliaryLine：行动 pill > 副句）。
        expect(find.text('关注TA'), findsOneWidget);
        // deferred（能力尚未上线）/ connect（无真实卡内 handler）保持诚实不渲染成死 pill。
        expect(find.text('加入同行'), findsNothing);
        expect(find.text('进语音房'), findsNothing);
      },
    );

    testWidgets('无任何可执行行动（仅 deferred/connect）→ 回落安静共同证据副句', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: ObjectHomepageText.objectMyIntersectionsTitle,
        reasons: <IntersectionReason>[
          _reason(
            id: 'ix_summary_fallback',
            primaryText: '联系人林清越赞过《川西雪山和校园摄影路线》',
            connectionSummary: '有可查看的共同证据',
            actionHints: <IntersectionActionHint>[
              IntersectionActionHint(
                actionKey: 'join_trip',
                label: '加入同行',
                dispatch: 'companion',
                targetAvailability: 'deferred',
                target: IntersectionTarget(
                  objectId: 'trip_1',
                  objectKind: 'trip',
                ),
              ),
              IntersectionActionHint(
                actionKey: 'start_voice_room',
                label: '进语音房',
                dispatch: 'connect',
                targetAvailability: 'available',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('加入同行'), findsNothing);
      expect(find.text('进语音房'), findsNothing);
      // 无可执行行动 → auxiliaryLine 回落安静共同证据副句（不留空、不造死 pill）。
      expect(find.text('有可查看的共同证据'), findsOneWidget);
    });
  });
}
