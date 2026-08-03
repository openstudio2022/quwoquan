import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/circle_contracts.dart'
    as circle_wire;
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_statement_card.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_impact_provider.dart';
import 'package:quwoquan_app/ui/entity/providers/entity_impact_provider.dart';

/// 对象页「打动」预览卡目标（实体 homepage / 圈子 circle）。
enum ObjectImpactTarget { homepage, circle }

/// 「打动」预览卡（实体 / 圈子主页共享）。
///
/// 与 [ObjectIntersectionSection] 同壳：最多 3 条、只读云侧 [primaryText]、
/// 数字片段可点开来源说明；无真实打动事实时整卡收起（G2）。
class ObjectImpactPreviewCard extends ConsumerWidget {
  const ObjectImpactPreviewCard({
    super.key,
    required this.objectId,
    required this.target,
    required this.referralSource,
    required this.title,
    this.enumerableHint = ObjectHomepageText.impactEnumerableHintEntity,
    this.maxItems = 3,
    this.topDivider = true,
    this.cardKey,
  });

  final String objectId;
  final ObjectImpactTarget target;
  final ReferralSource referralSource;
  final String title;
  final String enumerableHint;
  final int maxItems;
  final bool topDivider;
  final Key? cardKey;

  IntersectionTargetNavigator _navigator(WidgetRef ref) =>
      IntersectionTargetNavigator(
        onTrack: (targetHit, attribution) {
          final id = targetHit.objectId.trim();
          if (id.isEmpty) {
            return;
          }
          ref
              .read(contentBehaviorTrackerProvider)
              .trackClick(
                id,
                referralSource: referralSource,
                intersectionDimension: attribution.dimension,
                intersectionSourceRef: attribution.sourceRef,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  Future<void> _showEvidence(BuildContext context, _ObjectImpactLine item) {
    final source = item.source.trim().isEmpty ? title : item.source.trim();
    final message = item.count > 0
        ? '$enumerableHint\n$source · ${item.count}'
        : '$enumerableHint\n$source';
    return showAppActionSheet<void>(
      context,
      title: item.primaryText.trim(),
      message: message,
      sections: const <AppActionSheetSection<void>>[],
      cancelLabel: FoundationText.confirm,
    );
  }

  void _onSpanTap(
    BuildContext context,
    WidgetRef ref,
    _ObjectImpactLine item,
    IntersectionTextSpan span,
  ) {
    if (span.role == 'count') {
      unawaited(_showEvidence(context, item));
      return;
    }
    _navigator(ref).open(
      context,
      span.target,
      attribution: IntersectionNavAttribution(
        dimension: item.intersectionDimension,
        sourceRef: item.source,
        evidenceId: item.evidenceSnapshotId,
        tagRefs: item.tagRef.trim().isEmpty
            ? const <String>[]
            : <String>[item.tagRef.trim()],
      ),
    );
  }

  List<_ObjectImpactLine> _linesFromEntity(EntityImpactSummary summary) {
    return summary.items
        .where((item) => item.primaryText.trim().isNotEmpty)
        .take(maxItems)
        .map(_ObjectImpactLine.fromEntity)
        .toList(growable: false);
  }

  List<_ObjectImpactLine> _linesFromCircle(CircleImpactSummary summary) {
    return summary.items
        .where((item) => item.primaryText.trim().isNotEmpty)
        .take(maxItems)
        .map(_ObjectImpactLine.fromCircle)
        .toList(growable: false);
  }

  Widget _buildCard(
    BuildContext context,
    WidgetRef ref,
    List<_ObjectImpactLine> lines,
  ) {
    if (lines.isEmpty) {
      return const SizedBox.shrink();
    }
    final navigator = _navigator(ref);
    return IntersectionStatementCard(
      key: cardKey,
      topDivider: topDivider,
      title: title,
      footerActionLabel: DiscoveryFeedText.intersectionViewAll,
      onFooterAction: () => unawaited(_showEvidence(context, lines.first)),
      items: <IntersectionStatementItem>[
        for (final item in lines)
          IntersectionStatementItem(
            primaryText: item.primaryText.trim(),
            subtitleText: item.subtitleText.trim(),
            spans: item.primarySpans,
            visuals: item.sampleVisuals,
            iconKey: item.iconKey,
            sourceRef: item.source,
            dimension: item.intersectionDimension,
            actionHints: item.actionHints,
            propagationPath: item.propagationPath,
            showAuxiliaryLine: false,
            onSpanTap: (span) => _onSpanTap(context, ref, item, span),
            onVisualTap: (visual) => navigator.open(
              context,
              visual.target,
              attribution: IntersectionNavAttribution(
                dimension: item.intersectionDimension,
                sourceRef: item.source,
                evidenceId: item.evidenceSnapshotId,
                tagRefs: item.tagRef.trim().isEmpty
                    ? const <String>[]
                    : <String>[item.tagRef.trim()],
              ),
            ),
            onPropagationTap: () => unawaited(_showEvidence(context, item)),
            onTap: () => unawaited(_showEvidence(context, item)),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final trimmedId = objectId.trim();
    if (trimmedId.isEmpty) {
      return const SizedBox.shrink();
    }

    return switch (target) {
      ObjectImpactTarget.homepage =>
        ref
            .watch(entityImpactProvider(trimmedId))
            .when(
              loading: () => const SizedBox.shrink(),
              error: (_, _) => const SizedBox.shrink(),
              data: (summary) =>
                  _buildCard(context, ref, _linesFromEntity(summary)),
            ),
      ObjectImpactTarget.circle =>
        ref
            .watch(circleImpactProvider(trimmedId))
            .when(
              loading: () => const SizedBox.shrink(),
              error: (_, _) => const SizedBox.shrink(),
              data: (summary) =>
                  _buildCard(context, ref, _linesFromCircle(summary)),
            ),
    };
  }
}

class _ObjectImpactLine {
  const _ObjectImpactLine({
    required this.primaryText,
    required this.subtitleText,
    required this.primarySpans,
    required this.sampleVisuals,
    required this.iconKey,
    required this.source,
    required this.intersectionDimension,
    required this.tagRef,
    required this.evidenceSnapshotId,
    required this.count,
    required this.actionHints,
    required this.propagationPath,
  });

  final String primaryText;
  final String subtitleText;
  final List<IntersectionTextSpan> primarySpans;
  final List<IntersectionVisual> sampleVisuals;
  final String iconKey;
  final String source;
  final String intersectionDimension;
  final String tagRef;
  final String evidenceSnapshotId;
  final int count;
  final List<IntersectionActionHint> actionHints;
  final IntersectionPropagationPath? propagationPath;

  factory _ObjectImpactLine.fromEntity(EntityImpactItem item) {
    return _ObjectImpactLine(
      primaryText: item.primaryText,
      subtitleText: item.subtitleText,
      primarySpans: item.primarySpans,
      sampleVisuals: item.sampleVisuals,
      iconKey: item.iconKey,
      source: item.source,
      intersectionDimension: item.intersectionDimension,
      tagRef: item.tagRef,
      evidenceSnapshotId: item.evidenceSnapshotId,
      count: item.count,
      actionHints: item.actionHints,
      propagationPath: item.propagationPath,
    );
  }

  factory _ObjectImpactLine.fromCircle(circle_wire.CircleImpactItem item) {
    return _ObjectImpactLine(
      primaryText: item.primaryText,
      subtitleText: item.subtitleText,
      primarySpans: item.primarySpans,
      sampleVisuals: item.sampleVisuals,
      iconKey: item.iconKey,
      source: item.source,
      intersectionDimension: item.intersectionDimension,
      tagRef: item.tagRef,
      evidenceSnapshotId: item.evidenceSnapshotId,
      count: item.count,
      actionHints: item.actionHints,
      propagationPath: item.propagationPath,
    );
  }
}
