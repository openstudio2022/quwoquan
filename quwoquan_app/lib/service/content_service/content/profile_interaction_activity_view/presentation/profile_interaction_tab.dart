import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/profile_interaction_activity_view_data_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_activity_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_selection.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/presentation/profile_interaction_comment_route.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show
        activePersonaContextProvider,
        chatConversationRepositoryProvider,
        chatMessageCommandWriterProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart'
    show profileCommentsContentCommentFacetProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show profileInteractionQueryFacetProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/observability/trackers/comment_observability.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/design_system/navigation/secondary_tab_bar.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide InteractionDirection;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud_contracts
    show InteractionDirection;

part 'profile_interaction_tab_widgets.dart';
part 'profile_interaction_tab_inline_actions.dart';

typedef ProfileShareInteractionBuilder =
    Widget Function({
      required ShareInteractionDirection direction,
      required String personaId,
      required bool inlineScroll,
    });

class ProfileInteractionTab extends ConsumerStatefulWidget {
  const ProfileInteractionTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
    required this.selectedSubTab,
    required this.selectedDirection,
    required this.onSubTabSelected,
    required this.onDirectionSelected,
    required this.shareInteractionBuilder,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;
  final InteractionSubTab selectedSubTab;
  final InteractionDirection selectedDirection;
  final ValueChanged<InteractionSubTab> onSubTabSelected;
  final ValueChanged<InteractionDirection> onDirectionSelected;
  final ProfileShareInteractionBuilder shareInteractionBuilder;

  @override
  ConsumerState<ProfileInteractionTab> createState() =>
      _ProfileInteractionTabState();
}

