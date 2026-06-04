import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

class WebMainAppShell extends ConsumerStatefulWidget {
  const WebMainAppShell({
    super.key,
    required this.currentDestination,
    required this.currentLocation,
    required this.backgroundColor,
    required this.onPrimarySelected,
    required this.onOpenCreateSheet,
  });

  final MainTabDestination currentDestination;
  final String currentLocation;
  final Color backgroundColor;
  final ValueChanged<MainTabDestination> onPrimarySelected;
  final VoidCallback onOpenCreateSheet;

  @override
  ConsumerState<WebMainAppShell> createState() => _WebMainAppShellState();
}

class _WebMainAppShellState extends ConsumerState<WebMainAppShell> {
  static const String _defaultHomeChannelId = 'recommend';
  static const String _defaultFeaturedFilterId = 'all';
  static const String _defaultCreateTabId = 'gallery';
  static const String _defaultMessageTabId = 'messages';
  static const String _profileContextId = 'profile';

  final ScrollController _scrollController = ScrollController();
  String _homeChannelId = _defaultHomeChannelId;
  String _featuredFilterId = _defaultFeaturedFilterId;
  String _createTabId = _defaultCreateTabId;
  String _messageTabId = _defaultMessageTabId;
  double _toolbarProgress = 0;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScroll);
  }

  @override
  void didUpdateWidget(WebMainAppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentLocation != widget.currentLocation) {
      final destination = mainTabFromLocation(widget.currentLocation);
      if (destination == MainTabDestination.home) {
        _homeChannelId = _defaultHomeChannelId;
      }
    }
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_handleScroll)
      ..dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final destination = widget.currentDestination;
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(color: widget.backgroundColor),
        child: LayoutBuilder(
          builder: (context, constraints) {
            const heroHeight = AppSpacing.webPcWelcomeHeroHeight;
            return CustomScrollView(
              controller: _scrollController,
              slivers: [
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: heroHeight,
                    child: _WebWelcomeHero(
                      scrollProgress: _toolbarProgress,
                      onEnter: () => _enterWebHome(heroHeight),
                    ),
                  ),
                ),
                SliverPersistentHeader(
                  pinned: true,
                  delegate: _WebToolbarHeaderDelegate(
                    progress: _toolbarProgress,
                    child: SafeArea(
                      top: false,
                      bottom: false,
                      child: _WebTopToolbar(
                        destination: destination,
                        toolbarProgress: _toolbarProgress,
                        contextTabs: _contextTabsFor(destination),
                        activeContextId: _activeContextIdFor(destination),
                        searchHint: _searchHintFor(destination),
                        onContextTabSelected: (id) =>
                            _selectContext(destination, id),
                        onPrimarySelected: _selectPrimary,
                      ),
                    ),
                  ),
                ),
                SliverFillRemaining(
                  hasScrollBody: true,
                  child: _buildContent(destination),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  void _handleScroll() {
    if (!_scrollController.hasClients) {
      return;
    }
    final nextProgress =
        (_scrollController.offset / AppSpacing.webPcHeroPinnedProgressDistance)
            .clamp(0.0, 1.0)
            .toDouble();
    if ((nextProgress - _toolbarProgress).abs() < 0.01) {
      return;
    }
    setState(() {
      _toolbarProgress = nextProgress;
    });
  }

  void _enterWebHome(double heroHeight) {
    unawaited(
      _scrollController.animateTo(
        heroHeight,
        duration: AppSpacing.webPcScrollToContentDuration,
        curve: Curves.easeOutCubic,
      ),
    );
    _selectPrimary(MainTabDestination.home);
  }

  void _selectPrimary(MainTabDestination destination) {
    widget.onPrimarySelected(destination);
  }

  List<_WebContextTabSpec> _contextTabsFor(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return ref
            .watch(homeChannelsProvider)
            .map(
              (channel) => _WebContextTabSpec(
                id: channel.id,
                label: UITextConstants.homeChannelLabel(channel.labelKey),
              ),
            )
            .toList(growable: false);
      case MainTabDestination.featured:
        return ContentUIConfig.workFormatFilters
            .map(
              (filter) => _WebContextTabSpec(
                id: filter.id,
                label: UITextConstants.contentLabelForKey(filter.labelKey),
              ),
            )
            .toList(growable: false);
      case MainTabDestination.create:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: 'video',
            label: UITextConstants.webPcCreateTabVideo,
          ),
          _WebContextTabSpec(
            id: 'gallery',
            label: UITextConstants.webPcCreateTabGallery,
          ),
          _WebContextTabSpec(
            id: 'write',
            label: UITextConstants.webPcCreateTabText,
          ),
          _WebContextTabSpec(
            id: 'drafts',
            label: UITextConstants.webPcCreateTabDrafts,
          ),
        ];
      case MainTabDestination.chat:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: 'messages',
            label: UITextConstants.webPcMessagesTabMessages,
          ),
          _WebContextTabSpec(
            id: 'contacts',
            label: UITextConstants.webPcMessagesTabContacts,
          ),
          _WebContextTabSpec(
            id: 'groups',
            label: UITextConstants.webPcMessagesTabGroups,
          ),
          _WebContextTabSpec(
            id: 'xiaoqu',
            label: UITextConstants.webPcMessagesTabXiaoqu,
          ),
        ];
      case MainTabDestination.profile:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: _profileContextId,
            label: UITextConstants.webPcProfileContextTitle,
          ),
        ];
    }
  }

  String _activeContextIdFor(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return _homeChannelId;
      case MainTabDestination.featured:
        return _featuredFilterId;
      case MainTabDestination.create:
        return _createTabId;
      case MainTabDestination.chat:
        return _messageTabId;
      case MainTabDestination.profile:
        return _profileContextId;
    }
  }

  String _searchHintFor(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return UITextConstants.webPcSearchHintHome;
      case MainTabDestination.featured:
        return UITextConstants.webPcSearchHintFeatured;
      case MainTabDestination.create:
        return UITextConstants.webPcSearchHintCreate;
      case MainTabDestination.chat:
        return UITextConstants.webPcSearchHintMessages;
      case MainTabDestination.profile:
        return UITextConstants.webPcSearchHintProfile;
    }
  }

  void _selectContext(MainTabDestination destination, String id) {
    setState(() {
      switch (destination) {
        case MainTabDestination.home:
          _homeChannelId = id;
          break;
        case MainTabDestination.featured:
          _featuredFilterId = id;
          break;
        case MainTabDestination.create:
          _createTabId = id;
          break;
        case MainTabDestination.chat:
          _messageTabId = id;
          break;
        case MainTabDestination.profile:
          break;
      }
    });
  }

  Widget _buildContent(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return _WebHomeWorkspace(channelId: _homeChannelId);
      case MainTabDestination.featured:
        return _WebFeaturedWorkspace(filterId: _featuredFilterId);
      case MainTabDestination.create:
        return _WebCreateWorkspace(
          activeTabId: _createTabId,
          onOpenCreateSheet: widget.onOpenCreateSheet,
        );
      case MainTabDestination.chat:
        return _WebDesktopFrame(
          rightRail: const _WebInfoRail(
            title: UITextConstants.webPcMessagesRailTitle,
            body: UITextConstants.webPcMessagesRailBody,
          ),
          child: const ChatPage(),
        );
      case MainTabDestination.profile:
        return _WebDesktopFrame(
          rightRail: const _WebInfoRail(
            title: UITextConstants.webPcProfileRailTitle,
            body: UITextConstants.webPcProfileRailBody,
          ),
          child: const MyProfilePage(),
        );
    }
  }
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
          UITextConstants.webPcBrandName,
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
                    petalProgresses: [
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
              AnimatedSwitcher(
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
              if (showBrand) const SizedBox(width: AppSpacing.lg),
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
        Icon(
          CupertinoIcons.camera,
          color: AppColors.primaryColor,
          size: AppSpacing.twenty,
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(
          UITextConstants.webPcBrandName,
          style: TextStyle(
            color: foreground,
            fontSize: AppTypography.xl,
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
              fontSize: AppTypography.iosSubheadline,
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
          label: UITextConstants.webPcPrimaryHome,
          icon: CupertinoIcons.house,
          selected: selected == MainTabDestination.home,
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.featured,
          label: UITextConstants.webPcPrimaryFeatured,
          selected: selected == MainTabDestination.featured,
          customIcon: (color, filled) => AppPremiumMarkIcon(
            size: AppSpacing.twenty,
            color: color,
            filled: filled,
          ),
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.create,
          label: UITextConstants.webPcPrimaryCreate,
          icon: CupertinoIcons.plus,
          selected: selected == MainTabDestination.create,
          emphasized: true,
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.chat,
          label: UITextConstants.webPcPrimaryMessages,
          selected: selected == MainTabDestination.chat,
          customIcon: (color, filled) => AppMessagesIcon(
            size: AppSpacing.twenty,
            color: color,
            backgroundColor: AppColors.iosGroupedSurface(context),
            filled: filled,
          ),
          onTap: onSelected,
        ),
        _WebPrimaryActionButton(
          destination: MainTabDestination.profile,
          label: UITextConstants.webPcPrimaryProfile,
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
    this.emphasized = false,
  });

  final MainTabDestination destination;
  final String label;
  final IconData? icon;
  final Widget Function(Color color, bool filled)? customIcon;
  final bool selected;
  final bool emphasized;
  final ValueChanged<MainTabDestination> onTap;

  @override
  Widget build(BuildContext context) {
    final color = emphasized
        ? AppColors.white
        : (selected
              ? AppColors.primaryColor
              : AppColors.iosSecondaryLabel(context));
    final background = emphasized
        ? AppColors.primaryColor
        : (selected ? AppColors.webPcSelectedSurface : AppColors.transparent);
    return Padding(
      padding: const EdgeInsets.only(left: AppSpacing.xs),
      child: Semantics(
        button: true,
        selected: selected,
        label: label,
        child: CupertinoButton(
          key: ValueKey<String>('web-primary-${destination.routeName}'),
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.minInteractiveSize),
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          color: background,
          onPressed: () => onTap(destination),
          child: SizedBox.square(
            dimension: AppSpacing.minInteractiveSize,
            child: Center(
              child: customIcon != null
                  ? customIcon!(color, selected)
                  : Icon(icon, color: color, size: AppSpacing.twenty),
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
      rightRail: const _WebInfoRail(
        title: UITextConstants.webPcHomeRailTitle,
        body: UITextConstants.webPcHomeRailBody,
      ),
      child: _WebFeedSection(
        channelId: channelId,
        title: UITextConstants.webPcHomeFeedTitle,
      ),
    );
  }
}

class _WebFeaturedWorkspace extends StatelessWidget {
  const _WebFeaturedWorkspace({required this.filterId});

  final String filterId;

  @override
  Widget build(BuildContext context) {
    final channelId = switch (filterId) {
      'image' => 'photo',
      'video' => 'video',
      'note' => 'article',
      _ => 'work',
    };
    return _WebDesktopFrame(
      rightRail: const _WebInfoRail(
        title: UITextConstants.webPcFeaturedRailTitle,
        body: UITextConstants.webPcFeaturedRailBody,
      ),
      child: _WebFeedSection(
        channelId: channelId,
        title: UITextConstants.webPcFeaturedFeedTitle,
      ),
    );
  }
}

class _WebCreateWorkspace extends StatelessWidget {
  const _WebCreateWorkspace({
    required this.activeTabId,
    required this.onOpenCreateSheet,
  });

  final String activeTabId;
  final VoidCallback onOpenCreateSheet;

  @override
  Widget build(BuildContext context) {
    final cards = <_CreateCardSpec>[
      _CreateCardSpec(
        id: 'video',
        title: UITextConstants.webPcCreateVideoTitle,
        subtitle: UITextConstants.webPcCreateVideoSubtitle,
        action: () =>
            _openCreate(context, EditorStartAction.gallery, tab: 'video'),
      ),
      _CreateCardSpec(
        id: 'gallery',
        title: UITextConstants.webPcCreateGalleryTitle,
        subtitle: UITextConstants.webPcCreateGallerySubtitle,
        action: () => _openCreate(context, EditorStartAction.gallery),
      ),
      _CreateCardSpec(
        id: 'write',
        title: UITextConstants.webPcCreateTextTitle,
        subtitle: UITextConstants.webPcCreateTextSubtitle,
        action: () => _openCreate(context, EditorStartAction.write),
      ),
      _CreateCardSpec(
        id: 'drafts',
        title: UITextConstants.webPcCreateDraftsTitle,
        subtitle: UITextConstants.webPcCreateDraftsSubtitle,
        action: onOpenCreateSheet,
      ),
    ];
    return _WebDesktopFrame(
      rightRail: const _WebInfoRail(
        title: UITextConstants.webPcCreateRailTitle,
        body: UITextConstants.webPcCreateRailBody,
      ),
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Text(
            UITextConstants.webPcCreateWorkspaceTitle,
            style: TextStyle(
              fontSize: AppTypography.iosLargeTitle,
              fontWeight: AppTypography.black,
              color: AppColors.iosLabel(context),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.webPcCreateWorkspaceSubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosCallout,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
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

class _CreateWorkspaceCard extends StatelessWidget {
  const _CreateWorkspaceCard({required this.spec, required this.selected});

  final _CreateCardSpec spec;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
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
            Icon(CupertinoIcons.plus_app, color: AppColors.primaryColor),
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
  const _WebDesktopFrame({required this.child, required this.rightRail});

  final Widget child;
  final Widget rightRail;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSpacing.webPcShellMaxWidth,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(child: child),
            const SizedBox(width: AppSpacing.md),
            SizedBox(
              width: AppSpacing.webPcRightRailWidth,
              child: Padding(
                padding: const EdgeInsets.only(
                  top: AppSpacing.lg,
                  right: AppSpacing.lg,
                  bottom: AppSpacing.lg,
                ),
                child: rightRail,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WebFeedSection extends ConsumerStatefulWidget {
  const _WebFeedSection({required this.channelId, required this.title});

  final String channelId;
  final String title;

  @override
  ConsumerState<_WebFeedSection> createState() => _WebFeedSectionState();
}

class _WebFeedSectionState extends ConsumerState<_WebFeedSection> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(
        ref.read(discoveryFeedMapProvider.notifier).load(widget.channelId),
      );
    });
  }

  @override
  void didUpdateWidget(_WebFeedSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.channelId == widget.channelId) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(
        ref.read(discoveryFeedMapProvider.notifier).load(widget.channelId),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final value = ref.watch(discoveryFeedMapProvider)[widget.channelId];
    final state = value?.value;
    final items = state?.items ?? const <PostBaseDto>[];
    if (value == null || value.isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state?.errorMessage != null && items.isEmpty) {
      return Center(child: Text(state!.errorMessage!));
    }
    if (items.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.webPcFeedEmpty,
          style: TextStyle(color: AppColors.iosSecondaryLabel(context)),
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Text(
          widget.title,
          style: TextStyle(
            fontSize: AppTypography.iosLargeTitle,
            fontWeight: AppTypography.black,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        _WebHeroPostCard(post: items.first),
        const SizedBox(height: AppSpacing.lg),
        Wrap(
          spacing: AppSpacing.md,
          runSpacing: AppSpacing.md,
          children: [
            for (final post
                in items.skip(1).take(AppSpacing.webPcFeedPreviewItemLimit))
              SizedBox(
                width: AppSpacing.webPcFeedCardWidth,
                child: _WebPostCard(post: post),
              ),
          ],
        ),
      ],
    );
  }
}

class _WebHeroPostCard extends StatelessWidget {
  const _WebHeroPostCard({required this.post});

  final PostBaseDto post;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: AppSpacing.webPcHeroCardHeight,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        color: AppColors.iosGroupedSurface(context),
        border: Border.all(color: AppColors.feedCardBorder(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Row(
        children: [
          Expanded(flex: 3, child: _PostVisual(url: post.primaryVisualUrl)),
          Expanded(
            flex: 2,
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.xl),
              child: _PostCopy(post: post, hero: true),
            ),
          ),
        ],
      ),
    );
  }
}

class _WebPostCard extends StatelessWidget {
  const _WebPostCard({required this.post});

  final PostBaseDto post;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: AppColors.feedCardBorder(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: AppSpacing.webPcFeedCardImageHeight,
            child: _PostVisual(url: post.primaryVisualUrl),
          ),
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: _PostCopy(post: post),
          ),
        ],
      ),
    );
  }
}

class _PostVisual extends StatefulWidget {
  const _PostVisual({required this.url});

  final String url;

  @override
  State<_PostVisual> createState() => _PostVisualState();
}

class _PostVisualState extends State<_PostVisual> {
  @override
  Widget build(BuildContext context) {
    final resolvedCandidates = resolveContentMediaUrlCandidates(widget.url);
    if (resolvedCandidates.isEmpty) {
      return const DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              AppColors.webPcMediaFallbackGradientTop,
              AppColors.webPcMediaFallbackGradientBottom,
            ],
          ),
        ),
        child: Center(child: Icon(CupertinoIcons.sparkles)),
      );
    }
    return AppCachedNetworkImage(
      imageUrl: resolvedCandidates.first,
      imageUrlCandidates: resolvedCandidates,
      key: ValueKey<String>('web-post-visual-${resolvedCandidates.first}'),
      fit: BoxFit.cover,
      placeholder: const DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              AppColors.webPcMediaFallbackGradientTop,
              AppColors.webPcMediaFallbackGradientBottom,
            ],
          ),
        ),
        child: Center(child: CupertinoActivityIndicator()),
      ),
      errorWidget: const DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              AppColors.webPcMediaFallbackGradientTop,
              AppColors.webPcMediaFallbackGradientBottom,
            ],
          ),
        ),
        child: Center(child: Icon(CupertinoIcons.photo)),
      ),
    );
  }
}

class _PostCopy extends StatelessWidget {
  const _PostCopy({required this.post, this.hero = false});

  final PostBaseDto post;
  final bool hero;

  @override
  Widget build(BuildContext context) {
    final title = post.normalizedTitle.isNotEmpty
        ? post.normalizedTitle
        : (post.normalizedBody.isNotEmpty
              ? post.normalizedBody
              : post.displayName);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          title,
          maxLines: hero ? 3 : 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: hero ? AppTypography.iosTitle2 : AppTypography.iosCallout,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          post.displayName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
        if (hero && post.normalizedBody.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Text(
            post.normalizedBody,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCallout,
              height: AppSpacing.textLineHeightBody,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ],
    );
  }
}

class _WebInfoRail extends StatelessWidget {
  const _WebInfoRail({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: AppColors.feedCardBorder(context)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              body,
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

class _WebContextTabSpec {
  const _WebContextTabSpec({required this.id, required this.label});

  final String id;
  final String label;
}

class _CreateCardSpec {
  const _CreateCardSpec({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.action,
  });

  final String id;
  final String title;
  final String subtitle;
  final VoidCallback action;
}
