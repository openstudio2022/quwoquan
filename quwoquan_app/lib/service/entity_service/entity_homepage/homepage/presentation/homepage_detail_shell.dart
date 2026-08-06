import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/generated/homepage_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/design_system/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/design_system/navigation/tab_navigation.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/object_page/object_action_bar.dart';
import 'package:quwoquan_app/runtime/di/presentation/object_impact_preview_card.dart';
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart';
import 'package:quwoquan_app/runtime/di/presentation/object_intersection_section.dart';
import 'package:quwoquan_app/design_system/object_page/object_meta_chip.dart';
import 'package:quwoquan_app/design_system/object_page/object_chrome_actions.dart';
import 'package:quwoquan_app/design_system/object_page/object_page_shell.dart';
import 'package:quwoquan_app/design_system/object_page/object_page_sections.dart';
import 'package:quwoquan_app/design_system/object_page/object_secondary_filter_bar.dart';
import 'package:quwoquan_app/design_system/object_page/object_slogan_card.dart';
import 'package:quwoquan_app/design_system/object_page/object_stats_row.dart';
import 'package:quwoquan_app/design_system/media/content_preview_card.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_appearance.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/di/shell/actions/global_surface_actions.dart';
import 'package:quwoquan_app/design_system/formatters/compact_count_formatter.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_ref_label.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/runtime/di/presentation/intersection_reason_chip.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/domain/homepage_tab.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_type_labels.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_review_section.dart';

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
    required this.viewerPersonaId,
    required this.viewerOwnerUserId,
    required this.wishlistState,
    required this.initialTabTarget,
    required this.onBack,
    required this.onShare,
    required this.onClaim,
    required this.onMaintain,
    required this.onReport,
    required this.onToggleFollow,
    required this.onMessageOwner,
    required this.onCreateContent,
    required this.onOpenIntroduction,
    required this.onOpenRecord,
    required this.onAttach,
    this.onReviewsChanged,
    this.requireReviewAuth,
    this.reviewContinuationResumeToken = 0,
  });

  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final bool isLoading;
  final String? errorText;
  final HomepageDetail? detail;
  final HomepageShellData? shell;
  final ObjectPageBundle? objectPageBundle;
  final String? introductionSummary;
  final String? viewerPersonaId;
  final String? viewerOwnerUserId;

  /// null 表示该主页类型不适用「想去」，继续展示关注语义。
  final bool? wishlistState;
  final HomepageDetailTabTarget? initialTabTarget;
  final VoidCallback onBack;
  final VoidCallback onShare;
  final VoidCallback onClaim;
  final VoidCallback onMaintain;
  final VoidCallback onReport;
  final VoidCallback onToggleFollow;
  final VoidCallback onMessageOwner;
  final ValueChanged<HomepageCanonicalReference> onCreateContent;
  final VoidCallback onOpenIntroduction;
  final ValueChanged<HomepageContentPreview> onOpenRecord;
  final ValueChanged<HomepageCanonicalReference> onAttach;

  /// 评价写/改/删成功后回调（宿主刷新评分摘要）。
  final VoidCallback? onReviewsChanged;

  /// 评价写操作前的登录闸口。
  final Future<bool> Function()? requireReviewAuth;

  /// 登录成功后续接评价编辑器的一次性变化令牌。
  final int reviewContinuationResumeToken;

  @override
  State<HomepageDetailShell> createState() => _HomepageDetailShellState();
}

class _HomepageDetailShellState extends State<HomepageDetailShell> {
  static const double _cardRadius = AppSpacing.radiusTwentyFour;
  static const double _identityAvatarIntrusion =
      ObjectIdentityHeader.avatarOuterExtentDefault *
      ObjectIdentityHeader.avatarOverlapRatioDefault;
  static const double _identityPinExtent =
      ObjectIdentityHeader.avatarOuterExtentDefault - _identityAvatarIntrusion;
  static final List<_HomepagePrimaryTabSpec> _tabs = HomepageUIConfig.tabs
      .map(
        (tab) => _HomepagePrimaryTabSpec(
          id: tab.id,
          label: homepageTabLabelForKey(tab.labelKey),
        ),
      )
      .toList(growable: false);

  late String _activeTabId;

  static final String _defaultContentSubTabId = HomepageUIConfig.subTabs
      .firstWhere(
        (tab) => tab.isDefault,
        orElse: () => HomepageUIConfig.subTabs.first,
      )
      .id;

  String _activeContentSubTabId = _defaultContentSubTabId;

  @override
  void initState() {
    super.initState();
    _activeTabId = homepageTabIdForTarget(widget.initialTabTarget);
  }

