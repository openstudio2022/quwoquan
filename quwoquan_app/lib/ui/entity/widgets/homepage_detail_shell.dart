import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/object_detail_global_bottom_nav.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_ui_config.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/object_page/object_action_bar.dart';
import 'package:quwoquan_app/components/object_page/object_impact_preview_card.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_preview_card.dart';
import 'package:quwoquan_app/components/object_page/object_chrome_actions.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';
import 'package:quwoquan_app/components/object_page/object_page_sections.dart';
import 'package:quwoquan_app/components/object_page/object_secondary_filter_bar.dart';
import 'package:quwoquan_app/components/object_page/object_slogan_card.dart';
import 'package:quwoquan_app/components/object_page/object_stats_row.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/constants/homepage_detail_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/components/content/intersection_reason_chip.dart';
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

  /// 二级过滤可见集：无 homepageTypes 约束的全展示；有约束的仅匹配类型展示。
  /// 真相源 = codegen [HomepageUIConfig.subTabs]。
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

  /// 二级过滤 id → 记录类型；all 不按媒体类型收窄。
  String? _contentTypeForSubTab(String subTabId) {
    switch (subTabId) {
      case 'image':
        return 'image';
      case 'video':
        return 'video';
      case 'opinion':
        return 'review';
      case 'question':
        return 'question';
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
          // 高保口径：一级 Tab 正下方横向胶囊（全部/图片/视频/…），左对齐、
          // 无重复「记录」二级标题；替换旧「漏斗 + 弹层」入口（漏斗改回胶囊）。
          if (subTabs.length > 1) ...<Widget>[
            ObjectSecondaryFilterBar(
              barKey: const ValueKey<String>('homepage-content-filter-bar'),
              optionKeyPrefix: 'homepage-content-filter-option-',
              items: subTabs
                  .map(
                    (tab) => ObjectSecondaryFilterItem(
                      id: tab.id,
                      label: homepageTabLabelForKey(tab.labelKey),
                    ),
                  )
                  .toList(growable: false),
              activeId: activeId,
              onSelect: (id) {
                if (id != _activeContentSubTabId) {
                  setState(() => _activeContentSubTabId = id);
                }
              },
            ),
            SizedBox(height: AppSpacing.containerSm),
          ],
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

  /// 实体记录卡：封面 + 卡内唯一交集句（[IntersectionReasonChip]）+ 标题 + 类型角标。
  /// 与用户/圈子记录卡同范式；无交集来源不展示、不占位（G2）。
  Widget _buildEntityRecordCard(HomepageContentPreview item, bool isDark) {
    final contentType = (item.contentType ?? '').trim();
    final authorName = (item.authorName ?? '').trim();
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return PostPreviewCard(
      isDark: isDark,
      title: item.title,
      supportingText: item.summary ?? '',
      coverUrl: item.coverUrl ?? '',
      showVideoBadge: contentType == 'video',
      // 内容类型移到封面角标（与圈子记录卡 grid 同范式），footer 让位给「作者 + 赞」。
      mediaOverlay: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.intraGroupXs,
        ),
        decoration: BoxDecoration(
          color: AppColors.black.withValues(alpha: 0.32),
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          _contentTypeLabel(contentType),
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.xs,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
      header: IntersectionReasonChip.fromReasons(
        item.intersectionReasons,
        isDark: isDark,
        // N5：实体主页记录卡 → 交集句对象片段点击精确归因为实体主页（非推荐流）。
        referralSource: ReferralSource.entityPage,
      ),
      // 高保口径：footer 与圈子记录卡统一为「作者名 + 心形赞数」（PostCardMetric）。
      footer: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              authorName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: fgSecondary,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          PostCardMetric(
            icon: CupertinoIcons.heart_fill,
            label: '${item.likeCount}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: _relatedGroups
            .map((group) {
              final circleId = group.circleId.trim();
              return Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.containerSm),
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: circleId.isEmpty
                      ? null
                      : () => context.push(
                          AppRoutePaths.circleDetail(
                            id: circleId,
                            sourceTheme: uiErrorAppearanceRouteValueFor(
                              context,
                            ),
                          ),
                        ),
                  child: ProfileIosSectionCard(
                    child: _HomepageRelatedCircleCard(group: group),
                  ),
                ),
              );
            })
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
        surfaceBridgeOverride: 0,
        tabSurfaceHorizontalPadding: AppSpacing.containerMd,
        tabSurfaceTopRadius: _cardRadius,
        tabSurfaceBottomPadding: AppSpacing.containerLg,
        scrollViewKey: TestKeys.homepageDetailPage,
        backgroundBuilder: (c, pull) => _buildBackgroundLayer(c),
        summaryBuilder: (c) => _buildSummaryCard(c),
        toolbarBuilder: (c, identity, bg) => _buildToolbar(c, identity),
        tabBarBuilder: (c, pinned, opacity) => _buildPrimaryTabBar(c),
        tabBodyBuilder: (c) => Padding(
          padding: EdgeInsets.only(top: AppSpacing.containerSm),
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
            // 高保口径：浏览态详情页底部保留全局导航栏（首页/视频书/+/联系/我）。
            : const ObjectDetailGlobalBottomNav(),
      ),
    );
  }
}