class _ProfileInteractionTabState extends ConsumerState<ProfileInteractionTab>
    with _ProfileInlineActionsMixin {
  static const double _previewAspectRatio =
      DiscoveryFeedSpacing.homeFeedArticleSideThumbAspectRatio;

  List<UserProfileSubTabConfig> get _interactionFilters => UserProfileUIConfig
      .interactionSubTabs
      .where((filter) => filter.visibleInMode(widget.mode.name))
      .toList(growable: false);

  List<ProfileInteractionActivityViewData>? _items;
  bool _loading = true;
  Object? _loadError;
  InteractionSubTab? _loadedSubTab;
  InteractionDirection? _loadedDirection;

  @override
  void initState() {
    super.initState();
    _loadedSubTab = widget.selectedSubTab;
    _loadedDirection = widget.selectedDirection;
    _load();
  }

  Future<void> _load() async {
    final direction = widget.selectedDirection;
    final subTab = widget.selectedSubTab;
    _loadedDirection = direction;
    _loadedSubTab = subTab;
    if (subTab == InteractionSubTab.shares) {
      if (mounted) {
        setState(() {
          _items = null;
          _loading = false;
        });
      }
      return;
    }
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final page = await ref
          .read(profileInteractionQueryFacetProvider)
          .listActivities(
            ContentProfileInteractionPageQuery(
              personaId: widget.userId,
              type: switch (subTab) {
                InteractionSubTab.likes => InteractionActivityType.like,
                InteractionSubTab.comments => InteractionActivityType.comment,
                InteractionSubTab.shares => InteractionActivityType.share,
              },
            ),
            direction: direction == InteractionDirection.received
                ? cloud_contracts.InteractionDirection.received
                : cloud_contracts.InteractionDirection.sent,
          );
      final items = page.items
          .map(profileInteractionActivityViewDataFromWire)
          .toList(growable: false);

      if (mounted) {
        setState(() {
          _items = items;
          _loading = false;
          _loadError = null;
        });
      }
    } catch (error, stackTrace) {
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stackTrace,
          library: 'profile interaction tab',
          context: ErrorDescription('loading profile interaction activities'),
        ),
      );
      if (mounted) {
        setState(() {
          _loading = false;
          _loadError = error;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    _scheduleReloadIfNeeded();
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final selectedFilterId = _interactionFilters
        .firstWhere(
          (filter) =>
              _interactionSubTabForId(filter.id) == widget.selectedSubTab,
          orElse: () => _interactionFilters.first,
        )
        .id;

    final header = KeyedSubtree(
      key: const ValueKey<String>('profile-interaction-secondary-tabs'),
      child: AppSecondaryTabBar(
        tabs: _interactionFilters
            .map(
              (filter) => AppSecondaryTabItem(
                id: filter.id,
                label: _secondaryTabLabel(filter),
              ),
            )
            .toList(growable: false),
        selectedId: selectedFilterId,
        onSelected: (id) =>
            widget.onSubTabSelected(_interactionSubTabForId(id)),
        isDark: widget.isDark,
        scrollKey: widget.secondaryTabBarKey,
        onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
        trailing:
            widget.mode == ProfileMode.mine &&
                widget.selectedSubTab == InteractionSubTab.shares
            ? ProfileInteractionDirectionSwitch(
                isDark: widget.isDark,
                current: widget.selectedDirection,
                onSelected: widget.onDirectionSelected,
              )
            : null,
      ),
    );

    final body =
        widget.selectedSubTab == InteractionSubTab.shares &&
            widget.mode == ProfileMode.mine
        ? widget.shareInteractionBuilder(
            direction: widget.selectedDirection == InteractionDirection.received
                ? ShareInteractionDirection.received
                : ShareInteractionDirection.initiated,
            personaId: widget.userId,
            inlineScroll: widget.inlineScroll,
          )
        : _loading
        ? AppRequestFeedback.section()
        : _loadError != null
        ? AppSectionErrorCard(
            semantic: runtimeErrorSemantic(
              context,
              error: _loadError!,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
              presentation: UiErrorPresentation.sectionSoftCard,
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                await _load();
              }
            },
          )
        : _items == null || _items!.isEmpty
        ? Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  _emptyStateIcon(widget.selectedSubTab),
                  size: AppSpacing.iconLarge,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  _emptyStateTitle(widget.selectedSubTab),
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          )
        : ListView.builder(
            physics: widget.inlineScroll
                ? const NeverScrollableScrollPhysics()
                : const BouncingScrollPhysics(
                    parent: AlwaysScrollableScrollPhysics(),
                  ),
            shrinkWrap: widget.inlineScroll,
            padding: EdgeInsets.only(
              top: AppSpacing.intraGroupSm,
              bottom: AppSpacing.containerMd,
            ),
            itemCount: _items!.length,
            itemBuilder: (context, i) {
              final item = _items![i];
              return _buildInteractionRow(
                context,
                item,
                direction: widget.selectedDirection,
                isLast: i == _items!.length - 1,
              );
            },
          );

    if (widget.inlineScroll) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          header,
          SizedBox(height: AppSpacing.intraGroupXs),
          body,
        ],
      );
    }

    return Column(
      children: [
        header,
        Expanded(child: body),
      ],
    );
  }

  String _secondaryTabLabel(UserProfileSubTabConfig filter) {
    return UITextConstants.contentLabelForKey(filter.labelKey);
  }

  Widget _buildInteractionRow(
    BuildContext context,
    ProfileInteractionActivityViewData item, {
    required InteractionDirection direction,
    required bool isLast,
  }) {
    final displayUserId = item.displayPersonaId;
    final displayName = item.displayName;
    final avatarUrl = resolveAvatarImageUrl(item.displayAvatarUrl);
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: widget.isDark ? 0.24 : 0.14);

    return Column(
      children: <Widget>[
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size(
                    AppSpacing.minInteractiveSize,
                    AppSpacing.minInteractiveSize,
                  ),
                  // 评论类互动：行主体点击深链进入评论详情并定位高亮目标评论；
                  // 其它互动（点赞/转发等）维持进入对方主页。
                  onPressed: () {
                    if (_isCommentActivity(item) &&
                        _previewObjectEnabled(item)) {
                      _pushPreviewObject(context, item);
                    } else {
                      _pushDisplayUser(context, item, avatarUrl);
                    }
                  },
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      vertical: AppSpacing.containerSm,
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        SizedBox.square(
                          dimension: AppSpacing.avatarUserMd,
                          child: ClipOval(
                            child: avatarUrl.isEmpty
                                ? ColoredBox(
                                    color: AppColors.iosFill(context),
                                    child: Icon(
                                      CupertinoIcons.person_crop_circle_fill,
                                      color: fgSecondary,
                                    ),
                                  )
                                : AppAvatarImage(
                                    imageUrl: avatarUrl,
                                    size: AppSpacing.avatarUserMd,
                                    errorWidget: ColoredBox(
                                      color: AppColors.iosFill(context),
                                      child: Icon(
                                        CupertinoIcons.person_crop_circle_fill,
                                        color: fgSecondary,
                                      ),
                                    ),
                                  ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.containerSm),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                displayName.isNotEmpty
                                    ? displayName
                                    : displayUserId,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosSubheadline,
                                  fontWeight: AppTypography.regular,
                                  color: fg,
                                  letterSpacing: -0.18,
                                ),
                              ),
                              if (item.primaryText.isNotEmpty) ...<Widget>[
                                SizedBox(height: AppSpacing.intraGroupXs),
                                Text(
                                  item.primaryText,
                                  style: TextStyle(
                                    fontSize: AppTypography.iosFootnote,
                                    fontWeight: AppTypography.regular,
                                    color: fg,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                              if (item.contextText.isNotEmpty) ...<Widget>[
                                SizedBox(height: AppSpacing.intraGroupXs),
                                Text(
                                  item.contextText,
                                  style: TextStyle(
                                    fontSize: AppTypography.iosCaption1,
                                    color: fgSecondary,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                              if (item.createdAt != null) ...<Widget>[
                                SizedBox(height: AppSpacing.intraGroupXs),
                                Text(
                                  _formatInteractionTime(item.createdAt!),
                                  style: TextStyle(
                                    fontSize: AppTypography.iosCaption2,
                                    color: AppColors.iosTertiaryLabel(context),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Padding(
                padding: EdgeInsets.only(top: AppSpacing.containerSm),
                child: _buildPreview(context, item),
              ),
            ],
          ),
        ),
        ..._buildInlineActionArea(context, item, direction: direction),
        if (!isLast)
          Padding(
            padding: EdgeInsets.only(
              left:
                  AppSpacing.containerMd +
                  AppSpacing.avatarUserMd +
                  AppSpacing.containerSm,
              right: AppSpacing.containerMd,
            ),
            child: Divider(
              height: AppSpacing.hairline,
              thickness: AppSpacing.hairline,
              color: separator,
            ),
          ),
      ],
    );
  }

  InteractionSubTab _interactionSubTabForId(String id) =>
      interactionSubTabFromId(id);

  IconData _emptyStateIcon(InteractionSubTab subTab) {
    switch (subTab) {
      case InteractionSubTab.likes:
        return CupertinoIcons.heart;
      case InteractionSubTab.comments:
        return CupertinoIcons.chat_bubble;
      case InteractionSubTab.shares:
        return CupertinoIcons.arrowshape_turn_up_right;
    }
  }

  String _emptyStateTitle(InteractionSubTab subTab) {
    switch (subTab) {
      case InteractionSubTab.likes:
        return ProfileText.profileInteractionEmptyLikes;
      case InteractionSubTab.comments:
        return ProfileText.profileInteractionEmptyComments;
      case InteractionSubTab.shares:
        return ProfileText.profileInteractionEmptyShares;
    }
  }

  Widget _buildPreview(
    BuildContext context,
    ProfileInteractionActivityViewData item,
  ) {
    final borderColor =
        SettingsSemanticConstants.conversationSheetCardBorderColor(
          widget.isDark,
        );
    final fill = AppColors.iosSecondaryFill(context);
    final previewEnabled = _previewObjectEnabled(item);
    final previewHeight = _interactionPreviewHeight(context, item);

    return CupertinoButton(
      key: ValueKey<String>(
        'profile-interaction-preview-button-${item.activityId}',
      ),
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
      onPressed: previewEnabled
          ? () => _pushPreviewObject(context, item)
          : null,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        child: Container(
          width: previewHeight * _previewAspectRatio,
          height: previewHeight,
          decoration: BoxDecoration(
            color: fill,
            border: Border.all(color: borderColor, width: AppSpacing.hairline),
            borderRadius: BorderRadius.circular(
              AppSpacing.contentPreviewCornerRadius,
            ),
          ),
          child: _ProfileInteractionPreviewTile(
            item: item,
            isDark: widget.isDark,
            backgroundColor: fill,
          ),
        ),
      ),
    );
  }

  double _interactionPreviewHeight(
    BuildContext context,
    ProfileInteractionActivityViewData item,
  ) {
    final textDirection = Directionality.of(context);
    double lineHeight(double fontSize) {
      final painter = TextPainter(
        text: TextSpan(
          text: 'Hg',
          style: TextStyle(fontSize: fontSize),
        ),
        textDirection: textDirection,
        maxLines: 1,
      )..layout();
      return painter.height;
    }

    var height = lineHeight(AppTypography.iosSubheadline);
    if (item.primaryText.isNotEmpty) {
      height += AppSpacing.intraGroupXs + lineHeight(AppTypography.iosFootnote);
    }
    if (item.contextText.isNotEmpty) {
      height += AppSpacing.intraGroupXs + lineHeight(AppTypography.iosCaption1);
    }
    if (item.createdAt != null) {
      height += AppSpacing.intraGroupXs + lineHeight(AppTypography.iosCaption2);
    }
    return height.clamp(AppSpacing.avatarUserLg, AppSpacing.avatarUserLg);
  }

  void _pushDisplayUser(
    BuildContext context,
    ProfileInteractionActivityViewData item,
    String resolvedAvatarUrl,
  ) {
    final userId = item.displayPersonaId.trim();
    if (item.displayUserRouteId != AppLinkTemplates.userRouteId ||
        userId.isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.userProfile(userHandle: userId),
      extra: UserProfileRouteExtra(
        personaId: userId,
        avatarUrl: resolvedAvatarUrl.isNotEmpty ? resolvedAvatarUrl : null,
        displayName: item.displayName.isNotEmpty ? item.displayName : null,
      ),
    );
  }

  void _pushPreviewObject(
    BuildContext context,
    ProfileInteractionActivityViewData item,
  ) {
    final objectId = item.previewObjectId.trim();
    if (item.previewRouteId != AppLinkTemplates.postRouteId ||
        objectId.isEmpty) {
      return;
    }
    final baseRoute = AppRoutePaths.workBrowser(
      workId: objectId,
      filter: _previewFilterFor(item),
      source: 'profile-interaction',
    );
    // 评论类互动：深链进入内容评论区并携带评论标识，
    // 落地后由分屏定位到「回复我的」那条（回复场景用父评论行高亮）。
    if (_isCommentActivity(item)) {
      final route = _commentActivityRoute(item);
      if (route == null) {
        return;
      }
      _trackCommentActivityDeeplink(item, postId: objectId);
      context.push(route);
      return;
    }
    context.push(baseRoute);
  }

  @override
  String? _commentActivityRoute(
    ProfileInteractionActivityViewData item, {
    bool replyToComment = false,
  }) {
    if (!_previewObjectEnabled(item)) {
      return null;
    }
    return buildProfileInteractionCommentRoute(
      workId: item.previewObjectId,
      filter: _previewFilterFor(item),
      source: 'profile-interaction',
      entrySource: MediaViewerCommentContext.entrySourceProfileInteraction,
      commentId: item.commentId,
      parentCommentId: item.parentCommentId,
      replyToCommentId: replyToComment ? item.commentId : null,
    );
  }

  @override
  void _trackCommentActivityDeeplink(
    ProfileInteractionActivityViewData item, {
    required String postId,
  }) {
    final commentId = item.commentId.trim();
    ref
        .read(commentObservabilityProvider)
        .trackAction(
          eventName: CommentEventNames.deeplinkOpened,
          postId: postId,
          commentId: commentId.isNotEmpty ? commentId : null,
          entrySource: MediaViewerCommentContext.entrySourceProfileInteraction,
          result: 'initiated',
        );
  }

  /// 该活动是否可深链进入内容（评论详情）：被评论内容存在且为 post 路由。
  bool _previewObjectEnabled(ProfileInteractionActivityViewData item) {
    return !item.previewUnavailable &&
        item.previewRouteId == AppLinkTemplates.postRouteId &&
        item.previewObjectId.trim().isNotEmpty;
  }

  String _previewFilterFor(ProfileInteractionActivityViewData item) {
    final kind = _normalizedPreviewKind(item);
    if (kind == _ProfilePreviewKind.video) {
      return 'video';
    }
    if (kind == _ProfilePreviewKind.article) {
      return 'article';
    }
    return 'image';
  }

  String _formatInteractionTime(DateTime value) {
    final local = value.toLocal();
    String twoDigits(int n) => n.toString().padLeft(2, '0');
    return '${twoDigits(local.month)}-${twoDigits(local.day)} ${twoDigits(local.hour)}:${twoDigits(local.minute)}';
  }

  void _scheduleReloadIfNeeded() {
    if (_loadedSubTab == widget.selectedSubTab &&
        _loadedDirection == widget.selectedDirection) {
      return;
    }
    _loadedSubTab = widget.selectedSubTab;
    _loadedDirection = widget.selectedDirection;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _load();
      }
    });
  }
}
