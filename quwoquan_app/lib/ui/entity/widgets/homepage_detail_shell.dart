import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

class HomepageDetailShell extends StatefulWidget {
  const HomepageDetailShell({
    super.key,
    required this.selectionMode,
    required this.initialSummary,
    required this.isLoading,
    required this.errorText,
    required this.detail,
    required this.shell,
    required this.viewerOwnerUserId,
    required this.onBack,
    required this.onClaim,
    required this.onMaintain,
    required this.onReport,
    required this.onCreateContent,
    required this.onAttach,
  });

  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final bool isLoading;
  final String? errorText;
  final HomepageDetail? detail;
  final HomepageShellData? shell;
  final String? viewerOwnerUserId;
  final VoidCallback onBack;
  final VoidCallback onClaim;
  final VoidCallback onMaintain;
  final VoidCallback onReport;
  final ValueChanged<HomepageCanonicalReference> onCreateContent;
  final ValueChanged<HomepageCanonicalReference> onAttach;

  @override
  State<HomepageDetailShell> createState() => _HomepageDetailShellState();
}

class _HomepageDetailShellState extends State<HomepageDetailShell> {
  static const double _cardRadius = AppSpacing.radiusTwenty;
  static const double _surfaceBridge = _cardRadius;
  static const List<_HomepagePrimaryTabSpec> _tabs = <_HomepagePrimaryTabSpec>[
    _HomepagePrimaryTabSpec(id: 'overview', label: '概览'),
    _HomepagePrimaryTabSpec(id: 'content', label: '内容'),
    _HomepagePrimaryTabSpec(id: 'related', label: '关联'),
  ];

  late final ScrollController _scrollController;
  double _scrollOffset = 0;
  double _rawPullOffset = 0;
  double _pullOffset = 0;
  String _activeTabId = _tabs.first.id;

  HomepageCanonicalReference? get _reference =>
      widget.detail?.canonicalReference ??
      widget.initialSummary?.canonicalReference;

  HomepageReviewSummaryData? get _reviewSummary =>
      widget.shell?.reviewSummary ?? widget.detail?.reviewSummary;

  List<HomepageContentPreview> get _contentPreview =>
      widget.shell?.contentPreview.isNotEmpty == true
      ? widget.shell!.contentPreview
      : widget.detail?.contentPreview ?? const <HomepageContentPreview>[];

  List<HomepageQuestionPreview> get _questionPreview =>
      widget.shell?.questionPreview.isNotEmpty == true
      ? widget.shell!.questionPreview
      : widget.detail?.questionPreview ?? const <HomepageQuestionPreview>[];

  List<HomepageRelatedGroupSummary> get _relatedGroups =>
      widget.shell?.relatedGroups.isNotEmpty == true
      ? widget.shell!.relatedGroups
      : widget.detail?.relatedGroups ?? const <HomepageRelatedGroupSummary>[];

  bool get _canCreateFromHomepage =>
      (_reference?.status ?? widget.detail?.status ?? '').trim() == 'published';

  bool get _canClaim {
    final detail = widget.detail;
    if (detail == null) {
      return false;
    }
    final claimStatus = (detail.claimStatus ?? '').trim();
    return detail.status == 'published' &&
        (claimStatus.isEmpty ||
            claimStatus == 'unclaimed' ||
            claimStatus == 'rejected');
  }

  bool get _isClaimPending =>
      (widget.detail?.claimStatus ?? '').trim() == 'pending_review';

  bool get _isOwnerLike {
    final detail = widget.detail;
    final viewerOwnerUserId = (widget.viewerOwnerUserId ?? '').trim();
    if (detail == null || viewerOwnerUserId.isEmpty) {
      return false;
    }
    return (detail.claimStatus ?? '').trim() == 'claimed' &&
        (detail.ownerUserId ?? '').trim() == viewerOwnerUserId;
  }

  bool get _canReport =>
      widget.detail != null &&
      (widget.detail!.status ?? '').trim() != 'offline';

