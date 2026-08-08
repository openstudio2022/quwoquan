import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_visual_cluster.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';

/// 影响明细分页拉取闭包（DI）：由展示面（持有 `ref`）从
/// `authorImpactQueryProvider.listAuthorImpactEvidence` 构造并下沉，使 sheet 保持
/// 纯展示、无 Riverpod / Repository 耦合，便于横切复用与组件测试。
typedef AuthorImpactEvidenceFetcher =
    Future<AuthorImpactEvidencePage> Function({String cursor});

/// 打动条目交互的统一真相源（横切复用，R25）。
///
/// 「我的主页」打动卡（[AuthorImpactCard]）与「打动」详情时间线共用同一套：
/// - [attributionFor]：归因（dimension/source/evidence/tagRefs）；
/// - [onSpanTap]：名字/对象片段进对应主页，数字片段进影响明细 sheet；
/// - [onActionHintTap]：行动建议有目标则导航，否则进影响明细；
/// - [showEvidence]：影响明细底部 sheet（来源摘要 + 云侧完整分页明细，以被影响内容为载体）。
class AuthorImpactEvidence {
  const AuthorImpactEvidence._();

  static IntersectionNavAttribution attributionFor(AuthorImpactItem item) {
    final tagRef = item.tagRef.trim();
    return IntersectionNavAttribution(
      dimension: item.intersectionDimension,
      sourceRef: item.source,
      evidenceId: item.evidenceSnapshotId,
      tagRefs: tagRef.isEmpty ? const <String>[] : <String>[tagRef],
    );
  }

  static void onSpanTap(
    BuildContext context, {
    required IntersectionTargetNavigator navigator,
    required AuthorImpactItem item,
    required IntersectionTextSpan span,
    required bool isMine,
    required AuthorImpactEvidenceFetcher fetchEvidence,
  }) {
    // 数字片段进影响明细（展示云侧完整分页）；名字 / 对象片段进对应主页。
    if (span.role == 'count') {
      showEvidence(
        context,
        navigator: navigator,
        item: item,
        isMine: isMine,
        fetchEvidence: fetchEvidence,
      );
      return;
    }
    navigator.open(context, span.target, attribution: attributionFor(item));
  }

  static void onActionHintTap(
    BuildContext context, {
    required IntersectionTargetNavigator navigator,
    required AuthorImpactItem item,
    required IntersectionActionHint hint,
    required bool isMine,
    required AuthorImpactEvidenceFetcher fetchEvidence,
  }) {
    if (hint.target != null) {
      navigator.open(context, hint.target, attribution: attributionFor(item));
      return;
    }
    showEvidence(
      context,
      navigator: navigator,
      item: item,
      isMine: isMine,
      fetchEvidence: fetchEvidence,
    );
  }

  static Future<void> showEvidence(
    BuildContext context, {
    required IntersectionTargetNavigator navigator,
    required AuthorImpactItem item,
    required bool isMine,
    required AuthorImpactEvidenceFetcher fetchEvidence,
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (sheetContext) => AuthorImpactEvidenceSheet(
        item: item,
        isMine: isMine,
        fetchEvidence: fetchEvidence,
        onVisualTap: (visual) {
          unawaited(
            dismissAppModalAndRun(
              sheetContext,
              action: () {
                if (!context.mounted) {
                  return;
                }
                navigator.open(
                  context,
                  visual.target,
                  attribution: attributionFor(item),
                );
              },
            ),
          );
        },
        onContentTap: (target) {
          unawaited(
            dismissAppModalAndRun(
              sheetContext,
              action: () {
                if (!context.mounted) {
                  return;
                }
                navigator.open(
                  context,
                  target,
                  attribution: attributionFor(item),
                );
              },
            ),
          );
        },
      ),
    );
  }
}

