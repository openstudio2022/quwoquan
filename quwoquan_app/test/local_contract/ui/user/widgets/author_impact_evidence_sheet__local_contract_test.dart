/// R-ID03 端侧 UI 契约：AuthorImpactEvidenceSheet 渲染云侧完整分页明细。
///
/// sheet 为纯展示组件 + 注入 fetchEvidence 闭包（DI），可脱离 Provider/Repository
/// 直接以受控分页数据驱动断言：真实来源行渲染、触底加载更多、整行进被影响内容、
/// 空页/失败的不造假降级（回退样本或空态/重试）。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_evidence.dart';
import '../../../../support/fixtures/author_impact_fixtures.dart';

AuthorImpactItem _item({List<IntersectionVisual> samples = const []}) {
  return authorImpactItemFixture(
    impactId: 'imp_1',
    helpType: 'decision',
    action: 'share',
    intersectionDimension: 'content',
    tagRef: 'content/city-cycling-guide',
    source: 'source:repost',
    count: 3,
    primaryText: '3人转发了你的内容',
    subtitleText: '来自城市夜骑指南的转发',
    sampleVisuals: samples,
  );
}

AuthorImpactEvidenceItem _row(
  String id,
  String summary, {
  IntersectionTarget? target,
}) {
  return authorImpactEvidenceItemFixture(
    evidenceId: id,
    impactId: 'imp_1',
    helpType: 'decision',
    action: 'share',
    intersectionDimension: 'content',
    summaryText: summary,
    contentTarget: target,
  );
}

Widget _host(AuthorImpactEvidenceSheet sheet) {
  return CupertinoApp(home: CupertinoPageScaffold(child: sheet));
}

void main() {
  group('AuthorImpactEvidenceSheet', () {
    testWidgets('渲染真实来源行 + 触底加载更多翻页', (tester) async {
      Future<AuthorImpactEvidencePage> fetch({String cursor = ''}) async {
        if (cursor.isEmpty) {
          return authorImpactEvidencePageFixture(
            impactId: 'imp_1',
            totalCount: 3,
            items: <AuthorImpactEvidenceItem>[
              _row('e0', '有人收藏了《城市夜骑指南》'),
              _row('e1', '有人转发了《城市夜骑指南》'),
            ],
            nextCursor: '2',
            hasMore: true,
          );
        }
        return authorImpactEvidencePageFixture(
          impactId: 'imp_1',
          totalCount: 3,
          items: <AuthorImpactEvidenceItem>[_row('e2', '有人进了相关圈子')],
          nextCursor: '',
          hasMore: false,
        );
      }

      await tester.pumpWidget(
        _host(
          AuthorImpactEvidenceSheet(
            item: _item(),
            isMine: true,
            fetchEvidence: fetch,
            onVisualTap: (_) {},
            onContentTap: (_) {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetDetailLabel),
        findsOneWidget,
      );
      expect(find.text('有人收藏了《城市夜骑指南》'), findsOneWidget);
      expect(find.text('有人转发了《城市夜骑指南》'), findsOneWidget);
      expect(find.text('有人进了相关圈子'), findsNothing);
      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetLoadMore),
        findsOneWidget,
      );

      await tester.tap(
        find.text(DiscoveryFeedText.impactEvidenceSheetLoadMore),
      );
      await tester.pumpAndSettle();

      expect(find.text('有人进了相关圈子'), findsOneWidget);
      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetLoadMore),
        findsNothing,
      );
    });

    testWidgets('整行点击 → 进入被影响内容（onContentTap）', (tester) async {
      IntersectionTarget? tapped;
      Future<AuthorImpactEvidencePage> fetch({String cursor = ''}) async {
        return authorImpactEvidencePageFixture(
          impactId: 'imp_1',
          totalCount: 1,
          items: <AuthorImpactEvidenceItem>[
            _row(
              'e0',
              '有人收藏了《城市夜骑指南》',
              target: IntersectionTarget(
                objectId: 'post_9',
                objectKind: 'place',
                routeId: 'homepageDetail',
              ),
            ),
          ],
          hasMore: false,
        );
      }

      await tester.pumpWidget(
        _host(
          AuthorImpactEvidenceSheet(
            item: _item(),
            isMine: true,
            fetchEvidence: fetch,
            onVisualTap: (_) {},
            onContentTap: (t) => tapped = t,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('有人收藏了《城市夜骑指南》'));
      await tester.pumpAndSettle();

      expect(tapped, isNotNull);
      expect(tapped!.objectId, 'post_9');
    });

    testWidgets('空页 + 无样本 → 空态文案（不造假）', (tester) async {
      Future<AuthorImpactEvidencePage> fetch({String cursor = ''}) async {
        return authorImpactEvidencePageFixture(impactId: 'imp_1');
      }

      await tester.pumpWidget(
        _host(
          AuthorImpactEvidenceSheet(
            item: _item(),
            isMine: false,
            fetchEvidence: fetch,
            onVisualTap: (_) {},
            onContentTap: (_) {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetEmptyNote),
        findsOneWidget,
      );
      expect(find.byType(IntersectionVisualCluster), findsNothing);
    });

    testWidgets('加载失败 + 无样本 → 失败提示 + 重试', (tester) async {
      var attempts = 0;
      Future<AuthorImpactEvidencePage> fetch({String cursor = ''}) async {
        attempts++;
        throw Exception('boom');
      }

      await tester.pumpWidget(
        _host(
          AuthorImpactEvidenceSheet(
            item: _item(),
            isMine: false,
            fetchEvidence: fetch,
            onVisualTap: (_) {},
            onContentTap: (_) {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetLoadFailed),
        findsOneWidget,
      );
      expect(attempts, 1);

      await tester.tap(find.text('重试'));
      await tester.pumpAndSettle();
      expect(attempts, 2);
    });

    testWidgets('空页 + 有样本 → 回退样本簇（真实样本，不编造完整名单）', (tester) async {
      Future<AuthorImpactEvidencePage> fetch({String cursor = ''}) async {
        return authorImpactEvidencePageFixture(impactId: 'imp_1');
      }

      await tester.pumpWidget(
        _host(
          AuthorImpactEvidenceSheet(
            item: _item(
              samples: <IntersectionVisual>[
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
            isMine: true,
            fetchEvidence: fetch,
            onVisualTap: (_) {},
            onContentTap: (_) {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(IntersectionVisualCluster), findsOneWidget);
      expect(
        find.text(DiscoveryFeedText.impactEvidenceSheetFullPendingNote),
        findsOneWidget,
      );
    });
  });
}
