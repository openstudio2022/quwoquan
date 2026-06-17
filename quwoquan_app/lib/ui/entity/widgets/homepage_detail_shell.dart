import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';
import 'package:quwoquan_app/components/object_page/object_page_sections.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_tab.dart';

part 'homepage_detail_shell_components.dart';
part 'homepage_detail_shell_components2.dart';
part 'homepage_detail_shell_builders.dart';

class HomepageDetailShell extends StatefulWidget {
  const HomepageDetailShell({
    super.key,
    required this.selectionMode,
    required this.initialSummary,
    required this.isLoading,
    required this.errorText,
    required this.detail,
    required this.shell,
    required this.objectPageBundle,
    required this.introductionSummary,
    required this.viewerOwnerUserId,
    required this.onBack,
    required this.onClaim,
    required this.onMaintain,
    required this.onReport,
    required this.onToggleFollow,
    required this.onMessageOwner,
    required this.onCreateContent,
    required this.onOpenIntroduction,
    required this.onAttach,
    this.onIntersectionReasonTap,
  });

  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final bool isLoading;
  final String? errorText;
  final HomepageDetail? detail;
  final HomepageShellData? shell;
  final ObjectPageBundle? objectPageBundle;
  final String? introductionSummary;
  final String? viewerOwnerUserId;
  final VoidCallback onBack;
  final VoidCallback onClaim;
  final VoidCallback onMaintain;
  final VoidCallback onReport;
  final VoidCallback onToggleFollow;
  final VoidCallback onMessageOwner;
  final ValueChanged<HomepageCanonicalReference> onCreateContent;
  final VoidCallback onOpenIntroduction;
  final ValueChanged<HomepageCanonicalReference> onAttach;
  final ValueChanged<IntersectionReason>? onIntersectionReasonTap;

  @override
  State<HomepageDetailShell> createState() => _HomepageDetailShellState();
}

class _HomepageDetailShellState extends State<HomepageDetailShell> {
  static const double _cardRadius = AppSpacing.radiusTwentyFour;
  static final List<_HomepagePrimaryTabSpec> _tabs = HomepageUIConfig.tabs
      .map(
        (tab) => _HomepagePrimaryTabSpec(
          id: tab.id,
          label: homepageTabLabelForKey(tab.labelKey),
        ),
      )
      .toList(growable: false);

  String _activeTabId = HomepageUIConfig.defaultTabId;

  static final String _defaultContentSubTabId = HomepageUIConfig.subTabs
      .firstWhere(
        (tab) => tab.isDefault,
        orElse: () => HomepageUIConfig.subTabs.first,
      )
      .id;

  String _activeContentSubTabId = _defaultContentSubTabId;

  /// 二级过滤可见集：无 homepageTypes 约束的全展示；有约束的仅匹配类型展示
  /// （如「校园生活」仅 school）。真相源 = codegen [HomepageUIConfig.subTabs]。
  List<HomepageSubTabConfig> get _visibleContentSubTabs {
    final homepageType = (_reference?.homepageType ?? '').trim();
    return HomepageUIConfig.subTabs
        .where(
          (tab) =>
              tab.homepageTypes.isEmpty ||
              tab.homepageTypes.contains(homepageType),
        )
        .toList(growable: false);
  }

  /// 二级过滤 id → 记录媒体类型；all/campus_life 不按媒体类型收窄。
  String? _contentTypeForSubTab(String subTabId) {
    switch (subTabId) {
      case 'image':
        return 'image';
      case 'video':
        return 'video';
      case 'article':
        return 'article';
      default:
        return null;
    }
  }

  List<HomepageContentPreview> _filteredContentPreviewFor(String subTabId) {
    final wantType = _contentTypeForSubTab(subTabId);
    if (wantType == null) {
      return _contentPreview;
    }
    return _contentPreview
        .where((item) => (item.contentType ?? '').trim() == wantType)
        .toList(growable: false);
  }

  HomepageCanonicalReference? get _reference =>
      widget.detail?.canonicalReference ??
      widget.initialSummary?.canonicalReference;

  HomepageReviewSummaryData? get _reviewSummary =>
      widget.shell?.reviewSummary ?? widget.detail?.reviewSummary;

  List<HomepageContentPreview> get _contentPreview =>
      widget.objectPageBundle?.highlightItems.isNotEmpty == true
      ? widget.objectPageBundle!.highlightItems
      : widget.shell?.contentPreview.isNotEmpty == true
      ? widget.shell!.contentPreview
      : widget.detail?.contentPreview ?? const <HomepageContentPreview>[];

  List<HomepageQuestionPreview> get _questionPreview =>
      widget.shell?.questionPreview.isNotEmpty == true
      ? widget.shell!.questionPreview
      : widget.detail?.questionPreview ?? const <HomepageQuestionPreview>[];

