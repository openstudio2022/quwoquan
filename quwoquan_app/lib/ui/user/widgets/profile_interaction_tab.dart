import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

class ProfileInteractionTab extends ConsumerStatefulWidget {
  const ProfileInteractionTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;

  @override
  ConsumerState<ProfileInteractionTab> createState() =>
      _ProfileInteractionTabState();
}

class _ProfileInteractionTabState extends ConsumerState<ProfileInteractionTab> {
  List<UserProfileSubTabConfig> get _interactionFilters =>
      UserProfileUIConfig.interactionSubTabs;

  List<ProfileInteractionActivityViewData>? _items;
  bool _loading = true;
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
    final repo = ref.read(userProfileRepositoryProvider);
    setState(() => _loading = true);
    try {
      final list = direction == InteractionDirection.received
          ? await repo.listProfileInteractionReceivedView(widget.userId)
          : await repo.listProfileInteractionSentView(widget.userId);

      final filterKey = subTab.id;
      final filtered = list
          .where((item) {
            return item.filterKeys
                .map((key) => key.trim())
                .where((key) => key.isNotEmpty)
                .contains(filterKey);
          })
          .toList(growable: false);

      if (mounted) {
        setState(() {
          _items = filtered;
          _loading = false;
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
          _items = [];
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
    _scheduleReloadIfNeeded(state);
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final activeIndex = _interactionFilters.indexWhere(
      (filter) => _interactionSubTabForId(filter.id) == state.interactionSubTab,
    );

    final header = Container(
      key: const ValueKey<String>('profile-interaction-secondary-tabs'),
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.intraGroupXs,
        AppSpacing.containerMd,
        AppSpacing.intraGroupXs,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
              child: SingleChildScrollView(
                key: widget.secondaryTabBarKey,
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                child: Row(
                  children: List<Widget>.generate(_interactionFilters.length, (
                    index,
                  ) {
                    final selected =
                        (activeIndex < 0 ? 0 : activeIndex) == index;
                    final label = UITextConstants.contentLabelForKey(
                      _interactionFilters[index].labelKey,
                    );
                    return Padding(
                      padding: EdgeInsets.only(
                        right: index == _interactionFilters.length - 1
                            ? AppSpacing.zero
                            : AppSpacing.intraGroupSm,
                      ),
                      child: CupertinoButton(
                        minimumSize: const Size(
                          AppSpacing.minInteractiveSize,
                          AppSpacing.minInteractiveSize,
                        ),
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          notifier.setInteractionSubTab(
                            _interactionSubTabForId(
                              _interactionFilters[index].id,
                            ),
                          );
                        },
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          curve: Curves.easeOutCubic,
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.containerSm,
                            vertical: AppSpacing.intraGroupXs,
                          ),
                          decoration: BoxDecoration(
                            color: selected
                                ? AppColors.iosTintedFill(context)
                                : AppColors.transparent,
                            borderRadius: BorderRadius.circular(
                              AppSpacing.radiusNinetyNine,
                            ),
                            border: selected
                                ? Border.all(
                                    color: AppColors.iosAccent(context)
                                        .withValues(
                                          alpha: widget.isDark ? 0.34 : 0.20,
                                        ),
                                    width: AppSpacing.hairline,
                                  )
                                : null,
                          ),
                          child: Text(
                            label,
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption1,
                              fontWeight: selected
                                  ? AppTypography.semiBold
                                  : AppTypography.medium,
                              color: selected
                                  ? AppColors.iosAccent(context)
                                  : fgSecondary,
                              letterSpacing: -0.08,
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                ),
              ),
            ),
          ),
          if (widget.mode == ProfileMode.mine)
            CupertinoButton(
              key: const ValueKey<String>(
                'profile-interaction-direction-entry',
              ),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              padding: EdgeInsets.only(left: AppSpacing.containerSm),
              onPressed: () => _showDirectionSheet(
                context,
                state.interactionDirection,
                notifier,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    _directionLabel(state.interactionDirection),
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      fontWeight: AppTypography.semiBold,
                      color: fg,
                      letterSpacing: -0.08,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  Icon(
                    CupertinoIcons.chevron_down,
                    size: AppSpacing.iconSmall,
                    color: fgSecondary,
                  ),
                ],
              ),
            ),
        ],
      ),
    );

    final body = _loading
        ? Center(child: CupertinoActivityIndicator())
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
            itemBuilder: (context, i) => _buildInteractionRow(
              context,
              _items![i],
              isLast: i == _items!.length - 1,
            ),
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

  Widget _buildInteractionRow(
    BuildContext context,
    ProfileInteractionActivityViewData item, {
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
                  onPressed: () {
                    _pushDisplayUser(context, item, avatarUrl);
                  },
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      vertical: AppSpacing.containerSm,
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        CircleAvatar(
                          radius: AppSpacing.avatarUserMd / 2,
                          backgroundImage: avatarUrl.isNotEmpty
                              ? NetworkImage(avatarUrl)
                              : null,
                          backgroundColor: AppColors.iosFill(context),
                          child: avatarUrl.isEmpty
                              ? Icon(
                                  CupertinoIcons.person_crop_circle_fill,
                                  color: fgSecondary,
                                )
                              : null,
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
                                  fontWeight: AppTypography.semiBold,
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
      case InteractionSubTab.all:
        return CupertinoIcons.bell;
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
      case InteractionSubTab.all:
        return UITextConstants.profileInteractionEmpty;
      case InteractionSubTab.likes:
        return UITextConstants.profileInteractionEmptyLikes;
      case InteractionSubTab.comments:
        return UITextConstants.profileInteractionEmptyComments;
      case InteractionSubTab.shares:
        return UITextConstants.profileInteractionEmptyShares;
    }
  }

  String _directionLabel(InteractionDirection direction) {
    switch (direction) {
      case InteractionDirection.received:
        return UITextConstants.profileInteractionDirectionReceived;
      case InteractionDirection.sent:
        return UITextConstants.profileInteractionDirectionSent;
    }
  }

  Future<void> _showDirectionSheet(
    BuildContext context,
    InteractionDirection current,
    ProfileNotifier notifier,
  ) async {
    final selected = await showAppActionSheet<InteractionDirection>(
      context,
      title: UITextConstants.profileInteractionDirectionTitle,
      sections: <AppActionSheetSection<InteractionDirection>>[
        AppActionSheetSection<InteractionDirection>(
          items: <AppActionSheetItem<InteractionDirection>>[
            AppActionSheetItem<InteractionDirection>(
              label: UITextConstants.profileInteractionDirectionReceived,
              value: InteractionDirection.received,
              icon: CupertinoIcons.tray_arrow_down,
              isSelected: current == InteractionDirection.received,
            ),
            AppActionSheetItem<InteractionDirection>(
              label: UITextConstants.profileInteractionDirectionSent,
              value: InteractionDirection.sent,
              icon: CupertinoIcons.paperplane,
              isSelected: current == InteractionDirection.sent,
            ),
          ],
        ),
      ],
    );
    if (selected != null) {
      notifier.setInteractionDirection(selected);
    }
  }

  Widget _buildPreview(
    BuildContext context,
    ProfileInteractionActivityViewData item,
  ) {
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final borderColor =
        SettingsSemanticConstants.conversationSheetCardBorderColor(
          widget.isDark,
        );
    final fill = AppColors.iosSecondaryFill(context);
    final previewKind = item.previewMediaKind.trim().toLowerCase();
    final imageUrl = resolveContentMediaUrl(item.previewImageUrl);
    final previewText = item.previewText.trim();
    final previewEnabled =
        !item.previewUnavailable &&
        item.previewRouteId == AppLinkTemplates.postRouteId &&
        item.previewObjectId.trim().isNotEmpty;
    final previewChild = item.previewUnavailable
        ? _buildPreviewPlaceholder(
            context,
            CupertinoIcons.doc_text,
            UITextConstants.profileInteractionOriginalUnavailable,
          )
        : (previewKind == 'image' || previewKind == 'video') &&
              imageUrl.isNotEmpty
        ? Stack(
            fit: StackFit.expand,
            children: <Widget>[
              Image.network(
                imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, error, stackTrace) =>
                    _buildPreviewPlaceholder(
                      context,
                      CupertinoIcons.photo,
                      UITextConstants.profileInteractionPreviewUnavailable,
                    ),
              ),
              if (previewKind == 'video')
                Center(
                  child: Icon(
                    CupertinoIcons.play_circle_fill,
                    size: AppSpacing.iconMedium,
                    color: AppColors.white.withValues(alpha: 0.92),
                  ),
                ),
            ],
          )
        : previewKind == 'video'
        ? Stack(
            fit: StackFit.expand,
            children: <Widget>[
              _buildPreviewPlaceholder(
                context,
                CupertinoIcons.play_rectangle,
                UITextConstants.profileInteractionPreviewUnavailable,
              ),
              Center(
                child: Icon(
                  CupertinoIcons.play_circle_fill,
                  size: AppSpacing.iconMedium,
                  color: fgSecondary,
                ),
              ),
            ],
          )
        : previewText.isNotEmpty
        ? Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: Text(
                previewText,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption2,
                  color: fg,
                  height: AppTypography.lineHeightTight,
                ),
              ),
            ),
          )
        : _buildPreviewPlaceholder(
            context,
            CupertinoIcons.doc_text,
            UITextConstants.profileInteractionPreviewUnavailable,
          );

    return CupertinoButton(
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
          width: AppSpacing.avatarUserXl,
          height: AppSpacing.avatarUserLg,
          decoration: BoxDecoration(
            color: fill,
            border: Border.all(color: borderColor, width: AppSpacing.hairline),
            borderRadius: BorderRadius.circular(
              AppSpacing.contentPreviewCornerRadius,
            ),
          ),
          child: previewChild,
        ),
      ),
    );
  }

  Widget _buildPreviewPlaceholder(
    BuildContext context,
    IconData icon,
    String label,
  ) {
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupSm),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Icon(icon, size: AppSpacing.iconSmall, color: fgSecondary),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption2,
              color: fgSecondary,
              height: AppTypography.lineHeightTight,
            ),
          ),
        ],
      ),
    );
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
    context.push(
      AppRoutePaths.workBrowser(
        workId: objectId,
        source: 'profile-interaction',
      ),
    );
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
