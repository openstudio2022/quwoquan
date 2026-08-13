import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/di/search_launch_dependencies.dart';
import 'package:quwoquan_app/runtime/di/global_surface_action_dependencies.dart';

class GlobalTopActions extends ConsumerWidget {
  const GlobalTopActions({
    super.key,
    this.showSearch = true,
    this.showQuickAction = false,
    this.initialSearchScope = GlobalSearchScope.all,
    this.surface = AppChromeSurface.standard,
    this.foregroundColor,
  });

  final bool showSearch;
  final bool showQuickAction;
  final GlobalSearchScope initialSearchScope;
  final AppChromeSurface surface;
  final Color? foregroundColor;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (showSearch)
          GlobalTopBarIconButton(
            key: TestKeys.globalSearchLauncherButton,
            icon: CupertinoIcons.search,
            surface: surface,
            foregroundColor: foregroundColor,
            onTap: () => GlobalSearchLauncher.open(
              context,
              initialScopeWire: initialSearchScope.scopeWireValue,
            ),
          ),
        if (showSearch) SizedBox(width: AppSpacing.intraGroupXs),
        GlobalAssistantEntryButton(
          semanticLabel: DiscoveryText.globalXiaoquSearchAsk,
          showLabel: false,
          surface: surface,
          foregroundColor: foregroundColor,
          onTap: () => GlobalAssistantLauncher.open(context, ref),
        ),
        if (showQuickAction) ...[
          SizedBox(width: AppSpacing.intraGroupXs),
          GlobalTopBarIconButton(
            icon: CupertinoIcons.add,
            surface: surface,
            foregroundColor: foregroundColor,
            onTap: () => GlobalQuickActionSheet.show(context, ref),
          ),
        ],
      ],
    );
  }
}

class GlobalAssistantLauncher {
  const GlobalAssistantLauncher._();

  static Future<void> open(BuildContext context, WidgetRef ref) {
    return ref
        .read(globalSurfaceActionBindingsProvider)
        .openAssistant(context, ref);
  }
}

class GlobalSearchLauncher {
  const GlobalSearchLauncher._();

  /// 通过组合根注入的 [GlobalSearchLaunchPort] 打开搜索；壳层不构造 search 域类型。
  static Future<void> open(
    BuildContext context, {
    String? entrySurfaceId,
    String initialScopeWire = 'all',
    String prefilledQuery = '',
  }) {
    final container = ProviderScope.containerOf(context, listen: false);
    final port = container.read(globalSearchLaunchPortProvider);
    return port.open(
      context,
      entrySurfaceId: entrySurfaceId ?? _entrySurfaceIdForContext(context),
      initialScopeWire: initialScopeWire,
      prefilledQuery: prefilledQuery,
    );
  }

  static String _entrySurfaceIdForContext(BuildContext context) {
    try {
      return GoRouterState.of(context).uri.path;
    } catch (_) {
      return AppRoutePaths.globalSearch;
    }
  }
}

class GlobalXiaoquSearchBar extends ConsumerWidget {
  const GlobalXiaoquSearchBar({
    super.key,
    this.hint = DiscoveryText.globalXiaoquSearchHint,
    this.initialSearchScope = GlobalSearchScope.all,
    this.surface = AppChromeSurface.standard,
    this.showAssistantLabel = true,
    this.hintFontSize,
  });

  final String hint;
  final GlobalSearchScope initialSearchScope;
  final AppChromeSurface surface;
  final bool showAssistantLabel;
  final double? hintFontSize;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final elevatedSurface = surface != AppChromeSurface.standard;
    final background = elevatedSurface
        ? AppColorsFunctional.getColor(
            isDark,
            ColorType.globalSearchFieldBackground,
          )
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = elevatedSurface
        ? AppColorsFunctional.getColor(
            isDark,
            ColorType.globalSearchFieldBorder,
          )
        : AppColorsFunctional.getColor(isDark, ColorType.separatorSubtle);
    final effectiveHintFontSize =
        hintFontSize ?? AppTypography.feedBodyResponsive(context);

