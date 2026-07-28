import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/discovery/services/home_feed_post_open_action.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';
import 'package:quwoquan_app/ui/interest_match/pages/interest_match_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

part 'web_main_app_shell_auth.dart';
part 'web_main_app_shell_state.dart';

class WebMainAppShell extends ConsumerStatefulWidget {
  const WebMainAppShell({
    super.key,
    required this.currentDestination,
    required this.currentLocation,
    required this.backgroundColor,
    required this.onPrimarySelected,
  });

  final MainTabDestination currentDestination;
  final String currentLocation;
  final Color backgroundColor;
  final ValueChanged<MainTabDestination> onPrimarySelected;

  @override
  ConsumerState<WebMainAppShell> createState() => _WebMainAppShellState();
}

class _WebToolbarHeaderDelegate extends SliverPersistentHeaderDelegate {
  const _WebToolbarHeaderDelegate({
    required this.child,
    required this.progress,
  });

  final Widget child;
  final double progress;

  @override
  double get minExtent => AppSpacing.webPcHeaderHeight;

  @override
  double get maxExtent => AppSpacing.webPcHeaderHeight;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    final showShadow = progress > AppSpacing.zero || overlapsContent;
    return DecoratedBox(
      decoration: BoxDecoration(
        boxShadow: showShadow
            ? const <BoxShadow>[
                BoxShadow(
                  color: AppColors.webPcToolbarShadow,
                  blurRadius: AppSpacing.webPcToolbarElevationBlurRadius,
                  offset: Offset(AppSpacing.zero, AppSpacing.two),
                ),
              ]
            : null,
      ),
      child: child,
    );
  }

  @override
  bool shouldRebuild(_WebToolbarHeaderDelegate oldDelegate) {
    return oldDelegate.child != child || oldDelegate.progress != progress;
  }
}

class _WebWelcomeHero extends StatelessWidget {
  const _WebWelcomeHero({required this.scrollProgress, required this.onEnter});

  final double scrollProgress;
  final VoidCallback onEnter;

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerSignal: (event) {
        if (event is PointerScrollEvent && event.scrollDelta.dy > 0) {
          onEnter();
        }
      },
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AppColors.worksBackground,
              AppColors.primaryColorActive,
              AppColors.worksBackground,
            ],
          ),
        ),
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xl,
              vertical: AppSpacing.sm,
            ),
            child: Center(
              child: Transform.translate(
                offset: Offset(
                  AppSpacing.zero,
                  -scrollProgress * AppSpacing.webPcHeroParallaxDistance,
                ),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.webContentMaxWidth,
                  ),
                  child: const _WebWelcomeBrand(),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _WebWelcomeBrand extends StatelessWidget {
  const _WebWelcomeBrand();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        const _WebWelcomeVisual(),
        const SizedBox(height: AppSpacing.xs),
        Text(
          DiscoveryText.webPcBrandName,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.iosCallout,
            fontWeight: AppTypography.black,
            height: AppTypography.lineHeightTight,
            letterSpacing: 0.4,
          ),
        ),
      ],
    );
  }
}

class _WebWelcomeVisual extends StatefulWidget {
  const _WebWelcomeVisual();

  @override
  State<_WebWelcomeVisual> createState() => _WebWelcomeVisualState();
}

