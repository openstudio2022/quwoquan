import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/widgets/intersection_statement_card.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// 影响力摘要模块（他人主页 / 我的主页双视角，可解释）。
///
/// 统一交互子契约落地（Phase 0 §20.7）：逐条只读 [AuthorImpactSummary]：
/// - 结论句走 [AuthorImpactItem.primarySpans] + 统一渲染器（[IntersectionStatementRow]），
///   端不本地拼装文案（G2），spans 缺省回落 [AuthorImpactItem.primaryText]；
/// - 样本视觉走 [AuthorImpactItem.sampleVisuals] + [IntersectionVisualCluster]；
/// - 名字 / 对象片段经 [IntersectionTargetNavigator] 进对应主页；
/// - 数字片段 / 整行进「影响明细」iOS 底部 sheet，展示来源摘要 + 云侧样本视觉；
///   完整名单（[AuthorImpactItem.evidenceSnapshotId] / 分页）未就绪时只展示样本、不编造全量。
/// other 模式无数据不占位，mine 模式空态展示鼓励发布文案。
class AuthorImpactCard extends ConsumerWidget {
  const AuthorImpactCard({
    super.key,
    required this.summary,
    required this.isDark,
    required this.isMine,
    this.maxItems = 3,
  });

  static const Key cardKey = ValueKey<String>('author-impact-card');
  static const Key emptyKey = ValueKey<String>('author-impact-empty');

  final AuthorImpactSummary summary;
  final bool isDark;

  /// true = 我的主页；false = 他人主页。
  final bool isMine;
  final int maxItems;

  bool get _isEmpty =>
      summary.total <= 0 ||
      summary.items.every((item) => item.primaryText.trim().isEmpty);

  IntersectionTargetNavigator _navigator(WidgetRef ref) =>
      IntersectionTargetNavigator(
        onTrack: (target, attribution) {
          final id = target.objectId.trim();
          if (id.isEmpty) {
            return;
          }
          ref
              .read(contentBehaviorTrackerProvider)
              .trackClick(
                id,
                referralSource: ReferralSource.organicFeed,
                intersectionDimension: attribution.dimension,
                intersectionSourceRef: attribution.sourceRef,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (_isEmpty && !isMine) {
      // 用户主页无影响事实不占位（不造假、不放占位数字）。
      return const SizedBox.shrink();
    }
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final visible = summary.items
        .where((item) => item.primaryText.trim().isNotEmpty)
        .take(maxItems)
        .toList(growable: false);
    final navigator = _navigator(ref);

    return IntersectionStatementCard(
      key: AuthorImpactCard.cardKey,
      topDivider: true,
      title: isMine
          ? UITextConstants.profileImpactTitleMine
          : UITextConstants.profileImpactTitleOther,
      items: _isEmpty
          ? const <IntersectionStatementItem>[]
          : <IntersectionStatementItem>[
              for (final item in visible)
                IntersectionStatementItem(
                  primaryText: item.primaryText.trim(),
                  subtitleText: '',
                  highlight: IntersectionStatementHighlight.gray,
                  spans: item.primarySpans,
                  visuals: const <IntersectionVisual>[],
                  // 四槽：① 类型图标（iconKey 回退 helpType/dimension）+ ④ 传播视图。
                  iconKey: item.iconKey,
                  sourceRef: item.source,
                  dimension: item.intersectionDimension,
                  showAuxiliaryLine: false,
                  onSpanTap: (span) =>
                      _onSpanTap(context, navigator, item, span),
                  onVisualTap: (visual) => navigator.open(
                    context,
                    visual.target,
                    attribution: _attributionFor(item),
                  ),
                  onPropagationTap: () => _showEvidence(
                    context,
                    navigator: navigator,
                    item: item,
                    isMine: isMine,
                  ),
                  onTap: () => _showEvidence(
                    context,
                    navigator: navigator,
                    item: item,
                    isMine: isMine,
                  ),
                ),
            ],
      emptyChild: Text(
        key: AuthorImpactCard.emptyKey,
        UITextConstants.profileImpactEmptyMine,
        style: TextStyle(
          fontSize: AppTypography.iosCaption1,
          height: AppSpacing.textLineHeightBody,
          color: fgSecondary,
        ),
      ),
    );
  }

  void _onSpanTap(
    BuildContext context,
    IntersectionTargetNavigator navigator,
    AuthorImpactItem item,
    IntersectionTextSpan span,
  ) {
    // 数字片段进影响明细（展示云侧样本）；名字 / 对象片段进对应主页。
    if (span.role == 'count') {
      _showEvidence(context, navigator: navigator, item: item, isMine: isMine);
      return;
    }
    navigator.open(context, span.target, attribution: _attributionFor(item));
  }

  static IntersectionNavAttribution _attributionFor(AuthorImpactItem item) {
    final tagRef = item.tagRef.trim();
    return IntersectionNavAttribution(
      dimension: item.intersectionDimension,
      sourceRef: item.source,
      evidenceId: item.evidenceSnapshotId,
      tagRefs: tagRef.isEmpty ? const <String>[] : <String>[tagRef],
    );
  }

  static Future<void> _showEvidence(
    BuildContext context, {
    required IntersectionTargetNavigator navigator,
    required AuthorImpactItem item,
    required bool isMine,
  }) {
    return showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.black.withValues(alpha: 0.32),
      builder: (sheetContext) => _AuthorImpactEvidenceSheet(
        item: item,
        isMine: isMine,
        onVisualTap: (visual) {
          Navigator.of(sheetContext).pop();
          navigator.open(
            context,
            visual.target,
            attribution: _attributionFor(item),
          );
        },
      ),
    );
  }
}

/// 影响明细底部 sheet：来源摘要 + 云侧样本视觉，不编造完整名单。
class _AuthorImpactEvidenceSheet extends StatelessWidget {
  const _AuthorImpactEvidenceSheet({
    required this.item,
    required this.isMine,
    required this.onVisualTap,
  });

