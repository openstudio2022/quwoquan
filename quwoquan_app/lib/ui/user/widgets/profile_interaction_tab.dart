import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_interaction_list.dart';
import 'package:quwoquan_app/ui/user/utils/profile_comment_detail_route.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'profile_interaction_tab_widgets.dart';
part 'profile_interaction_tab_inline_actions.dart';

class ProfileInteractionTab extends ConsumerStatefulWidget {
  const ProfileInteractionTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
    this.onDirectionSelected,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;
  final ValueChanged<InteractionDirection>? onDirectionSelected;

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
    final state = ref.read(profileNotifierProvider(widget.userId));
    _loadedSubTab = state.interactionSubTab;
    _loadedDirection = state.interactionDirection;
    _load();
  }

  Future<void> _load() async {
    final profileState = ref.read(profileNotifierProvider(widget.userId));
    final direction = profileState.interactionDirection;
    final subTab = profileState.interactionSubTab;
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
              subAccountId: widget.userId,
              type: switch (subTab) {
                InteractionSubTab.likes => ContentProfileInteractionType.like,
                InteractionSubTab.comments =>
                  ContentProfileInteractionType.comment,
                InteractionSubTab.shares => ContentProfileInteractionType.share,
              },
            ),
            direction: direction == InteractionDirection.received
                ? ContentProfileInteractionDirection.received
                : ContentProfileInteractionDirection.sent,
          );
      final items = page.items
          .map(ProfileInteractionActivityViewData.fromContentActivity)
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
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
    _scheduleReloadIfNeeded(state);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final selectedFilterId = _interactionFilters
        .firstWhere(
          (filter) =>
              _interactionSubTabForId(filter.id) == state.interactionSubTab,
          orElse: () => _interactionFilters.first,
        )
        .id;

    final header = KeyedSubtree(
      key: const ValueKey<String>('profile-interaction-secondary-tabs'),
      child: ProfileSecondaryTabBar(
        tabs: _interactionFilters
            .map(
              (filter) => ProfileSecondaryTabItem(
                id: filter.id,
                label: _secondaryTabLabel(filter),
              ),
            )
            .toList(growable: false),
        selectedId: selectedFilterId,
        onSelected: (id) =>
            notifier.setInteractionSubTab(_interactionSubTabForId(id)),
        isDark: widget.isDark,
        scrollKey: widget.secondaryTabBarKey,
        onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
        trailing:
            widget.mode == ProfileMode.mine &&
                state.interactionSubTab == InteractionSubTab.shares
            ? ProfileInteractionDirectionSwitch(
                isDark: widget.isDark,
                current: state.interactionDirection,
                onSelected: (direction) {
                  final callback = widget.onDirectionSelected;
                  if (callback != null) {
                    callback(direction);
                  } else {
                    notifier.setInteractionDirection(direction);
                  }
                },
              )
            : null,
      ),
    );

    final body =
        state.interactionSubTab == InteractionSubTab.shares &&
            widget.mode == ProfileMode.mine
        ? ShareInteractionList(
            direction:
                state.interactionDirection == InteractionDirection.received
                ? ShareInteractionDirection.received
                : ShareInteractionDirection.initiated,
            subAccountId: widget.userId,
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
                  _emptyStateIcon(state.interactionSubTab),
                  size: AppSpacing.iconLarge,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  _emptyStateTitle(state.interactionSubTab),
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
                direction: state.interactionDirection,
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
    final displayUserId = item.displaySubAccountId;
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
    final userId = item.displaySubAccountId.trim();
    if (item.displayUserRouteId != AppLinkTemplates.userRouteId ||
        userId.isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.userProfile(username: userId),
      extra: UserProfileRouteExtra(
        subAccountId: userId,
        avatar: resolvedAvatarUrl.isNotEmpty ? resolvedAvatarUrl : null,
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
    return buildProfileCommentDetailRoute(
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

  void _scheduleReloadIfNeeded(ProfileState state) {
    if (_loadedSubTab == state.interactionSubTab &&
        _loadedDirection == state.interactionDirection) {
      return;
    }
    _loadedSubTab = state.interactionSubTab;
    _loadedDirection = state.interactionDirection;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _load();
      }
    });
  }
}