  @override
  void didUpdateWidget(covariant HomepageDetailShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialTabTarget != widget.initialTabTarget) {
      _activeTabId = homepageTabIdForTarget(widget.initialTabTarget);
    }
    if (oldWidget.reviewContinuationResumeToken !=
        widget.reviewContinuationResumeToken) {
      _activeTabId = homepageTabIdForTarget(HomepageDetailTabTarget.record);
      _activeContentSubTabId = 'opinion';
    }
  }

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

  /// 实体主页展示标签：消费 [ObjectPageBundle.tagRefs]（数据工程 publish/tags
  /// 契约树全路径，含 Entity 类型 + Topic 地理/主题标签，WP3 统一打标产物），
  /// 缺省回退 detail.categoryTags（云侧同源投影）。`Format/**` 属内容载体
  /// 标签，对地点主页无展示价值，滤除；展示名 = 叶子名（tagRefDisplayLabels）。
  List<String> get _displayTagLabels {
    final bundleRefs = widget.objectPageBundle?.tagRefs ?? const <String>[];
    final refs = bundleRefs.isNotEmpty
        ? bundleRefs
        : (widget.detail?.categoryTags ?? const <String>[]);
    return tagRefDisplayLabels(
      refs.where((ref) => !ref.trimLeft().startsWith('Format/')),
    );
  }

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

  bool get _canMessageOwner {
    final detail = widget.detail;
    if (detail == null ||
        (detail.claimStatus ?? '').trim() != 'claimed' ||
        _isOwnerLike) {
      return false;
    }
    return (detail.ownerPersonaId ?? detail.ownerUserId ?? '')
        .trim()
        .isNotEmpty;
  }

  bool get _canReport =>
      widget.detail != null &&
      (widget.detail!.status ?? '').trim() != 'offline';

  /// 站外分享仅对已发布主页开放；候选/下线主页对外链接无消费价值。
  bool get _canShare =>
      widget.detail != null &&
      (widget.detail!.status ?? '').trim() == 'published';

  bool get _hasMoreActions =>
      !widget.selectionMode &&
      (_canShare || _isOwnerLike || _canClaim || _canReport);

  Future<void> _showMoreActions(BuildContext context) async {
    if (!_hasMoreActions) {
      return;
    }
    final sections = <AppActionSheetSection<_HomepageMoreAction>>[];
    final primaryItems = <AppActionSheetItem<_HomepageMoreAction>>[];
    if (_canShare) {
      primaryItems.add(
        const AppActionSheetItem<_HomepageMoreAction>(
          value: _HomepageMoreAction.share,
          label: ObjectHomepageText.homepageShareAction,
          icon: CupertinoIcons.arrowshape_turn_up_right,
        ),
      );
    }
    if (_isOwnerLike) {
      primaryItems.add(
        const AppActionSheetItem<_HomepageMoreAction>(
          value: _HomepageMoreAction.maintain,
          label: ObjectHomepageText.homepageMaintainAction,
          icon: CupertinoIcons.pencil,
        ),
      );
    } else if (_canClaim) {
      primaryItems.add(
        const AppActionSheetItem<_HomepageMoreAction>(
          value: _HomepageMoreAction.claim,
          label: ObjectHomepageText.homepageClaimAction,
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
              label: ObjectHomepageText.homepageStatusReportAction,
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      );
    }
    final action = await showAppActionSheet<_HomepageMoreAction>(
      context,
      title: _reference?.title ?? ObjectHomepageText.objectHomepageDefaultTitle,
      sections: sections,
    );
    if (!context.mounted || action == null) {
      return;
    }
    switch (action) {
      case _HomepageMoreAction.share:
        widget.onShare();
      case _HomepageMoreAction.claim:
        widget.onClaim();
      case _HomepageMoreAction.maintain:
        widget.onMaintain();
      case _HomepageMoreAction.report:
        widget.onReport();
    }
  }

  Widget _buildContentTab(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final subTabs = _visibleContentSubTabs;
    final activeId = subTabs.any((tab) => tab.id == _activeContentSubTabId)
        ? _activeContentSubTabId
        : _defaultContentSubTabId;
    // 口碑子 tab 消费 HomepageReview 对象真实数据（读写全链），
    // 不再从 contentPreview 记录流过滤伪造的 review 类型。
    final isOpinionTab = activeId == 'opinion';
    if (_contentPreview.isEmpty && !isOpinionTab) {
      return _buildMessageCard(
        context,
        title: ObjectHomepageText.homepageContentSectionTitle,
        child: _HomepageEmptyState(
          icon: CupertinoIcons.square_stack_3d_up,
          title: ObjectHomepageText.homepageContentEmptyTitle,
          description: ObjectHomepageText.homepageContentEmptyDescription,
        ),
      );
    }
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
          if (isOpinionTab)
            _buildReviewSection(context)
          else if (filtered.isEmpty)
            ProfileIosSectionCard(
              child: _HomepageEmptyState(
                icon: CupertinoIcons.square_stack_3d_up,
                title: ObjectHomepageText.homepageContentEmptyTitle,
                description: ObjectHomepageText.homepageContentEmptyDescription,
              ),
            )
          else
            GridView.builder(
              physics: const NeverScrollableScrollPhysics(),
              shrinkWrap: true,
              primary: false,
              padding: EdgeInsets.zero,
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: AppSpacing.responsiveGridColumns(context),
                mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                mainAxisExtent: _contentGridMainAxisExtent(context),
              ),
              itemCount: filtered.length,
              itemBuilder: (context, index) =>
                  _buildEntityRecordCard(filtered[index], isDark),
            ),
        ],
      ),
    );
  }

  Widget _buildReviewSection(BuildContext context) {
    final homepageId = (widget.detail?.id ?? _reference?.id ?? '').trim();
    if (homepageId.isEmpty) {
      return ProfileIosSectionCard(
        child: _HomepageEmptyState(
          icon: CupertinoIcons.star,
          title: ObjectHomepageText.homepageReviewEmptyTitle,
          description: ObjectHomepageText.homepageReviewEmptyDescription,
        ),
      );
    }
    return HomepageReviewSection(
      key: ValueKey<String>('homepage-review-section-$homepageId'),
      homepageId: homepageId,
      tagOptions: widget.detail?.categoryTags ?? const <String>[],
      onReviewsChanged: widget.onReviewsChanged,
      requireAuth: widget.requireReviewAuth,
      resumeComposerToken: widget.reviewContinuationResumeToken,
    );
  }

  double _contentGridMainAxisExtent(BuildContext context) {
    final columns = AppSpacing.responsiveGridColumns(context);
    if (columns <= 1) {
      return AppSpacing.threeHundredTwenty + AppSpacing.twoHundredTwenty;
    }
    return AppSpacing.threeHundredTwenty + AppSpacing.buttonHeight * 2;
  }

  /// 实体记录卡：封面 + 卡内唯一交集句（[IntersectionReasonChip]）+ 标题 + 类型角标。
  /// 与用户/圈子记录卡同范式；无交集来源不展示、不占位（G2）。
  Widget _buildEntityRecordCard(HomepageContentPreview item, bool isDark) {
    final contentType = (item.contentType ?? '').trim();
    final authorName = (item.authorName ?? '').trim();
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return ContentPreviewCard(
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
        contextObjectName: item.title.trim().isNotEmpty
            ? item.title.trim()
            : (item.summary ?? '').trim(),
        contextObjectTarget: IntersectionTarget(
          objectType: 'post',
          objectId: item.postId,
          objectKind: 'content',
          routeId: 'workBrowser',
        ),
      ),
      // 高保口径：footer 与圈子记录卡统一为「作者名 + 心形赞数」（ContentCardMetric）。
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
          ContentCardMetric(
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
      onTap: item.postId.trim().isEmpty
          ? null
          : () => widget.onOpenRecord(item),
    );
  }

  Widget _buildDiscussionTab(BuildContext context) {
    final objectName = (_reference?.title ?? '').trim();
    final sectionTitle = objectName.isEmpty
        ? ObjectHomepageText.homepageDiscussionSectionTitle
        : UITextConstants.homepageDiscussionSectionTitleFor(objectName);
    if (_questionPreview.isEmpty) {
      return _buildMessageCard(
        context,
        title: sectionTitle,
        child: _HomepageEmptyState(
          icon: CupertinoIcons.chat_bubble_2_fill,
          title: ObjectHomepageText.homepageDiscussionEmptyTitle,
          description: ObjectHomepageText.homepageDiscussionEmptyDescription,
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
                label: ObjectHomepageText.objectTabDiscussion,
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
        title: ObjectHomepageText.homepageInterestCircleSectionTitle,
        child: _HomepageEmptyState(
          icon: CupertinoIcons.person_3_fill,
          title: ObjectHomepageText.homepageInterestCircleEmptyTitle,
          description:
              ObjectHomepageText.homepageInterestCircleEmptyDescription,
        ),
      );
    }

    return _buildSectionBlock(
      context: context,
      title: ObjectHomepageText.homepageInterestCircleSectionTitle,
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
                          extra: const CircleDetailPageRouteExtra(
                            referralSource: ReferralSource.entityPage,
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
        pinMode: ObjectPagePinMode.standard,
        enablePinnedTabOverlay: false,
        identityPinExtent: _identityPinExtent,
        identityTransitionDistance: AppSpacing.xs,
        contentHorizontalPadding: 0,
        surfaceBridgeOverride: 0,
        tabSurfaceHorizontalPadding: 0,
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
            : null,
      ),
    );
  }
}