  final AuthorImpactItem item;
  final bool isMine;
  final void Function(IntersectionVisual visual) onVisualTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColors.iosProfileSurface(context);
    final sourceLabel = _sourceLabel();
    final hint = isMine
        ? UITextConstants.impactEnumerableHintMine
        : UITextConstants.impactEnumerableHintOther;
    final hasVisuals = item.sampleVisuals.isNotEmpty;

    return SafeArea(
      top: false,
      child: Container(
        margin: EdgeInsets.all(AppSpacing.md),
        padding: EdgeInsets.all(AppSpacing.containerMd),
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            // 结论句（单通道真相源，纯文本直出，不在 sheet 内拆字拼装）。
            Text(
              item.primaryText.trim(),
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              hint,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.containerSm),
            _MetaRow(
              label: DiscoveryFeedText.impactEvidenceSheetSourceLabel,
              value: item.count > 0
                  ? '$sourceLabel · ${item.count}'
                  : sourceLabel,
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              DiscoveryFeedText.impactEvidenceSheetSampleLabel,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            if (hasVisuals) ...<Widget>[
              IntersectionVisualCluster(
                visuals: item.sampleVisuals,
                maxVisuals: 5,
                size: AppSpacing.avatarUserMd,
                onVisualTap: onVisualTap,
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                DiscoveryFeedText.impactEvidenceSheetFullPendingNote,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption2,
                  color: AppColors.iosTertiaryLabel(context),
                ),
              ),
            ] else
              Text(
                DiscoveryFeedText.impactEvidenceSheetNoSampleNote,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption2,
                  color: AppColors.iosTertiaryLabel(context),
                ),
              ),
            SizedBox(height: AppSpacing.containerMd),
            SizedBox(
              width: double.infinity,
              child: CupertinoButton.filled(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text(UITextConstants.confirm),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _sourceLabel() {
    final source = item.source.trim();
    if (source.isNotEmpty) {
      return source;
    }
    final subtitle = item.subtitleText.trim();
    if (subtitle.isNotEmpty) {
      return subtitle;
    }
    return isMine
        ? UITextConstants.profileImpactTitleMine
        : UITextConstants.profileImpactTitleOther;
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              color: AppColors.iosLabel(context),
            ),
          ),
        ),
      ],
    );
  }
}