  bool get _hasMoreActions =>
      !widget.selectionMode && (_isOwnerLike || _canClaim || _canReport);

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController()..addListener(_handleScrollOffset);
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_handleScrollOffset)
      ..dispose();
    super.dispose();
  }

  void _handleScrollOffset() {
    if (!_scrollController.hasClients) {
      return;
    }
    final nextOffset = max(0.0, _scrollController.offset);
    if ((nextOffset - _scrollOffset).abs() < 0.5) {
      return;
    }
    setState(() => _scrollOffset = nextOffset);
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.metrics.axis != Axis.vertical) {
      return false;
    }
    if (notification is ScrollUpdateNotification ||
        notification is OverscrollNotification ||
        notification is ScrollEndNotification) {
      final pixels = notification.metrics.pixels;
      if (pixels < 0) {
        final maxPull =
            _maxStretchBackgroundHeight(context) -
            _baseBackgroundHeight(context);
        final nextRaw = -pixels;
        final nextPull = _springDampedOffset(nextRaw, maxPull);
        if ((nextRaw - _rawPullOffset).abs() < 0.5 &&
            (nextPull - _pullOffset).abs() < 0.5) {
          return false;
        }
        setState(() {
          _rawPullOffset = nextRaw;
          _pullOffset = nextPull;
        });
      } else if (_rawPullOffset != 0 || _pullOffset != 0) {
        setState(() {
          _rawPullOffset = 0;
          _pullOffset = 0;
        });
      }
    }
    return false;
  }

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) {
      return 0;
    }
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  double _baseBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        AppSpacing.profileHeaderBaseHeightRatio;
  }

  double _maxStretchBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        AppSpacing.profileHeaderMaxStretchHeightRatio;
  }

  double _currentBackgroundHeight(BuildContext context) {
    final base = _baseBackgroundHeight(context);
    final maxStretch = _maxStretchBackgroundHeight(context);
    return (base + _pullOffset).clamp(base, maxStretch);
  }

  double _backgroundSpacerHeight(BuildContext context) {
    return max(0.0, _currentBackgroundHeight(context) - _rawPullOffset);
  }

  double _toolbarRevealProgress() {
    final threshold =
        HomepageIdentityHeader.coverOuterExtent + AppSpacing.containerLg;
    return Curves.easeOutCubic.transform(
      (_scrollOffset / threshold).clamp(0.0, 1.0),
    );
  }

  List<_HomepageSummaryChip> _summaryChips() {
    final chips = <_HomepageSummaryChip>[
      _HomepageSummaryChip(label: _typeLabel(_reference?.homepageType ?? '')),
      _HomepageSummaryChip(label: _statusLabel(_reference?.status)),
    ];
    final detail = widget.detail;
    if (detail != null && (detail.claimStatus ?? '').trim().isNotEmpty) {
      chips.add(_HomepageSummaryChip(label: _claimLabel(detail.claimStatus)));
    }
    final averageRating =
        _reviewSummary?.averageRating ??
        widget.detail?.averageRating ??
        widget.initialSummary?.averageRating;
    if (averageRating != null) {
      chips.add(
        _HomepageSummaryChip(
          label: '${averageRating.toStringAsFixed(1)} 分',
          accent: true,
        ),
      );
    }
    return chips;
  }

  Future<void> _showMoreActions(BuildContext context) async {
    if (!_hasMoreActions) {
      return;
    }
    final sections = <AppActionSheetSection<_HomepageMoreAction>>[];
    final primaryItems = <AppActionSheetItem<_HomepageMoreAction>>[];
    if (_isOwnerLike) {
      primaryItems.add(
        const AppActionSheetItem<_HomepageMoreAction>(
          value: _HomepageMoreAction.maintain,
          label: '维护主页',
          icon: CupertinoIcons.pencil,
        ),
      );
    } else if (_canClaim) {
      primaryItems.add(
        const AppActionSheetItem<_HomepageMoreAction>(
          value: _HomepageMoreAction.claim,
          label: '认领主页',
          icon: CupertinoIcons.check_mark_circled,
        ),
      );
    }
    if (primaryItems.isNotEmpty) {
      sections.add(
        AppActionSheetSection<_HomepageMoreAction>(items: primaryItems),
      );
    }
    if (_canReport) {
      sections.add(
        const AppActionSheetSection<_HomepageMoreAction>(
          items: <AppActionSheetItem<_HomepageMoreAction>>[
            AppActionSheetItem<_HomepageMoreAction>(
              value: _HomepageMoreAction.report,
              label: '状态上报',
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      );
    }
    final action = await showAppActionSheet<_HomepageMoreAction>(
      context,
      title: _reference?.title ?? '主页',
      sections: sections,
    );
    if (!context.mounted || action == null) {
      return;
    }
    switch (action) {
      case _HomepageMoreAction.claim:
        widget.onClaim();
      case _HomepageMoreAction.maintain:
        widget.onMaintain();
      case _HomepageMoreAction.report:
        widget.onReport();
    }
  }

  void _handlePrimaryAction() {
    final reference = _reference;
    if (reference == null || !_canCreateFromHomepage) {
      return;
    }
    widget.onCreateContent(reference);
  }

  Widget _buildConstrainedContent(Widget child) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSpacing.feedMaxContentWidth,
        ),
        child: child,
      ),
    );
  }

  Widget _buildToolbar(BuildContext context) {
    final progress = _toolbarRevealProgress();
    final safeTop = MediaQuery.paddingOf(context).top;
    final toolbarFill = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: progress * 0.92);
    final toolbarBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: progress * 0.14);
    final buttonForeground =
        Color.lerp(
          CupertinoColors.white,
          AppColors.iosLabel(context),
          progress,
        ) ??
        AppColors.iosLabel(context);
    final buttonBackground =
        Color.lerp(
          AppColors.black.withValues(alpha: 0.18),
          AppColors.iosFill(context).withValues(alpha: 0.94),
          progress,
        ) ??
        AppColors.iosFill(context);

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          safeTop + AppSpacing.intraGroupXs,
          AppSpacing.containerMd,
          AppSpacing.intraGroupXs,
        ),
        decoration: BoxDecoration(
          color: toolbarFill,
          border: Border(
            bottom: BorderSide(
              color: toolbarBorder,
              width: AppSpacing.hairline,
            ),
          ),
        ),
        child: Row(
          children: <Widget>[
            ProfileIosIconButton(
              icon: widget.selectionMode
                  ? CupertinoIcons.xmark
                  : CupertinoIcons.chevron_back,
              onPressed: widget.onBack,
              backgroundColor: buttonBackground,
              foregroundColor: buttonForeground,
            ),
            Expanded(
              child: IgnorePointer(
                child: Opacity(
                  opacity: progress,
                  child: Text(
                    _reference?.title ?? '',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosNavTitle,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ),
              ),
            ),
            if (_hasMoreActions)
              ProfileIosIconButton(
                key: const ValueKey<String>('homepage-detail-more-button'),
                icon: CupertinoIcons.slider_horizontal_3,
                onPressed: () => _showMoreActions(context),
                backgroundColor: buttonBackground,
                foregroundColor: buttonForeground,
              )
            else
              const SizedBox(width: AppSpacing.minInteractiveSize),
          ],
        ),
      ),
    );
  }

  Widget _buildBackgroundLayer(BuildContext context) {
    final coverUrl = (_reference?.coverUrl ?? '').trim();
    final pageBackground = AppColors.iosPageBackground(context);
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            AppColors.primaryColor.withValues(alpha: 0.22),
            AppColors.primaryColor.withValues(alpha: 0.08),
            pageBackground,
          ],
        ),
      ),
      child: Center(
        child: Icon(
          CupertinoIcons.photo_fill_on_rectangle_fill,
          size: AppSpacing.iconLarge,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        if (coverUrl.isEmpty)
          fallback
        else
          CircleMediaImage(
            imageSource: coverUrl,
            fit: BoxFit.cover,
            placeholder: fallback,
            errorWidget: fallback,
          ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: <Color>[
                AppColors.black.withValues(alpha: 0.12),
                AppColors.black.withValues(alpha: 0.06),
                pageBackground.withValues(alpha: 0.96),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSummaryCard(BuildContext context) {
    final detail = widget.detail;
    final reference = _reference;
    final summarySurface = AppColors.iosProfileSurface(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final summaryBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.08);
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);
    final locationLine = <String>[
      if ((detail?.city ?? widget.initialSummary?.city ?? '').trim().isNotEmpty)
        (detail?.city ?? widget.initialSummary?.city ?? '').trim(),
      if ((detail?.address ?? widget.initialSummary?.address ?? '')
          .trim()
          .isNotEmpty)
        (detail?.address ?? widget.initialSummary?.address ?? '').trim(),
    ].join(' · ');
    final stats = _HomepageSummaryStats(
      averageRating:
          _reviewSummary?.averageRating ??
          detail?.averageRating ??
          widget.initialSummary?.averageRating,
      ratingCount:
          _reviewSummary?.ratingCount ??
          detail?.ratingCount ??
          widget.initialSummary?.ratingCount ??
          0,
      contentCount: _contentPreview.length + _questionPreview.length,
      relatedCount: _relatedGroups.length,
    );

    return Container(
      decoration: BoxDecoration(
        color: summarySurface,
        borderRadius: BorderRadius.circular(_cardRadius),
        border: Border.all(color: summaryBorder, width: AppSpacing.hairline),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: summaryShadow,
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.feedContentHorizontal(context),
          AppSpacing.containerLg,
          AppSpacing.feedContentHorizontal(context),
          AppSpacing.containerLg,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            HomepageIdentityHeader(
              title: reference?.title ?? '主页',
              subtitle: (reference?.subtitle ?? '').trim(),
              metaLine: locationLine,
              coverUrl: reference?.coverUrl,
              trailing: _hasMoreActions
                  ? ProfileIosIconButton(
                      key: const ValueKey<String>(
                        'homepage-summary-settings-button',
                      ),
                      icon: CupertinoIcons.slider_horizontal_3,
                      onPressed: () => _showMoreActions(context),
                      style: ProfileIosIconButtonStyle.tinted,
                    )
                  : null,
            ),
            SizedBox(height: AppSpacing.containerSm),
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: _summaryChips()
                  .map(
                    (chip) => _HomepageSummaryChipWidget(
                      label: chip.label,
                      accent: chip.accent,
                    ),
                  )
                  .toList(growable: false),
            ),
            SizedBox(height: AppSpacing.containerSm),
            _HomepageStatsRow(stats: stats),
            if (!widget.selectionMode) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              _HomepageActionBar(
                canCreate: _canCreateFromHomepage,
                canClaim: _canClaim,
                isClaimPending: _isClaimPending,
                isOwnerLike: _isOwnerLike,
                onClaim: widget.onClaim,
                onMaintain: widget.onMaintain,
                onCreateContent: _handlePrimaryAction,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildPrimaryTabBar(BuildContext context) {
    final tabs = _tabs
        .map((tab) => TabItem(id: tab.id, label: tab.label))
        .toList(growable: false);
    return Container(
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.1),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        height: AppSpacing.tabNavigationHeight,
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: (tabId) => setState(() => _activeTabId = tabId),
          transparentBackground: true,
          iosProfileStyle: true,
        ),
      ),
    );
  }

  Widget _buildSectionBlock({
    required BuildContext context,
    required String title,
    required Widget child,
  }) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          ProfileIosSectionHeader(
            title: title,
            padding: EdgeInsets.only(
              left: AppSpacing.containerXs,
              right: AppSpacing.containerXs,
              bottom: AppSpacing.intraGroupSm,
            ),
          ),
          child,
        ],
      ),
    );
  }

  Widget _buildMessageCard(
    BuildContext context, {
    String? title,
    required Widget child,
  }) {
    return _buildSectionBlock(
      context: context,
      title: title ?? '说明',
      child: ProfileIosSectionCard(child: child),
    );
  }

  Widget _buildOverviewTab(BuildContext context) {
    final detail = widget.detail;
    if (detail == null) {
      if (widget.isLoading) {
        return _buildMessageCard(
          context,
          title: '加载中',
          child: const Center(child: CupertinoActivityIndicator()),
        );
      }
      return _buildMessageCard(
        context,
        title: '暂时不可用',
        child: Text(
          widget.errorText ?? '主页详情暂时不可用，请稍后重试',
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color: AppColors.iosSecondaryLabel(context),
            height: AppSpacing.textLineHeightBody,
          ),
        ),
      );
    }

    final sections = <Widget>[];
    if (_reviewSummary != null ||
        detail.averageRating != null ||
        widget.initialSummary?.averageRating != null) {
      sections.add(
        _buildSectionBlock(
          context: context,
          title: '口碑摘要',
          child: _HomepageReviewCard(
            summary: _reviewSummary,
            fallbackAverageRating:
                detail.averageRating ?? widget.initialSummary?.averageRating,
            fallbackRatingCount: detail.ratingCount,
          ),
        ),
      );
    }

    sections.add(
      _buildSectionBlock(
        context: context,
        title: '基础信息',
        child: ProfileIosGroupedSection(
          margin: EdgeInsets.zero,
          children: <Widget>[
            ProfileIosGroupedCell(
              title: '主页状态',
              subtitle: _statusLabel(detail.status),
              showChevron: false,
            ),
            if ((detail.sourceType ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: '来源',
                subtitle: _sourceLabel(detail.sourceType),
                showChevron: false,
              ),
            if ((detail.claimStatus ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: '认领状态',
                subtitle: _claimLabel(detail.claimStatus),
                showChevron: false,
              ),
            if ((detail.city ?? '').trim().isNotEmpty ||
                (detail.address ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: '位置',
                subtitle: <String>[
                  if ((detail.city ?? '').trim().isNotEmpty)
                    detail.city!.trim(),
                  if ((detail.address ?? '').trim().isNotEmpty)
                    detail.address!.trim(),
                ].join(' · '),
                showChevron: false,
              ),
            if (detail.categoryTags.isNotEmpty)
              ProfileIosGroupedCell(
                title: '分类标签',
                subtitle: detail.categoryTags.join(' · '),
                showChevron: false,
              ),
          ],
        ),
      ),
    );

    if (detail.status == 'offline' || detail.offlineAt != null) {
      sections.add(
        _buildSectionBlock(
          context: context,
          title: '历史状态',
          child: ProfileIosSectionCard(
            child: Text(
              '该主页已下线，历史口碑、关联内容与群组摘要会继续保留，方便用户回看与迁移判断。',
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosSecondaryLabel(context),
                height: AppSpacing.textLineHeightBody,
              ),
            ),
          ),
        ),
      );
    }

    if (_isOwnerLike || _canClaim || _isClaimPending) {
      final managementChildren = <Widget>[];
      if (_isOwnerLike) {
        managementChildren.add(
          ProfileIosGroupedCell(
            title: '维护主页',
            subtitle: '更新标题、简介、位置与分类标签等基础资料',
            onTap: widget.onMaintain,
          ),
        );
      } else if (_canClaim) {
        managementChildren.add(
          ProfileIosGroupedCell(
            title: '认领主页',
            subtitle: '提交营业执照、联系电话等材料进入审核',
            onTap: widget.onClaim,
          ),
        );
      } else if (_isClaimPending) {
        managementChildren.add(
          const ProfileIosGroupedCell(
            title: '认领审核中',
            subtitle: '审核通过后即可维护主页资料与状态',
            showChevron: false,
          ),
        );
      }
      if (_isOwnerLike || _canReport) {
        managementChildren.add(
          ProfileIosGroupedCell(
            title: '状态上报',
            subtitle: '主页停业、重复或关键信息失效时发起上报',
            onTap: widget.onReport,
            isDestructive: !_isOwnerLike,
          ),
        );
      }
      sections.add(
        _buildSectionBlock(
          context: context,
          title: '主页管理',
          child: ProfileIosGroupedSection(
            margin: EdgeInsets.zero,
            children: managementChildren,
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: sections,
    );
  }

  Widget _buildContentTab(BuildContext context) {
    if (_contentPreview.isEmpty && _questionPreview.isEmpty) {
      return _buildMessageCard(
        context,
        title: '相关内容',
        child: _HomepageEmptyState(
          icon: CupertinoIcons.square_stack_3d_up,
          title: '还没有内容沉淀',
          description: '后续围绕该主页发布的内容与提问会按频道沉淀在这里。',
        ),
      );
    }

    final sections = <Widget>[];
    if (_contentPreview.isNotEmpty) {
      sections.add(
        _buildSectionBlock(
          context: context,
          title: '相关内容',
          child: ProfileIosGroupedSection(
            margin: EdgeInsets.zero,
            children: _contentPreview
                .map(
                  (item) => _HomepagePreviewCell(
                    title: item.title,
                    subtitle: item.summary ?? '',
                    label: _contentTypeLabel(item.contentType ?? ''),
                    coverUrl: item.coverUrl,
                    icon: _contentTypeIcon(item.contentType ?? ''),
                  ),
                )
                .toList(growable: false),
          ),
        ),
      );
    }
    if (_questionPreview.isNotEmpty) {
      sections.add(
        _buildSectionBlock(
          context: context,
          title: '相关提问',
          child: ProfileIosGroupedSection(
            margin: EdgeInsets.zero,
            children: _questionPreview
                .map(
                  (item) => _HomepagePreviewCell(
                    title: item.title,
                    subtitle: item.summary ?? '',
                    label: '提问',
                    icon: CupertinoIcons.question_circle,
                  ),
                )
                .toList(growable: false),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: sections,
    );
  }

  Widget _buildRelatedTab(BuildContext context) {
    if (_relatedGroups.isEmpty) {
      return _buildMessageCard(
        context,
        title: '关联圈子',
        child: _HomepageEmptyState(
          icon: CupertinoIcons.person_3_fill,
          title: '还没有关联圈子',
          description: '与该主页绑定的圈子、官方群或兴趣分组会展示在这里。',
        ),
      );
    }

    return _buildSectionBlock(
      context: context,
      title: '关联圈子',
      child: ProfileIosGroupedSection(
        margin: EdgeInsets.zero,
        children: _relatedGroups
            .map(
              (group) => ProfileIosGroupedCell(
                title: group.name,
                subtitle: '${group.memberCount} 位成员 · 已关联主页',
                leading: Container(
                  width: AppSpacing.buttonHeightSm,
                  height: AppSpacing.buttonHeightSm,
                  decoration: BoxDecoration(
                    color: AppColors.iosTintedFill(context),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusTwenty,
                    ),
                  ),
                  child: Icon(
                    CupertinoIcons.person_3_fill,
                    size: AppSpacing.iconSmall,
                    color: AppColors.iosAccent(context),
                  ),
                ),
                showChevron: false,
              ),
            )
            .toList(growable: false),
      ),
    );
  }

  Widget _buildActiveTabContent(BuildContext context) {
    return switch (_activeTabId) {
      'content' => _buildContentTab(context),
      'related' => _buildRelatedTab(context),
      _ => _buildOverviewTab(context),
    };
  }

  Widget _buildTabSurface(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = AppColors.iosProfileSurface(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.08);
    final shadow = isDark
        ? AppColors.black.withValues(alpha: 0.12)
        : AppColors.black.withValues(alpha: 0.04);

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(_cardRadius),
        border: Border.all(color: border, width: AppSpacing.hairline),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: shadow,
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          SizedBox(height: _surfaceBridge),
          _buildPrimaryTabBar(context),
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              AppSpacing.containerLg,
            ),
            child: _buildActiveTabContent(context),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      child: Column(
        children: <Widget>[
          Expanded(
            child: Stack(
              children: <Widget>[
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: SizedBox(
                    height: _currentBackgroundHeight(context),
                    child: _buildBackgroundLayer(context),
                  ),
                ),
                NotificationListener<ScrollNotification>(
                  onNotification: _handleScrollNotification,
                  child: CustomScrollView(
                    key: TestKeys.homepageDetailPage,
                    controller: _scrollController,
                    physics: const BouncingScrollPhysics(
                      parent: AlwaysScrollableScrollPhysics(),
                    ),
                    slivers: <Widget>[
                      SliverToBoxAdapter(
                        child: SizedBox(
                          height: _backgroundSpacerHeight(context),
                        ),
                      ),
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.containerMd,
                          ),
                          child: _buildConstrainedContent(
                            _buildSummaryCard(context),
                          ),
                        ),
                      ),
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.fromLTRB(
                            AppSpacing.containerMd,
                            0,
                            AppSpacing.containerMd,
                            AppSpacing.containerLg,
                          ),
                          child: _buildConstrainedContent(
                            Transform.translate(
                              offset: const Offset(0, -_surfaceBridge),
                              child: _buildTabSurface(context),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                _buildToolbar(context),
              ],
            ),
          ),
          if (widget.selectionMode)
            _HomepageBottomActionBar(
              enabled: _canCreateFromHomepage,
              onPressed: () {
                final reference = _reference;
                if (reference != null) {
                  widget.onAttach(reference);
                }
              },
            ),
        ],
      ),
    );
  }
}

class HomepageIdentityHeader extends StatelessWidget {
  const HomepageIdentityHeader({
    super.key,
    required this.title,
    required this.subtitle,
    required this.metaLine,
    this.coverUrl,
    this.trailing,
  });

  final String title;
  final String subtitle;
  final String metaLine;
  final String? coverUrl;
  final Widget? trailing;

  static const double _coverBorder = AppSpacing.three;
  static const double coverExtent = AppSpacing.avatarUserXl;
  static const double coverRadius = AppSpacing.radiusTwenty;
  static const double _coverOverlapRatio = 0.34;

  static double get coverOuterExtent => coverExtent + (_coverBorder * 2);
  static double get coverIntrusion => coverOuterExtent * _coverOverlapRatio;

  Widget _buildCover(BuildContext context) {
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(coverRadius),
      ),
      child: Icon(
        CupertinoIcons.photo_fill_on_rectangle_fill,
        size: AppSpacing.iconLarge,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );

    final image = (coverUrl ?? '').trim().isEmpty
        ? fallback
        : CircleMediaImage(
            imageSource: coverUrl!,
            fit: BoxFit.cover,
            placeholder: fallback,
            errorWidget: fallback,
          );

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(coverRadius + _coverBorder),
        border: Border.all(
          color: AppColors.iosProfileSurface(context),
          width: _coverBorder,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.12),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(coverRadius),
        child: SizedBox(width: coverExtent, height: coverExtent, child: image),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.only(left: coverOuterExtent + AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(
                    child: Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle2,
                        fontWeight: AppTypography.bold,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  if (trailing != null) ...<Widget>[
                    SizedBox(width: AppSpacing.containerSm),
                    trailing!,
                  ],
                ],
              ),
              if (subtitle.trim().isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
              ],
              if (metaLine.trim().isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  metaLine,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
              ],
            ],
          ),
        ),
        Positioned(top: -coverIntrusion, left: 0, child: _buildCover(context)),
      ],
    );
  }
}