/// 影响明细底部 sheet：结论句 + 来源摘要 + 云侧完整分页明细（R-ID03 端侧下钻闭合）。
///
/// 明细以被影响内容为载体逐条展示（[AuthorImpactEvidenceItem.summaryText] + 时间 +
/// 样本视觉），支持触底「加载更多」；分页结果为空（或失败）时回退展示聚合条目的样本视觉，
/// 既不编造完整名单也不暴露产生影响的具体用户身份。
class AuthorImpactEvidenceSheet extends StatefulWidget {
  const AuthorImpactEvidenceSheet({
    super.key,
    required this.item,
    required this.isMine,
    required this.fetchEvidence,
    required this.onVisualTap,
    required this.onContentTap,
  });

  final AuthorImpactItem item;
  final bool isMine;
  final AuthorImpactEvidenceFetcher fetchEvidence;
  final void Function(IntersectionVisual visual) onVisualTap;
  final void Function(IntersectionTarget target) onContentTap;

  @override
  State<AuthorImpactEvidenceSheet> createState() =>
      _AuthorImpactEvidenceSheetState();
}

class _AuthorImpactEvidenceSheetState extends State<AuthorImpactEvidenceSheet> {
  final List<AuthorImpactEvidenceItem> _items = <AuthorImpactEvidenceItem>[];
  String _cursor = '';
  bool _hasMore = false;
  bool _loadingFirst = true;
  bool _loadingMore = false;
  bool _firstFailed = false;
  bool _loadMoreFailed = false;

  @override
  void initState() {
    super.initState();
    _loadFirst();
  }

  Future<void> _loadFirst() async {
    setState(() {
      _loadingFirst = true;
      _firstFailed = false;
    });
    try {
      final page = await widget.fetchEvidence(cursor: '');
      if (!mounted) return;
      setState(() {
        _items
          ..clear()
          ..addAll(page.items);
        _cursor = page.nextCursor;
        _hasMore = page.hasMore;
        _loadingFirst = false;
      });
    } catch (error, stackTrace) {
      if (!mounted) return;
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'author_impact_evidence.load_first',
          error: error,
          stackTrace: stackTrace,
          operationId: AppCloudOperationIds.contentPostListAuthorImpactEvidence,
        ),
      );
      // 结构化降级：保留头部 + 样本兜底，不崩溃、不编造（R17）。
      setState(() {
        _loadingFirst = false;
        _firstFailed = true;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || !_hasMore) return;
    setState(() {
      _loadingMore = true;
      _loadMoreFailed = false;
    });
    try {
      final page = await widget.fetchEvidence(cursor: _cursor);
      if (!mounted) return;
      setState(() {
        _items.addAll(page.items);
        _cursor = page.nextCursor;
        _hasMore = page.hasMore;
        _loadingMore = false;
      });
    } catch (error, stackTrace) {
      if (!mounted) return;
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'author_impact_evidence.load_more',
          error: error,
          stackTrace: stackTrace,
          operationId: AppCloudOperationIds.contentPostListAuthorImpactEvidence,
        ),
      );
      setState(() {
        _loadingMore = false;
        _loadMoreFailed = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final surface = AppColors.iosProfileSurface(context);
    final hint = widget.isMine
        ? ObjectHomepageText.impactEnumerableHintMine
        : ObjectHomepageText.impactEnumerableHintOther;

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
              widget.item.primaryText.trim(),
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
              value: _sourceValue(),
            ),
            SizedBox(height: AppSpacing.containerSm),
            _buildBody(context),
            SizedBox(height: AppSpacing.containerMd),
            SizedBox(
              width: double.infinity,
              child: CupertinoButton.filled(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text(FoundationText.confirm),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loadingFirst) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: AppRequestFeedback.section(),
      );
    }
    if (_items.isNotEmpty) {
      return _buildList(context);
    }
    // 分页为空 / 失败：回退聚合条目样本（真实样本，不编造完整名单）。
    final visuals = widget.item.sampleVisuals;
    if (visuals.isNotEmpty) {
      return _buildSampleFallback(context, visuals);
    }
    if (_firstFailed) {
      return _buildErrorState(context);
    }
    return Text(
      DiscoveryFeedText.impactEvidenceSheetEmptyNote,
      style: TextStyle(
        fontSize: AppTypography.iosCaption2,
        color: AppColors.iosTertiaryLabel(context),
      ),
    );
  }

  Widget _buildList(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          DiscoveryFeedText.impactEvidenceSheetDetailLabel,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height * 0.4,
          ),
          child: ListView.separated(
            shrinkWrap: true,
            padding: EdgeInsets.zero,
            itemCount: _items.length + (_hasMore ? 1 : 0),
            separatorBuilder: (_, _) =>
                SizedBox(height: AppSpacing.intraGroupSm),
            itemBuilder: (context, index) {
              if (index >= _items.length) {
                return _buildLoadMore(context);
              }
              return _EvidenceRow(
                item: _items[index],
                onVisualTap: widget.onVisualTap,
                onContentTap: widget.onContentTap,
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildLoadMore(BuildContext context) {
    if (_loadingMore) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: AppRequestFeedback.section(),
      );
    }
    return Align(
      alignment: Alignment.center,
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
        onPressed: _loadMore,
        child: Text(
          _loadMoreFailed
              ? ContentText.tryAgain
              : DiscoveryFeedText.impactEvidenceSheetLoadMore,
          style: TextStyle(fontSize: AppTypography.iosFootnote),
        ),
      ),
    );
  }

  Widget _buildSampleFallback(
    BuildContext context,
    List<IntersectionVisual> visuals,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          DiscoveryFeedText.impactEvidenceSheetSampleLabel,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        IntersectionVisualCluster(
          visuals: visuals,
          maxVisuals: 5,
          size: AppSpacing.avatarUserMd,
          onVisualTap: widget.onVisualTap,
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        Text(
          DiscoveryFeedText.impactEvidenceSheetFullPendingNote,
          style: TextStyle(
            fontSize: AppTypography.iosCaption2,
            color: AppColors.iosTertiaryLabel(context),
          ),
        ),
      ],
    );
  }

  Widget _buildErrorState(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          DiscoveryFeedText.impactEvidenceSheetLoadFailed,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        CupertinoButton(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
          onPressed: _loadFirst,
          child: Text(
            FoundationText.retry,
            style: TextStyle(fontSize: AppTypography.iosFootnote),
          ),
        ),
      ],
    );
  }

  String _sourceValue() {
    final source = widget.item.source.trim();
    final label = source.isNotEmpty
        ? source
        : (widget.item.subtitleText.trim().isNotEmpty
              ? widget.item.subtitleText.trim()
              : (widget.isMine
                    ? ContentText.profileImpactTitleMine
                    : ContentText.profileImpactTitleOther));
    return widget.item.count > 0 ? '$label · ${widget.item.count}' : label;
  }
}