    return Row(
      children: [
        Expanded(
          child: Container(
            height: AppSpacing.globalSearchFieldHeight,
            decoration: BoxDecoration(
              color: background,
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
              border: Border.all(color: border, width: AppSpacing.hairline),
            ),
            child: CupertinoButton(
              key: TestKeys.globalSearchLauncherButton,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.globalSearchFieldHeight,
              ),
              onPressed: () => GlobalSearchLauncher.open(
                context,
                initialScopeWire: initialSearchScope.scopeWireValue,
              ),
              child: SizedBox(
                height: AppSpacing.globalSearchFieldHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Icon(
                      CupertinoIcons.search,
                      size: AppSpacing.globalAssistantEntryMarkSize,
                      color: secondary,
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Expanded(
                      child: Text(
                        hint,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        strutStyle: StrutStyle(
                          fontSize: effectiveHintFontSize,
                          height: AppSpacing.textLineHeightDense,
                          forceStrutHeight: true,
                        ),
                        style: TextStyle(
                          fontSize: effectiveHintFontSize,
                          fontWeight: AppTypography.regular,
                          height: AppSpacing.textLineHeightDense,
                          color: secondary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        GlobalAssistantEntryButton(
          semanticLabel: DiscoveryText.globalXiaoquSearchAsk,
          showLabel: showAssistantLabel,
          surface: surface,
          onTap: () => GlobalAssistantLauncher.open(context, ref),
        ),
      ],
    );
  }
}

/// 首页顶栏等与 [GlobalTopActions] 一致的圆形热区 + 主标签色图标（非强调蓝）。
class GlobalTopBarIconButton extends StatelessWidget {
  const GlobalTopBarIconButton({
    super.key,
    required this.icon,
    required this.onTap,
    this.semanticLabel,
    this.surface = AppChromeSurface.standard,
    this.foregroundColor,
  });

  final IconData icon;
  final VoidCallback onTap;
  final String? semanticLabel;
  final AppChromeSurface surface;
  final Color? foregroundColor;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Semantics(
      button: true,
      label: semanticLabel,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        minimumSize: Size(
          AppSpacing.appChromeActionButtonSize,
          AppSpacing.appChromeActionButtonSize,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppNavigationSemanticConstants.chromeActionBackground(
              surface: surface,
            ),
            shape: BoxShape.circle,
          ),
          child: SizedBox(
            width: AppSpacing.appChromeActionButtonSize,
            height: AppSpacing.appChromeActionButtonSize,
            child: Center(
              child: Icon(
                icon,
                size: AppSpacing.appChromeActionIconSize,
                color:
                    foregroundColor ??
                    AppNavigationSemanticConstants.chromeActionIconColor(
                      isDark,
                      surface: surface,
                    ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class GlobalAssistantEntryButton extends StatelessWidget {
  const GlobalAssistantEntryButton({
    super.key,
    required this.onTap,
    this.semanticLabel,
    this.showLabel = true,
    this.surface = AppChromeSurface.standard,
    this.foregroundColor,
  });

  final VoidCallback onTap;
  final String? semanticLabel;
  final bool showLabel;
  final AppChromeSurface surface;
  final Color? foregroundColor;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final circleSize = AppSpacing.globalAssistantEntryMarkSize;
    final elevatedSurface = surface != AppChromeSurface.standard;
    final toolbarForeground = foregroundColor;
    return Semantics(
      button: true,
      label: semanticLabel,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        minimumSize: Size(
          AppSpacing.appChromeActionButtonSize,
          AppSpacing.appChromeActionButtonSize,
        ),
        child: SizedBox(
          width: AppSpacing.appChromeActionButtonSize,
          height: AppSpacing.appChromeActionButtonSize,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (toolbarForeground != null && !showLabel)
                Icon(
                  CupertinoIcons.sparkles,
                  key: TestKeys.globalAssistantEntryMark,
                  size: AppSpacing.appChromeActionIconSize,
                  color: toolbarForeground,
                )
              else
                Container(
                  key: TestKeys.globalAssistantEntryMark,
                  width: circleSize,
                  height: circleSize,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        AppColors.welcomeTitleGradientEnd,
                        isDark
                            ? AppColors.assistantMarkColorOnDark
                            : AppColors.assistantMarkColor,
                        AppColors.welcomeTitleGradientMid,
                      ],
                    ),
                    border: Border.all(
                      color: AppColors.white.withValues(
                        alpha: elevatedSurface ? 0.68 : (isDark ? 0.24 : 0.4),
                      ),
                      width: AppSpacing.hairline,
                    ),
                    boxShadow: elevatedSurface
                        ? [
                            BoxShadow(
                              color: AppColors.black.withValues(alpha: 0.18),
                              blurRadius: AppSpacing.six,
                            ),
                          ]
                        : null,
                  ),
                  child: Icon(
                    CupertinoIcons.sparkles,
                    size: AppSpacing.globalAssistantEntryGlyphSize,
                    color: AppColors.white,
                  ),
                ),
              if (showLabel) ...[
                SizedBox(height: AppSpacing.globalAssistantEntryLabelGap),
                Text(
                  DiscoveryText.globalXiaoquSearchAsk,
                  maxLines: 1,
                  overflow: TextOverflow.clip,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    fontWeight: AppTypography.medium,
                    height: AppSpacing.textLineHeightDense,
                    color: elevatedSurface
                        ? AppColors.white
                        : AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundPrimary,
                          ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class GlobalQuickActionSheet {
  const GlobalQuickActionSheet._();

  static Future<void> show(BuildContext context, WidgetRef ref) async {
    final intent = await showAppBottomModal<_QuickActionIntent>(
      context: context,
      builder: (sheetContext) => const _QuickActionSheet(),
    );
    if (intent == null || !context.mounted) {
      return;
    }
    await WidgetsBinding.instance.endOfFrame;
    if (!context.mounted) {
      return;
    }
    await _handleQuickActionIntent(context, ref, intent);
  }

  /// 进入创建流（写文章/发图片/发视频）。/create 路由门负责未登录拦截与登录后回源。
  static void openCreateAction(BuildContext context, String actionWire) {
    context.go(AppRoutePaths.create(type: actionWire));
  }

  /// 发起活动使用 generated canonical route；route host 负责依赖不可用终态。
  static Future<void> openStartGathering(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final opened = await ref
        .read(globalSurfaceActionBindingsProvider)
        .openStartGathering(context);
    if (!opened && context.mounted) {
      await showAppActionSheet<void>(
        context,
        title: CommunityText.gatheringCreateUnavailableTitle,
        message: CommunityText.gatheringCreateUnavailableMessage,
        sections: const <AppActionSheetSection<void>>[],
      );
    }
  }

  static Future<void> openGatedStartGathering(
    BuildContext context,
    WidgetRef ref,
  ) {
    return _runGatedSheetAction(
      context,
      ref,
      reason: AuthGateReason.startGathering,
      sheet: AuthContinuationSheet.startGathering,
      openNow: () => openStartGathering(context, ref),
    );
  }

  /// 发起群聊。已登录直接进入；登录后续接由 [OpenSheetContinuation] 在外壳消费。
  static void openStartGroupChat(BuildContext context) {
    context.push(AppRoutePaths.startGroupChat);
  }

  /// 从非快捷动作面板的账号态入口进入发起群聊，保持与面板入口同一登录续接。
  static Future<void> openGatedStartGroupChat(
    BuildContext context,
    WidgetRef ref,
  ) {
    return _runGatedSheetAction(
      context,
      ref,
      reason: AuthGateReason.startGroupChat,
      sheet: AuthContinuationSheet.startGroupChat,
      openNow: () => openStartGroupChat(context),
    );
  }

  /// 进入「添加联系人」主页（账号态强入口）。路由门负责未登录拦截与登录后回源。
  static void openAddContact(BuildContext context) {
    context.push(AppRoutePaths.addContact);
  }

  /// 打开「建圈子」编辑页（账号态动作）。
  static void openCreateCircle(BuildContext context) {
    ProviderScope.containerOf(
      context,
      listen: false,
    ).read(globalSurfaceActionBindingsProvider).openCreateCircle(context);
  }

  /// 打开「兴趣配对」发现入口。此页仅导流既有真实面，游客可浏览。
  static void openInterestMatch(BuildContext context) {
    context.push(AppRoutePaths.interestMatch);
  }

  /// 登录成功后消费 [OpenSheetContinuation]：续接打开对应面板/流程。
  /// 由始终在场的外壳（MainAppShell）调用，确保 context 在路由树内、续接稳定。
  static Future<void> resumeSheetContinuation(
    BuildContext context,
    WidgetRef ref,
    AuthContinuationSheet sheet,
  ) async {
    switch (sheet) {
      case AuthContinuationSheet.addContact:
        openAddContact(context);
      case AuthContinuationSheet.startGathering:
        await openStartGathering(context, ref);
      case AuthContinuationSheet.startGroupChat:
        openStartGroupChat(context);
      case AuthContinuationSheet.createCircle:
        openCreateCircle(context);
    }
  }

  static Future<void> _handleQuickActionIntent(
    BuildContext context,
    WidgetRef ref,
    _QuickActionIntent intent,
  ) async {
    switch (intent.kind) {
      case _QuickActionIntentKind.createAction:
        final action = intent.createAction;
        if (action == null) {
          return;
        }
        openCreateAction(context, action);
      case _QuickActionIntentKind.startGathering:
        await openGatedStartGathering(context, ref);
      case _QuickActionIntentKind.startGroupChat:
        await openGatedStartGroupChat(context, ref);
    }
  }

  static Future<void> _runGatedSheetAction(
    BuildContext context,
    WidgetRef ref, {
    required AuthGateReason reason,
    required AuthContinuationSheet sheet,
    required FutureOr<void> Function() openNow,
  }) async {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await openNow();
      return;
    }
    ref
        .read(authContinuationProvider.notifier)
        .set(OpenSheetContinuation(sheet));
    // 账号态动作门为强登录入口：动作面板已关闭，关闭登录只走安全兜底（首页），
    // 禁止 pop 回受限触发态形成「关闭→再弹登录」死循环（登录入口无死循环宪法）。
    await requireLogin(
      ref,
      context,
      reason,
      dismissFallback: AppRoutePaths.home,
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
  }
}

enum _QuickActionIntentKind { createAction, startGathering, startGroupChat }

class _QuickActionIntent {
  const _QuickActionIntent(this.kind, {this.createAction});

  final _QuickActionIntentKind kind;
  final String? createAction;

  static _QuickActionIntent create(String actionWire) => _QuickActionIntent(
    _QuickActionIntentKind.createAction,
    createAction: actionWire,
  );
}

class _QuickActionSheet extends StatelessWidget {
  const _QuickActionSheet();

  @override
  Widget build(BuildContext context) {
    final bindings = ProviderScope.containerOf(
      context,
      listen: false,
    ).read(globalSurfaceActionBindingsProvider);
    return bindings.buildQuickActionSheet(
      context: context,
      onCreateAction: (actionWire) =>
          Navigator.of(context).pop(_QuickActionIntent.create(actionWire)),
      onStartGathering: () => Navigator.of(
        context,
      ).pop(const _QuickActionIntent(_QuickActionIntentKind.startGathering)),
      onStartGroupChat: () => Navigator.of(
        context,
      ).pop(const _QuickActionIntent(_QuickActionIntentKind.startGroupChat)),
      onCancel: () => Navigator.of(context).pop(),
    );
  }
}

class GlobalSearchSheet {
  const GlobalSearchSheet._();

  static Future<void> show(
    BuildContext context, {
    GlobalSearchScope initialScope = GlobalSearchScope.all,
  }) {
    return GlobalSearchLauncher.open(
      context,
      initialScopeWire: initialScope.scopeWireValue,
    );
  }
}

enum GlobalSearchScope { all, content, circles, contacts, messages }

extension GlobalSearchScopeX on GlobalSearchScope {
  /// 与 search 域 `SearchScope.wireValue` 对齐的 wire 字面量；壳层只传 wire，不依赖域枚举。
  String get scopeWireValue => switch (this) {
    GlobalSearchScope.all => 'all',
    GlobalSearchScope.content => 'content',
    GlobalSearchScope.circles => 'circles',
    GlobalSearchScope.contacts => 'social_relation',
    GlobalSearchScope.messages => 'messages',
  };
}