class _HomepageActionBar extends StatelessWidget {
  const _HomepageActionBar({
    required this.canCreate,
    required this.canClaim,
    required this.isClaimPending,
    required this.isOwnerLike,
    required this.onClaim,
    required this.onMaintain,
    required this.onCreateContent,
  });

  final bool canCreate;
  final bool canClaim;
  final bool isClaimPending;
  final bool isOwnerLike;
  final VoidCallback onClaim;
  final VoidCallback onMaintain;
  final VoidCallback onCreateContent;

  @override
  Widget build(BuildContext context) {
    Widget filled({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ProfileIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.filled,
        labelFontWeight: AppTypography.medium,
      );
    }

    Widget outlined({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ProfileIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.outlined,
        backgroundColor: AppColors.iosSecondaryFill(context),
        foregroundColor: AppColors.iosLabel(context),
        borderColor: AppColors.iosSeparator(context).withValues(alpha: 0.14),
        labelFontWeight: AppTypography.medium,
      );
    }

    if (isOwnerLike) {
      return Row(
        children: <Widget>[
          Expanded(
            child: outlined(
              label: '维护主页',
              icon: CupertinoIcons.pencil,
              onPressed: onMaintain,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: filled(
              label: canCreate ? '从主页发内容' : '主页暂不可发布',
              icon: CupertinoIcons.add_circled,
              onPressed: canCreate ? onCreateContent : null,
            ),
          ),
        ],
      );
    }

    if (canClaim || isClaimPending) {
      return Row(
        children: <Widget>[
          Expanded(
            child: filled(
              label: canClaim ? '认领主页' : '认领审核中',
              icon: canClaim
                  ? CupertinoIcons.check_mark_circled
                  : CupertinoIcons.time,
              onPressed: canClaim ? onClaim : null,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: outlined(
              label: canCreate ? '从主页发内容' : '主页暂不可发布',
              icon: CupertinoIcons.add_circled,
              onPressed: canCreate ? onCreateContent : null,
            ),
          ),
        ],
      );
    }

    return filled(
      label: canCreate ? '从主页发内容' : '主页暂不可发布',
      icon: CupertinoIcons.add_circled,
      onPressed: canCreate ? onCreateContent : null,
    );
  }
}

class _HomepageStatsRow extends StatelessWidget {
  const _HomepageStatsRow({required this.stats});

  final _HomepageSummaryStats stats;

  @override
  Widget build(BuildContext context) {
    final dividerColor = AppColors.iosSeparator(
      context,
    ).withValues(alpha: 0.12);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: dividerColor, width: AppSpacing.hairline),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: _HomepageStatItem(
              label: '评分',
              value: stats.averageRating?.toStringAsFixed(1) ?? '--',
            ),
          ),
          _HomepageStatDivider(color: dividerColor),
          Expanded(
            child: _HomepageStatItem(
              label: '内容',
              value: '${stats.contentCount}',
            ),
          ),
          _HomepageStatDivider(color: dividerColor),
          Expanded(
            child: _HomepageStatItem(
              label: '口碑',
              value: '${stats.ratingCount}',
            ),
          ),
          _HomepageStatDivider(color: dividerColor),
          Expanded(
            child: _HomepageStatItem(
              label: '圈子',
              value: '${stats.relatedCount}',
            ),
          ),
        ],
      ),
    );
  }
}