class _WebWelcomeVisualState extends State<_WebWelcomeVisual>
    with TickerProviderStateMixin {
  static const Duration _petalDuration = Duration(milliseconds: 600);
  static const Duration _petalStagger = Duration(milliseconds: 35);
  static const double _initialPetalProgress = 0.72;

  late final List<AnimationController> _petalControllers;

  @override
  void initState() {
    super.initState();
    _petalControllers = List.generate(
      WelcomeFlowerMarkPainter.petalCount,
      (_) => AnimationController(
        vsync: this,
        duration: _petalDuration,
        value: _initialPetalProgress,
      ),
    );
    unawaited(_runBloom());
  }

  @override
  void dispose() {
    for (final controller in _petalControllers) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _runBloom() async {
    for (final controller in _petalControllers) {
      if (!mounted) return;
      controller.forward();
      await Future<void>.delayed(_petalStagger);
    }
  }

  @override
  Widget build(BuildContext context) {
    final appearance = WelcomeAppearance.of(context);
    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: AppSpacing.webPcWelcomeVisualDiameter,
          height: AppSpacing.webPcWelcomeVisualDiameter,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              colors: [
                AppColors.webPcWelcomeVisualGlowPrimary,
                AppColors.webPcWelcomeVisualGlowSecondary,
                AppColors.transparent,
              ],
            ),
          ),
        ),
        SizedBox.square(
          dimension: AppSpacing.webPcWelcomeVisualDiameter,
          child: FittedBox(
            child: SizedBox.square(
              dimension: AppSpacing.welcomeGraphicDiameter,
              child: AnimatedBuilder(
                animation: Listenable.merge(_petalControllers),
                builder: (context, child) {
                  return WelcomeFlowerMark(
                    appearance: appearance,
                    petalBloomAmounts: [
                      for (final controller in _petalControllers)
                        controller.value,
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _WebTopToolbar extends ConsumerWidget {
  const _WebTopToolbar({
    required this.destination,
    required this.toolbarProgress,
    required this.contextTabs,
    required this.activeContextId,
    required this.searchHint,
    required this.onContextTabSelected,
    required this.onPrimarySelected,
  });

  final MainTabDestination destination;
  final double toolbarProgress;
  final List<_WebContextTabSpec> contextTabs;
  final String activeContextId;
  final String searchHint;
  final ValueChanged<String> onContextTabSelected;
  final ValueChanged<MainTabDestination> onPrimarySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final background = AppColors.webPcToolbarSurface(context);
    final showBrand = toolbarProgress > 0.08;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        border: Border(
          bottom: BorderSide(color: AppColors.feedCardBorder(context)),
        ),
      ),
      child: SizedBox(
        height: AppSpacing.webPcHeaderHeight,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Row(
            children: [
              SizedBox(
                width: AppSpacing.webPcToolbarBrandSlotWidth,
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: AnimatedSwitcher(
                    duration: AppSpacing.webPcContextTabSwitchDuration,
                    child: showBrand
                        ? _WebBrandMark(
                            key: const ValueKey<String>('web-toolbar-brand'),
                            onDark: isDark,
                          )
                        : const SizedBox.shrink(
                            key: ValueKey<String>('web-toolbar-brand-hidden'),
                          ),
                  ),
                ),
              ),
              Expanded(
                child: _WebContextTabBar(
                  tabs: contextTabs,
                  activeId: activeContextId,
                  onSelected: onContextTabSelected,
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: AppSpacing.webPcSearchMaxWidth,
                  minWidth: AppSpacing.webPcSearchMinWidth,
                ),
                child: GlobalXiaoquSearchBar(
                  hint: searchHint,
                  initialSearchScope: GlobalSearchScope.all,
                  showAssistantLabel: false,
                  hintFontSize: AppTypography.webPcToolbarLabel,
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              _WebPrimaryActions(
                selected: destination,
                onSelected: onPrimarySelected,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WebBrandMark extends StatelessWidget {
  const _WebBrandMark({super.key, required this.onDark});

  final bool onDark;

  @override
  Widget build(BuildContext context) {
    final foreground = onDark ? AppColors.white : AppColors.iosLabel(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox.square(
          dimension: AppSpacing.webPcToolbarBrandIconSize,
          child: FittedBox(
            child: SizedBox.square(
              dimension: AppSpacing.welcomeGraphicDiameter,
              child: WelcomeFlowerMark(
                appearance: WelcomeAppearance.of(context),
              ),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(
          DiscoveryText.webPcBrandName,
          style: TextStyle(
            color: foreground,
            fontSize: AppTypography.webPcToolbarBrand,
            fontWeight: AppTypography.black,
            height: AppTypography.lineHeightTight,
          ),
        ),
      ],
    );
  }
}

class _WebContextTabBar extends StatelessWidget {
  const _WebContextTabBar({
    required this.tabs,
    required this.activeId,
    required this.onSelected,
  });

  final List<_WebContextTabSpec> tabs;
  final String activeId;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final tab in tabs)
            _WebContextTabChip(
              tab: tab,
              selected: tab.id == activeId,
              onTap: () => onSelected(tab.id),
            ),
        ],
      ),
    );
  }
}

class _WebContextTabChip extends StatelessWidget {
  const _WebContextTabChip({
    required this.tab,
    required this.selected,
    required this.onTap,
  });

  final _WebContextTabSpec tab;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? AppColors.primaryColor
        : AppColors.iosSecondaryLabel(context);
    return CupertinoButton(
      key: ValueKey<String>('web-context-tab-${tab.id}'),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      minimumSize: const Size(0, AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            tab.label,
            style: TextStyle(
              color: color,
              fontSize: AppTypography.webPcToolbarLabel,
              height: AppSpacing.textLineHeightDense,
              fontWeight: selected
                  ? AppTypography.semiBold
                  : AppTypography.medium,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          AnimatedContainer(
            duration: AppSpacing.webPcContextTabSwitchDuration,
            width: selected
                ? AppSpacing.webPcContextTabSelectedIndicatorWidth
                : AppSpacing.zero,
            height: AppSpacing.webPcContextTabIndicatorHeight,
            decoration: BoxDecoration(
              color: selected ? AppColors.primaryColor : AppColors.transparent,
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
            ),
          ),
        ],
      ),
    );
  }
}

class _WebPrimaryActions extends StatelessWidget {
  const _WebPrimaryActions({required this.selected, required this.onSelected});

  final MainTabDestination selected;
  final ValueChanged<MainTabDestination> onSelected;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _WebPrimaryActionButton(
          destination: MainTabDestination.home,
          label: DiscoveryText.webPcPrimaryHome,
          icon: CupertinoIcons.house,
          selected: selected == MainTabDestination.home,
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.featured,
          label: DiscoveryText.webPcPrimaryFeatured,
          selected: selected == MainTabDestination.featured,
          customIcon: (color, filled) => AppPremiumMarkIcon(
            size: AppSpacing.webPcToolbarActionIconSize,
            color: color,
            filled: filled,
          ),
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.create,
          label: DiscoveryText.webPcPrimaryCreate,
          icon: CupertinoIcons.plus,
          selected: selected == MainTabDestination.create,
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.chat,
          label: ChatText.webPcPrimaryMessages,
          selected: selected == MainTabDestination.chat,
          customIcon: (color, filled) => AppMessagesIcon(
            size: AppSpacing.webPcToolbarActionIconSize,
            color: color,
            backgroundColor: AppColors.iosGroupedSurface(context),
            filled: filled,
          ),
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.interestMatch,
          label: AppConceptConstants.interestMatch,
          icon: CupertinoIcons.person_2,
          selected: selected == MainTabDestination.interestMatch,
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.profile,
          label: DiscoveryText.webPcPrimaryProfile,
          icon: CupertinoIcons.person_crop_circle,
          selected: selected == MainTabDestination.profile,
          onTap: onSelected,
        ),
      ],
    );
  }
}

class _WebPrimaryActionButton extends StatelessWidget {
  const _WebPrimaryActionButton({
    required this.destination,
    required this.label,
    required this.selected,
    required this.onTap,
    this.icon,
    this.customIcon,
  });

  final MainTabDestination destination;
  final String label;
  final IconData? icon;
  final Widget Function(Color color, bool filled)? customIcon;
  final bool selected;
  final ValueChanged<MainTabDestination> onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? AppColors.primaryColor
        : AppColors.iosSecondaryLabel(context);
    final background = selected
        ? AppColors.webPcSelectedSurface
        : AppColors.transparent;
    return Padding(
      padding: const EdgeInsets.only(left: AppSpacing.xs),
      child: Semantics(
        button: true,
        selected: selected,
        label: label,
        child: CupertinoButton(
          key: ValueKey<String>('web-primary-${destination.routeName}'),
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.webPcToolbarActionSize),
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          color: background,
          onPressed: () => onTap(destination),
          child: SizedBox.square(
            dimension: AppSpacing.webPcToolbarActionSize,
            child: Center(
              child: customIcon != null
                  ? customIcon!(color, selected)
                  : Icon(
                      icon,
                      color: color,
                      size: AppSpacing.webPcToolbarActionIconSize,
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class _WebHomeWorkspace extends StatelessWidget {
  const _WebHomeWorkspace({required this.channelId});

  final String channelId;

  @override
  Widget build(BuildContext context) {
    return _WebDesktopFrame(
      child: _WebContentFeed(
        channelId: channelId,
        onInitialContentPainted: channelId == 'recommend'
            ? AppStartupRuntime.instance.markHomeFeedContentPainted
            : null,
      ),
    );
  }
}

class _WebFeaturedWorkspace extends StatelessWidget {
  const _WebFeaturedWorkspace({required this.filterId});

  final String filterId;

  @override
  Widget build(BuildContext context) {
    // 精品 = 发现内容流（不再有「精品队列」hero）；format 筛选映射到发现频道。
    final channelId = switch (filterId) {
      'image' => 'photo',
      'video' => 'video',
      'article' => 'article',
      _ => 'work',
    };
    return _WebDesktopFrame(child: _WebContentFeed(channelId: channelId));
  }
}

/// Web 宽屏内容流：复用移动端 [HomeMultiFormFeed]（多列瀑布 + 同源埋点 +
/// 四态），只在 Web 侧用主内容区宽度驱动列数，post 点击经统一动作进沉浸 viewer。
class _WebContentFeed extends ConsumerWidget {
  const _WebContentFeed({
    required this.channelId,
    this.onInitialContentPainted,
  });

  final String channelId;
  final VoidCallback? onInitialContentPainted;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final mediaQuery = MediaQuery.of(context);
        // 用主内容区宽度（而非整窗宽度）决定瀑布列数，避免卡片过窄。
        return MediaQuery(
          data: mediaQuery.copyWith(
            size: Size(constraints.maxWidth, mediaQuery.size.height),
          ),
          child: HomeMultiFormFeed(
            key: ValueKey<String>('web-content-feed-$channelId'),
            isDark: isDark,
            channelId: channelId,
            onInitialContentPainted: onInitialContentPainted,
            onUserTap:
                (
                  userId, {
                  String? avatarUrl,
                  String? displayName,
                  String? backgroundUrl,
                }) {
                  context.push(
                    AppRoutePaths.userProfile(username: userId),
                    extra: UserProfileRouteExtra(
                      subAccountId: userId,
                      avatar: avatarUrl,
                      displayName: displayName,
                      backgroundImage: backgroundUrl,
                    ),
                  );
                },
            onPostTap: (post, index, {feedPosts}) {
              unawaited(
                openHomeFeedPost(
                  context,
                  ref,
                  post: post,
                  mediaIndex: index,
                  feedPosts: feedPosts,
                ),
              );
            },
          ),
        );
      },
    );
  }
}

class _WebCreateWorkspace extends ConsumerWidget {
  const _WebCreateWorkspace({required this.activeTabId});

  final String activeTabId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final contentActions = <_CreateCardSpec>[
      _CreateCardSpec(
        id: 'album',
        icon: CupertinoIcons.photo_on_rectangle,
        title: DiscoveryText.webPcCreateGalleryTitle,
        subtitle: DiscoveryText.webPcCreateGallerySubtitle,
        action: () => _openCreate(context, EditorStartAction.gallery),
      ),
      _CreateCardSpec(
        id: 'camera',
        icon: CupertinoIcons.camera,
        title: DiscoveryText.webPcCreateCameraTitle,
        subtitle: DiscoveryText.webPcCreateCameraSubtitle,
        action: () => _openCreate(context, EditorStartAction.video),
      ),
      _CreateCardSpec(
        id: 'write',
        icon: CupertinoIcons.pencil_outline,
        title: DiscoveryText.webPcCreateTextTitle,
        subtitle: DiscoveryText.webPcCreateTextSubtitle,
        action: () => _openCreate(context, EditorStartAction.write),
      ),
    ];
    final socialActions = <_CreateCardSpec>[
      _CreateCardSpec(
        id: 'add-contact',
        icon: CupertinoIcons.person_badge_plus,
        title: DiscoveryText.webPcCreateAddContactTitle,
        subtitle: DiscoveryText.webPcCreateAddContactSubtitle,
        action: () => GlobalQuickActionSheet.openAddContact(context),
      ),
      _CreateCardSpec(
        id: 'group-chat',
        icon: CupertinoIcons.chat_bubble_2,
        title: ChatText.webPcCreateGroupChatTitle,
        subtitle: ChatText.webPcCreateGroupChatSubtitle,
        action: () => unawaited(
          GlobalQuickActionSheet.openGatedStartGroupChat(context, ref),
        ),
      ),
      _CreateCardSpec(
        id: 'create-circle',
        icon: CupertinoIcons.person_3,
        title: DiscoveryText.webPcCreateCircleTitle,
        subtitle: DiscoveryText.webPcCreateCircleSubtitle,
        action: () => GlobalQuickActionSheet.openCreateCircle(context),
      ),
    ];
    return _WebDesktopFrame(
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Text(
            DiscoveryText.webPcCreateWorkspaceTitle,
            style: TextStyle(
              fontSize: AppTypography.iosLargeTitle,
              fontWeight: AppTypography.black,
              color: AppColors.iosLabel(context),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            DiscoveryText.webPcCreateWorkspaceSubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosCallout,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          _WebCreateGroup(
            groupKey: const ValueKey<String>('web-create-group-content'),
            title: DiscoveryText.webPcCreateContentGroupTitle,
            cards: contentActions,
            activeTabId: activeTabId,
          ),
          const SizedBox(height: AppSpacing.xl),
          _WebCreateGroup(
            groupKey: const ValueKey<String>('web-create-group-social'),
            title: DiscoveryText.webPcCreateSocialGroupTitle,
            cards: socialActions,
            activeTabId: activeTabId,
          ),
        ],
      ),
    );
  }

  void _openCreate(
    BuildContext context,
    EditorStartAction action, {
    String? tab,
  }) {
    final queryParameters = <String, String>{'type': action.name};
    if (tab != null) {
      queryParameters['tab'] = tab;
    }
    final uri = Uri(
      path: AppRoutePaths.createPathTemplate,
      queryParameters: queryParameters,
    );
    context.go(uri.toString());
  }
}

class _WebCreateGroup extends StatelessWidget {
  const _WebCreateGroup({
    required this.groupKey,
    required this.title,
    required this.cards,
    required this.activeTabId,
  });

  final Key groupKey;
  final String title;
  final List<_CreateCardSpec> cards;
  final String activeTabId;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: groupKey,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: AppTypography.webPcSectionTitle,
            fontWeight: AppTypography.bold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Wrap(
          spacing: AppSpacing.md,
          runSpacing: AppSpacing.md,
          children: [
            for (final card in cards)
              SizedBox(
                width: AppSpacing.webPcCreateCardWidth,
                child: _CreateWorkspaceCard(
                  spec: card,
                  selected: card.id == activeTabId,
                ),
              ),
          ],
        ),
      ],
    );
  }
}

class _CreateWorkspaceCard extends StatelessWidget {
  const _CreateWorkspaceCard({required this.spec, required this.selected});

  final _CreateCardSpec spec;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: ValueKey<String>('web-create-card-${spec.id}'),
      padding: EdgeInsets.zero,
      onPressed: spec.action,
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.webPcCreateSelectedSurface
              : AppColors.iosGroupedSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: selected
                ? AppColors.primaryColor
                : AppColors.feedCardBorder(context),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(spec.icon, color: AppColors.primaryColor),
            const SizedBox(height: AppSpacing.md),
            Text(
              spec.title,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              spec.subtitle,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                height: AppSpacing.textLineHeightBody,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WebDesktopFrame extends StatelessWidget {
  const _WebDesktopFrame({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSpacing.webPcShellMaxWidth,
        ),
        child: child,
      ),
    );
  }
}
