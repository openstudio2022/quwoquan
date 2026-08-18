import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/shell/actions/global_surface_actions.dart';
import 'package:quwoquan_app/runtime/shell/interest_match/interest_match_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_actions_discovery_page.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_flower_mark.dart';

part 'web_main_app_shell_auth.dart';
part 'web_main_app_shell_state.dart';

/// Web 壳可展示的中性上下文选项。业务配置类型只在 runtime/di 读取并投影，
/// 壳层不依赖 Content 的 generated config 或领域模型。
class WebMainAppShellContextOption {
  const WebMainAppShellContextOption({
    required this.id,
    required this.labelKey,
  });

  final String id;
  final String labelKey;
}

typedef WebMainAppShellContentFeedBuilder = Widget Function({
  required BuildContext context,
  required WidgetRef ref,
  required bool isDark,
  required String channelId,
  required VoidCallback? onInitialContentPainted,
});

typedef WebMainAppShellPageBuilder = Widget Function();
typedef WebMainAppShellFeaturedChannelBuilder = Widget Function({
  required VoidCallback onExitToRecommend,
});

enum WebMainAppShellCreateIntent { gallery, video, write }

typedef WebMainAppShellCreateAction = void Function(
  BuildContext context,
  WebMainAppShellCreateIntent intent,
);

typedef WebMainAppShellAccountAction = Future<void> Function(
  BuildContext context,
  WidgetRef ref,
);

/// Web 壳唯一业务组合 seam。这里只保存中性 DTO、builder 与 action；生产对象
/// presentation、generated config、route extra 和领域 action 均由 runtime/di 注入。
class WebMainAppShellDependencies {
  const WebMainAppShellDependencies({
    required this.homeContextOptions,
    required this.buildContentFeed,
    required this.buildFeaturedChannel,
    required this.buildChat,
    required this.buildProfile,
    required this.openCreate,
    required this.openStartGathering,
    required this.openStartGroupChat,
  });

  final List<WebMainAppShellContextOption> homeContextOptions;
  final WebMainAppShellContentFeedBuilder buildContentFeed;
  final WebMainAppShellFeaturedChannelBuilder buildFeaturedChannel;
  final WebMainAppShellPageBuilder buildChat;
  final WebMainAppShellPageBuilder buildProfile;
  final WebMainAppShellCreateAction openCreate;
  final WebMainAppShellAccountAction openStartGathering;
  final WebMainAppShellAccountAction openStartGroupChat;
}

class WebMainAppShell extends ConsumerStatefulWidget {
  const WebMainAppShell({
    super.key,
    required this.currentDestination,
    required this.currentLocation,
    required this.backgroundColor,
    required this.onPrimarySelected,
    required this.onGuestAuthGateOpened,
    required this.dependencies,
  });

  final MainTabDestination currentDestination;
  final String currentLocation;
  final Color backgroundColor;
  final ValueChanged<MainTabDestination> onPrimarySelected;
  final WebMainAppShellDependencies dependencies;

  /// 游客在宽屏内部 tab 上触发账号态动作、登录门已压栈后回调：由宿主把壳归位到
  /// 首页安全态，保证关闭登录不会停留在触发面板。
  final VoidCallback onGuestAuthGateOpened;

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
              if (destination == MainTabDestination.create)
                const Spacer()
              else
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
          destination: MainTabDestination.actions,
          label: AppConceptConstants.offlineActions,
          icon: CupertinoIcons.flag,
          selected: selected == MainTabDestination.actions,
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
  const _WebHomeWorkspace({
    required this.channelId,
    required this.dependencies,
  });

  final String channelId;
  final WebMainAppShellDependencies dependencies;

  @override
  Widget build(BuildContext context) {
    return _WebDesktopFrame(
      child: _WebContentFeed(
        channelId: channelId,
        dependencies: dependencies,
        onInitialContentPainted: channelId == 'recommend'
            ? AppStartupRuntime.instance.markHomeFeedContentPainted
            : null,
      ),
    );
  }
}

/// Web 宽屏内容流只负责主内容区尺寸与主题上下文。业务 feed、作者主页 route
/// 与 post 打开动作由 [WebMainAppShellDependencies] 的 production builder 注入。
class _WebContentFeed extends ConsumerWidget {
  const _WebContentFeed({
    required this.channelId,
    required this.dependencies,
    this.onInitialContentPainted,
  });

  final String channelId;
  final WebMainAppShellDependencies dependencies;
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
          child: dependencies.buildContentFeed(
            context: context,
            ref: ref,
            isDark: isDark,
            channelId: channelId,
            onInitialContentPainted: onInitialContentPainted,
          ),
        );
      },
    );
  }
}

class _WebCreateWorkspace extends ConsumerStatefulWidget {
  const _WebCreateWorkspace({
    required this.activeTabId,
    required this.onGuestAuthGateOpened,
    required this.dependencies,
  });