class _HomepageStatItem extends StatelessWidget {
  const _HomepageStatItem({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosCaption1,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _HomepageStatDivider extends StatelessWidget {
  const _HomepageStatDivider({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.hairline,
      height: AppSpacing.iconButtonMinSizeMd,
      color: color,
    );
  }
}

class _HomepageReviewCard extends StatelessWidget {
  const _HomepageReviewCard({
    required this.summary,
    required this.fallbackAverageRating,
    required this.fallbackRatingCount,
  });

  final HomepageReviewSummaryData? summary;
  final double? fallbackAverageRating;
  final int fallbackRatingCount;

  @override
  Widget build(BuildContext context) {
    final averageRating = summary?.averageRating ?? fallbackAverageRating ?? 0;
    final ratingCount = summary?.ratingCount ?? fallbackRatingCount;
    final dimensionScores = summary?.dimensionScores ?? const [];
    final highlightTags = summary?.highlightTags ?? const [];

    return ProfileIosSectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            '${averageRating.toStringAsFixed(1)} 分',
            style: TextStyle(
              fontSize: AppTypography.iosLargeTitle,
              fontWeight: AppTypography.bold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            '$ratingCount 条评分',
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          if (dimensionScores.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.containerSm),
            for (
              var index = 0;
              index < dimensionScores.length;
              index += 1
            ) ...<Widget>[
              if (index > 0)
                Padding(
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  child: Divider(
                    height: AppSpacing.one,
                    color: AppColors.iosSeparator(
                      context,
                    ).withValues(alpha: 0.12),
                  ),
                ),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      dimensionScores[index].label,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  Text(
                    dimensionScores[index].score.toStringAsFixed(1),
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.medium,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ],
              ),
            ],
          ],
          if (highlightTags.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.containerSm),
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: highlightTags
                  .map(
                    (tag) =>
                        _HomepageSummaryChipWidget(label: tag, accent: true),
                  )
                  .toList(growable: false),
            ),
          ],
        ],
      ),
    );
  }
}

