// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003.t2
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001.t3
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_reason_selection.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_evidence_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// 证据半屏只按序渲染云侧 `evidenceRows`（IntersectionEvidenceRow 闭集）：
/// 顺序、去重与上限都在 Content 水合出口决定，端不再合并 secondaryText /
/// connectionSummary / actorEvidence / intersectionPoints，也不持本地上限。
void main() {
  Future<void> pumpSheet(
    WidgetTester tester,
    IntersectionReason reason, {
    IntersectionActionHint? primaryHint,
  }) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: IntersectionEvidenceSheet(
          resolution: IntersectionDisplayResolution(
            reason: reason,
            primaryHint: primaryHint,
          ),
          onDismiss: () {},
          panelKey: const ValueKey<String>('evidence-sheet'),
          onPrimaryAction: primaryHint == null ? null : () {},
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('证据行按云侧下发顺序渲染，本地异构字段不再被拼进证据列表', (tester) async {
    final reason = intersectionReasonFixture(
      kind: 'sharedFollowees',
      dimension: 'relationship',
      intersectionId: 'ix_rows',
      primaryText: '联系人林清越等2人也关注了陆衡',
      // 这些字段以前被端侧按本地优先级合并成证据行；现在只有 evidenceRows 才是证据行。
      secondaryText: '本地不应出现的副句',
      connectionSummary: '本地不应出现的连接说明',
      intersectionPoints: <IntersectionPoint>[
        intersectionPointFixture(
          pointId: 'p1',
          pointClass: 'fact',
          dimension: 'relationship',
          label: '共同关注',
          displayText: '本地不应出现的点位文本',
          sampleText: '本地不应出现的样本',
          sourceRef: 'sharedFollowees',
          visibility: 'public',
          count: 3,
        ),
      ],
      evidenceRows: const <IntersectionEvidenceRow>[
        IntersectionEvidenceRow(text: '第二行在前', source: 'connection_summary'),
        IntersectionEvidenceRow(text: '第一行在后', source: 'secondary_text'),
      ],
    );
    await pumpSheet(tester, reason);

    expect(
      find.text(DiscoveryFeedText.intersectionDetailTitle),
      findsOneWidget,
    );
    expect(find.text('联系人林清越等2人也关注了陆衡'), findsOneWidget);
    final first = tester.getRect(
      find.byKey(const ValueKey<String>('intersection-evidence-item-0')),
    );
    final second = tester.getRect(
      find.byKey(const ValueKey<String>('intersection-evidence-item-1')),
    );
    expect(first.top, lessThan(second.top));
    expect(find.text('第二行在前'), findsOneWidget);
    expect(find.text('第一行在后'), findsOneWidget);
    expect(find.textContaining('本地不应出现'), findsNothing);
  });

  testWidgets('行数完全由云侧决定：端不再硬截 4 行，也不在 0 行时补证据', (tester) async {
    final rows = List<IntersectionEvidenceRow>.generate(
      6,
      (i) => IntersectionEvidenceRow(text: '云侧证据 $i', source: 'actor_action'),
    );
    final many = intersectionReasonFixture(
      kind: 'sharedFollowees',
      dimension: 'relationship',
      intersectionId: 'ix_many',
      primaryText: '联系人林清越等2人也关注了陆衡',
      evidenceRows: rows,
    );
    await pumpSheet(tester, many);
    for (var i = 0; i < rows.length; i += 1) {
      expect(
        find.byKey(ValueKey<String>('intersection-evidence-item-$i')),
        findsOneWidget,
      );
    }

    final none = intersectionReasonFixture(
      kind: 'sharedFollowees',
      dimension: 'relationship',
      intersectionId: 'ix_none',
      primaryText: '联系人林清越等2人也关注了陆衡',
      secondaryText: '本地不应出现的副句',
    );
    final hint = intersectionActionHintFixture(
      actionKey: 'message_person',
      label: '发消息',
      isPrimary: true,
    );
    await pumpSheet(tester, none, primaryHint: hint);
    expect(
      find.byKey(const ValueKey<String>('intersection-evidence-item-0')),
      findsNothing,
    );
    expect(find.textContaining('本地不应出现'), findsNothing);
    // 半屏仍只显示 resolver 选出的唯一 typed 下一步。
    expect(find.text('发消息'), findsOneWidget);
  });
}