/// 单条影响来源行：样本视觉 + 摘要 + 发生时间，整行可点进被影响内容。
class _EvidenceRow extends StatelessWidget {
  const _EvidenceRow({
    required this.item,
    required this.onVisualTap,
    required this.onContentTap,
  });

  final AuthorImpactEvidenceItem item;
  final void Function(IntersectionVisual visual) onVisualTap;
  final void Function(IntersectionTarget target) onContentTap;

  @override
  Widget build(BuildContext context) {
    final visual = item.sampleVisual;
    final occurredAt = _formatOccurredAt(item.occurredAt);
    final target = item.contentTarget;
    final tappable = target != null && target.objectId.trim().isNotEmpty;
    final row = Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        if (visual != null) ...<Widget>[
          IntersectionVisualCluster(
            visuals: <IntersectionVisual>[visual],
            maxVisuals: 1,
            size: AppSpacing.avatarUserSm,
            onVisualTap: onVisualTap,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
        ],
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                item.summaryText.trim(),
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  color: AppColors.iosLabel(context),
                ),
              ),
              if (occurredAt.isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  occurredAt,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption2,
                    color: AppColors.iosTertiaryLabel(context),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (tappable)
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppTypography.iosFootnote,
            color: AppColors.iosTertiaryLabel(context),
          ),
      ],
    );
    if (!tappable) {
      return row;
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onContentTap(target),
      child: row,
    );
  }

  static String _formatOccurredAt(DateTime value) {
    final dt = value.toLocal();
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    return '${dt.year}-$m-$d';
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