class _HomepagePreviewCell extends StatelessWidget {
  const _HomepagePreviewCell({
    required this.title,
    required this.subtitle,
    required this.label,
    required this.icon,
    this.coverUrl,
  });

  final String title;
  final String subtitle;
  final String label;
  final IconData icon;
  final String? coverUrl;

  @override
  Widget build(BuildContext context) {
    final leading = _HomepagePreviewCover(coverUrl: coverUrl, icon: icon);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          leading,
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _HomepageSummaryChipWidget(label: label, accent: false),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.medium,
                    color: AppColors.iosLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
                if (subtitle.trim().isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: AppColors.iosSecondaryLabel(context),
                      height: AppSpacing.textLineHeightBody,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HomepagePreviewCover extends StatelessWidget {
  const _HomepagePreviewCover({required this.coverUrl, required this.icon});

  final String? coverUrl;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Icon(
        icon,
        size: AppSpacing.iconMedium,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );

    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      child: SizedBox(
        width: AppSpacing.oneHundred - AppSpacing.twentyEight,
        height: AppSpacing.oneHundred - AppSpacing.twentyEight,
        child: (coverUrl ?? '').trim().isEmpty
            ? fallback
            : CircleMediaImage(
                imageSource: coverUrl!,
                fit: BoxFit.cover,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}

class _HomepageEmptyState extends StatelessWidget {
  const _HomepageEmptyState({
    required this.icon,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerLg),
      child: Column(
        children: <Widget>[
          Container(
            width: AppSpacing.buttonSize,
            height: AppSpacing.buttonSize,
            decoration: BoxDecoration(
              color: AppColors.iosSecondaryFill(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            ),
            child: Icon(
              icon,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            description,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
              height: AppSpacing.textLineHeightBody,
            ),
          ),
        ],
      ),
    );
  }
}

class _HomepageBottomActionBar extends StatelessWidget {
  const _HomepageBottomActionBar({
    required this.enabled,
    required this.onPressed,
  });

  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        MediaQuery.paddingOf(context).bottom + AppSpacing.containerMd,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        border: Border(
          top: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.14),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        width: double.infinity,
        height: AppSpacing.buttonHeight,
        child: CupertinoButton.filled(
          key: TestKeys.homepageDetailAttachButton,
          onPressed: enabled ? onPressed : null,
          child: Text(enabled ? '关联到本次发布' : '该主页待审核，暂不可操作'),
        ),
      ),
    );
  }
}

class _HomepageSummaryChipWidget extends StatelessWidget {
  const _HomepageSummaryChipWidget({required this.label, required this.accent});

  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final accentColor = AppColors.iosAccent(context);
    final background = accent
        ? accentColor.withValues(alpha: 0.12)
        : AppColors.iosSecondaryFill(context);
    final foreground = accent
        ? accentColor
        : AppColors.iosSecondaryLabel(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: foreground,
        ),
      ),
    );
  }
}