  List<HomepageRelatedGroupSummary> get _relatedGroups =>
      widget.objectPageBundle?.relatedObjects.isNotEmpty == true
      ? widget.objectPageBundle!.relatedObjects
      : widget.shell?.relatedGroups.isNotEmpty == true
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
          label: UITextConstants.homepageMaintainAction,
          icon: CupertinoIcons.pencil,
        ),
      );
    } else if (_canClaim) {
      primaryItems.add(
        const AppActionSheetItem<_HomepageMoreAction>(
          value: _HomepageMoreAction.claim,
          label: UITextConstants.homepageClaimAction,
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
              label: UITextConstants.homepageStatusReportAction,
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      );
    }
    final action = await showAppActionSheet<_HomepageMoreAction>(
      context,
      title: _reference?.title ?? UITextConstants.objectHomepageDefaultTitle,
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

  Widget _buildContentTab(BuildContext context) {
    if (_contentPreview.isEmpty) {
      return _buildMessageCard(
        context,
        title: UITextConstants.homepageContentSectionTitle,
        child: _HomepageEmptyState(
          icon: CupertinoIcons.square_stack_3d_up,
          title: UITextConstants.homepageContentEmptyTitle,
          description: UITextConstants.homepageContentEmptyDescription,
        ),
      );
    }
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final subTabs = _visibleContentSubTabs;
    final activeId = subTabs.any((tab) => tab.id == _activeContentSubTabId)
        ? _activeContentSubTabId
        : _defaultContentSubTabId;
    final filtered = _filteredContentPreviewFor(activeId);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: ProfileIosSectionHeader(
                  title: UITextConstants.homepageContentSectionTitle,
                  padding: EdgeInsets.only(
                    left: AppSpacing.containerXs,
                    bottom: AppSpacing.intraGroupSm,
                  ),
                ),
              ),
              if (subTabs.length > 1)
                _buildContentFilterButton(context, subTabs, activeId),
            ],
          ),
          if (filtered.isEmpty)
            ProfileIosSectionCard(
              child: _HomepageEmptyState(
                icon: CupertinoIcons.square_stack_3d_up,
                title: UITextConstants.homepageContentEmptyTitle,
                description: UITextConstants.homepageContentEmptyDescription,
              ),
            )
          else
            MasonryGridView.count(
              physics: const NeverScrollableScrollPhysics(),
              shrinkWrap: true,
              primary: false,
              padding: EdgeInsets.zero,
              crossAxisCount: AppSpacing.responsiveGridColumns(context),
              mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
              crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
              itemCount: filtered.length,
              itemBuilder: (context, index) =>
                  _buildEntityRecordCard(filtered[index], isDark),
            ),
        ],
      ),
    );
  }

  /// 记录流二级过滤入口：最右侧「当前过滤名 + 漏斗」，点击弹层选择。
  /// 与用户/圈子主页同范式（去横滑胶囊）。
  Widget _buildContentFilterButton(
    BuildContext context,
    List<HomepageSubTabConfig> subTabs,
    String activeId,
  ) {
    final activeTab = subTabs.firstWhere(
      (tab) => tab.id == activeId,
      orElse: () => subTabs.first,
    );
    final isAll = _contentTypeForSubTab(activeId) == null;
    final fg = AppColors.iosLabel(context);
    final accent = AppColors.iosAccent(context);
    return CupertinoButton(
      key: const ValueKey<String>('homepage-content-filter-button'),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      minimumSize: Size.zero,
      onPressed: () => _openContentFilterSheet(context, subTabs, activeId),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            homepageTabLabelForKey(activeTab.labelKey),
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.medium,
              color: isAll ? fg : accent,
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Icon(
            CupertinoIcons.line_horizontal_3_decrease,
            size: AppSpacing.iconSmall,
            color: isAll ? AppColors.iosSecondaryLabel(context) : accent,
          ),
        ],
      ),
    );
  }

  Future<void> _openContentFilterSheet(
    BuildContext context,
    List<HomepageSubTabConfig> subTabs,
    String activeId,
  ) async {
    final selected = await showCupertinoModalPopup<String>(
      context: context,
      builder: (sheetContext) => CupertinoActionSheet(
        title: Text(UITextConstants.profileWorksFilterTitle),
        actions: <Widget>[
          for (final tab in subTabs)
            CupertinoActionSheetAction(
              key: ValueKey<String>('homepage-content-filter-option-${tab.id}'),
              onPressed: () => Navigator.of(sheetContext).pop(tab.id),
              child: Text(homepageTabLabelForKey(tab.labelKey)),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(sheetContext).pop(),
          child: Text(UITextConstants.cancel),
        ),
      ),
    );
    if (selected != null && selected != activeId) {
      setState(() => _activeContentSubTabId = selected);
    }
  }

  /// 实体记录卡：封面 + 卡内唯一交集句（[IntersectionReasonChip]）+ 标题 + 类型角标。
  /// 与用户/圈子记录卡同范式；无交集来源不展示、不占位（G2）。
  Widget _buildEntityRecordCard(HomepageContentPreview item, bool isDark) {
    final contentType = (item.contentType ?? '').trim();
    return PostPreviewCard(
      isDark: isDark,
      title: item.title,
      supportingText: item.summary ?? '',
      coverUrl: item.coverUrl ?? '',
      showVideoBadge: contentType == 'video',
      header: IntersectionReasonChip.fromReasons(
        item.intersectionReasons,
        isDark: isDark,
      ),
      footer: Align(
        alignment: Alignment.centerLeft,
        child: _HomepageSummaryChipWidget(
          label: _contentTypeLabel(contentType),
          accent: false,
        ),
      ),
      onTap: () {},
    );
  }

  Widget _buildDiscussionTab(BuildContext context) {
    final objectName = (_reference?.title ?? '').trim();
    final sectionTitle = objectName.isEmpty
        ? UITextConstants.homepageDiscussionSectionTitle
        : UITextConstants.homepageDiscussionSectionTitleFor(objectName);
    if (_questionPreview.isEmpty) {
      return _buildMessageCard(
        context,
        title: sectionTitle,
        child: _HomepageEmptyState(
          icon: CupertinoIcons.chat_bubble_2_fill,
          title: UITextConstants.homepageDiscussionEmptyTitle,
          description: UITextConstants.homepageDiscussionEmptyDescription,
        ),
      );
    }

    return _buildSectionBlock(
      context: context,
      title: sectionTitle,
      child: ProfileIosGroupedSection(
        margin: EdgeInsets.zero,
        children: _questionPreview
            .map(
              (item) => _HomepagePreviewCell(
                title: item.title,
                subtitle: item.summary ?? '',
                label: UITextConstants.objectTabDiscussion,
                icon: CupertinoIcons.chat_bubble_2,
              ),
            )
            .toList(growable: false),
      ),
    );
  }

  Widget _buildRelatedTab(BuildContext context) {
    if (_relatedGroups.isEmpty) {
      return _buildMessageCard(
        context,
        title: UITextConstants.homepageInterestCircleSectionTitle,
        child: _HomepageEmptyState(
          icon: CupertinoIcons.person_3_fill,
          title: UITextConstants.homepageInterestCircleEmptyTitle,
          description: UITextConstants.homepageInterestCircleEmptyDescription,
        ),
      );
    }

    return _buildSectionBlock(
      context: context,
      title: UITextConstants.homepageInterestCircleSectionTitle,
      child: ProfileIosGroupedSection(
        margin: EdgeInsets.zero,
        children: _relatedGroups
            .map(
              (group) => ProfileIosGroupedCell(
                title: group.name,
                subtitle:
                    '${group.memberCount} ${UITextConstants.homepageRelatedGroupSubtitle}',
                leading: Container(
                  width: AppSpacing.buttonHeightSm,
                  height: AppSpacing.buttonHeightSm,
                  decoration: BoxDecoration(
                    color: AppColors.iosTintedFill(context),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusTwentyFour,
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
    return switch (homepageTabBodySlotForId(_activeTabId)) {
      'content' => _buildContentTab(context),
      'discussion' => _buildDiscussionTab(context),
      'interest_circles' => _buildRelatedTab(context),
      _ => _buildOverviewTab(context),
    };
  }

  void _changeActiveTab(String tabId) {
    setState(() => _activeTabId = tabId);
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      child: ObjectPageShell(
        keyPrefix: 'homepage-shell',
        pinMode: ObjectPagePinMode.minimal,
        enablePinnedTabOverlay: false,
        contentHorizontalPadding: AppSpacing.containerMd,
        tabSurfaceBottomPadding: AppSpacing.containerLg,
        scrollViewKey: TestKeys.homepageDetailPage,
        backgroundBuilder: (c, pull) => _buildBackgroundLayer(c),
        summaryBuilder: (c) => _buildSummaryCard(c),
        toolbarBuilder: (c, identity, bg) => _buildToolbar(c, identity),
        tabBarBuilder: (c, pinned, opacity) => _buildPrimaryTabBar(c),
        tabBodyBuilder: (c) => Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.containerSm,
            AppSpacing.containerMd,
            0,
          ),
          child: _buildActiveTabContent(c),
        ),
        bottomBar: widget.selectionMode
            ? _HomepageBottomActionBar(
                enabled: _canCreateFromHomepage,
                onPressed: () {
                  final reference = _reference;
                  if (reference != null) {
                    widget.onAttach(reference);
                  }
                },
              )
            : null,
      ),
    );
  }
}
