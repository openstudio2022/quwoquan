import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/circle_contracts.dart'
    as circle_wire;
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_statement_card.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';

/// 「打动」预览卡（实体 / 圈子主页共享）。
///
/// 与 [ObjectIntersectionSection] 同壳：最多 3 条、只读云侧 [primaryText]、
/// 数字片段可点开来源说明；无真实打动事实时整卡收起（G2）。
class ObjectImpactPreviewCard extends StatelessWidget {
  const ObjectImpactPreviewCard.entity({
    super.key,
    required EntityImpactSummary summary,
    required this.contentBehaviorTracker,
    required this.referralSource,
    required this.title,
    this.enumerableHint = ObjectHomepageText.impactEnumerableHintEntity,
    this.maxItems = 3,
    this.topDivider = true,
    this.cardKey,
  }) : _entitySummary = summary,
       _circleSummary = null;

  const ObjectImpactPreviewCard.circle({
    super.key,
    required circle_wire.CircleImpactSummary summary,
    required this.contentBehaviorTracker,
    required this.referralSource,
    required this.title,
    this.enumerableHint = ObjectHomepageText.impactEnumerableHintCircle,
    this.maxItems = 3,
    this.topDivider = true,
    this.cardKey,
  }) : _entitySummary = null,
       _circleSummary = summary;

  final EntityImpactSummary? _entitySummary;
  final circle_wire.CircleImpactSummary? _circleSummary;
  final ContentBehaviorTrackerPort contentBehaviorTracker;
  final ReferralSource referralSource;
  final String title;
  final String enumerableHint;
  final int maxItems;
  final bool topDivider;
  final Key? cardKey;

  IntersectionTargetNavigator _navigator() => IntersectionTargetNavigator(
    onTrack: (targetHit, attribution) {
      final id = targetHit.objectId.trim();
      if (id.isEmpty) {
        return;
      }
      contentBehaviorTracker.trackClick(
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
    _ObjectImpactLine item,
    IntersectionTextSpan span,
  ) {
    if (span.role == 'count') {
      unawaited(_showEvidence(context, item));
      return;
    }
    _navigator().open(
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

  Widget _buildCard(BuildContext context, List<_ObjectImpactLine> lines) {
    if (lines.isEmpty) {
      return const SizedBox.shrink();
    }
    final navigator = _navigator();
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
            onSpanTap: (span) => _onSpanTap(context, item, span),
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
  Widget build(BuildContext context) {
    final entitySummary = _entitySummary;
    if (entitySummary != null) {
      return _buildCard(context, _linesFromEntity(entitySummary));
    }
    final circleSummary = _circleSummary;
    if (circleSummary != null) {
      return _buildCard(context, _linesFromCircle(circleSummary));
    }
    return const SizedBox.shrink();
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