class _HomepagePrimaryTabSpec {
  const _HomepagePrimaryTabSpec({required this.id, required this.label});

  final String id;
  final String label;
}

class _HomepageSummaryStats {
  const _HomepageSummaryStats({
    required this.averageRating,
    required this.ratingCount,
    required this.contentCount,
    required this.relatedCount,
  });

  final double? averageRating;
  final int ratingCount;
  final int contentCount;
  final int relatedCount;
}

class _HomepageSummaryChip {
  const _HomepageSummaryChip({required this.label, this.accent = false});

  final String label;
  final bool accent;
}

enum _HomepageMoreAction { claim, maintain, report }

String _statusLabel(String? status) {
  switch ((status ?? '').trim()) {
    case 'candidate':
      return '待发布';
    case 'offline':
      return '已下线';
    case 'published':
      return '已发布';
    default:
      return '主页';
  }
}

String _sourceLabel(String? sourceType) {
  switch ((sourceType ?? '').trim()) {
    case 'official_seed':
      return '官方初始化';
    case 'user_suggested':
      return '用户补充';
    case 'user_created':
      return '用户创建';
    default:
      return '未知来源';
  }
}

String _claimLabel(String? claimStatus) {
  switch ((claimStatus ?? '').trim()) {
    case 'pending_review':
    case 'pending':
      return '认领审核中';
    case 'claimed':
      return '已认领';
    case 'rejected':
      return '认领被退回';
    default:
      return '待认领';
  }
}

String _contentTypeLabel(String contentType) {
  switch (contentType.trim()) {
    case 'article':
      return '长文';
    case 'video':
      return '视频';
    case 'image':
      return '图片';
    default:
      return '内容';
  }
}

IconData _contentTypeIcon(String contentType) {
  switch (contentType.trim()) {
    case 'article':
      return CupertinoIcons.doc_text;
    case 'video':
      return CupertinoIcons.play_rectangle;
    case 'image':
      return CupertinoIcons.photo;
    default:
      return CupertinoIcons.square_stack_3d_up;
  }
}

String _typeLabel(String type) {
  switch (type.trim()) {
    case 'hotel':
      return '酒店';
    case 'restaurant':
      return '餐厅';
    case 'vehicle':
      return '车型';
    case 'sight':
      return '景点';
    default:
      return '主页';
  }
}