  final VoidCallback onGuestAuthGateOpened;

  final String activeTabId;
  final WebMainAppShellDependencies dependencies;

  @override
  ConsumerState<_WebCreateWorkspace> createState() =>
      _WebCreateWorkspaceState();
}

class _WebCreateWorkspaceState extends ConsumerState<_WebCreateWorkspace> {
  bool _showsContentActions = false;

  /// 账号态动作（发起活动 / 发起群聊）在游客态会压入登录门。登录门压栈后立刻请求
  /// 宿主把宽屏壳归位首页安全态：create 工作台是内部 tab，关闭登录只会 `go(home)`，
  /// 不归位就会原地回到触发面板。
  Future<void> _runAccountGatedAction(Future<void> Function() action) async {
    final wasGuest = !AuthGate.isAuthenticated(ref);
    await action();
    if (wasGuest && mounted) {
      widget.onGuestAuthGateOpened();
    }
  }

  @override
  Widget build(BuildContext context) {
    final contentActions = <_CreateCardSpec>[
      _CreateCardSpec(
        id: 'album',
        icon: CupertinoIcons.photo_on_rectangle,
        title: DiscoveryText.webPcCreateGalleryTitle,
        subtitle: DiscoveryText.webPcCreateGallerySubtitle,
        action: () => widget.dependencies.openCreate(
          context,
          WebMainAppShellCreateIntent.gallery,
        ),
      ),
      _CreateCardSpec(
        id: 'camera',
        icon: CupertinoIcons.camera,
        title: DiscoveryText.webPcCreateCameraTitle,
        subtitle: DiscoveryText.webPcCreateCameraSubtitle,
        action: () => widget.dependencies.openCreate(
          context,
          WebMainAppShellCreateIntent.video,
        ),
      ),
      _CreateCardSpec(
        id: 'write',
        icon: CupertinoIcons.pencil_outline,
        title: DiscoveryText.webPcCreateTextTitle,
        subtitle: DiscoveryText.webPcCreateTextSubtitle,
        action: () => widget.dependencies.openCreate(
          context,
          WebMainAppShellCreateIntent.write,
        ),
      ),
    ];
    final primaryActions = <_CreateCardSpec>[
      _CreateCardSpec(
        id: 'content',
        icon: CupertinoIcons.square_pencil,
        title: CreationText.createActionPublishContent,
        subtitle: CreationText.createEntryChooseContentSubtitle,
        action: () => setState(() => _showsContentActions = true),
      ),
      _CreateCardSpec(
        id: 'gathering',
        icon: CupertinoIcons.calendar_badge_plus,
        title: CommunityText.createActionStartGathering,
        subtitle: CommunityText.authGateSubtitleStartGathering,
        action: () => unawaited(
          _runAccountGatedAction(
            () => widget.dependencies.openStartGathering(context, ref),
          ),
        ),
      ),
      _CreateCardSpec(
        id: 'group-chat',
        icon: CupertinoIcons.chat_bubble_2,
        title: ChatText.createActionCreateGroupShort,
        subtitle: ChatText.webPcCreateGroupChatSubtitle,
        action: () => unawaited(
          _runAccountGatedAction(
            () => widget.dependencies.openStartGroupChat(context, ref),
          ),
        ),
      ),
    ];
    final actions = _showsContentActions ? contentActions : primaryActions;
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
            _showsContentActions
                ? CreationText.createEntryChooseContentSubtitle
                : CreationText.createEntryChooseActionSubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosCallout,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          _WebCreateGroup(
            groupKey: const ValueKey<String>('web-create-actions'),
            cards: actions,
            activeTabId: widget.activeTabId,
          ),
          const SizedBox(height: AppSpacing.lg),
          Align(
            alignment: Alignment.centerLeft,
            child: CupertinoButton(
              key: TestKeys.webCreateActionCancel,
              onPressed: () {
                if (_showsContentActions) {
                  setState(() => _showsContentActions = false);
                  return;
                }
                context.go(AppRoutePaths.home);
              },
              child: Text(FoundationText.cancel),
            ),
          ),
        ],
      ),
    );
  }
}

class _WebCreateGroup extends StatelessWidget {
  const _WebCreateGroup({
    required this.groupKey,
    required this.cards,
    required this.activeTabId,
  });

  final Key groupKey;
  final List<_CreateCardSpec> cards;
  final String activeTabId;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: groupKey,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
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
    final cardKey = switch (spec.id) {
      'content' => TestKeys.webCreateActionPublishContent,
      'gathering' => TestKeys.webCreateActionStartGathering,
      'group-chat' => TestKeys.webCreateActionStartGroupChat,
      _ => ValueKey<String>('web-create-card-${spec.id}'),
    };
    return CupertinoButton(
      key: cardKey,
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
