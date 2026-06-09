import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_draft_picker_flow.dart';

class GlobalTopActions extends ConsumerWidget {
  const GlobalTopActions({
    super.key,
    this.showSearch = true,
    this.showQuickAction = false,
    this.initialSearchScope = GlobalSearchScope.all,
    this.quickActionPriority = CreateActionSheetPriority.createPrimary,
    this.surface = AppChromeSurface.standard,
    this.foregroundColor,
  });

  final bool showSearch;
  final bool showQuickAction;
  final GlobalSearchScope initialSearchScope;
  final CreateActionSheetPriority quickActionPriority;
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
              initialScope: initialSearchScope.searchScope,
            ),
          ),
        if (showSearch) SizedBox(width: AppSpacing.intraGroupXs),
        GlobalAssistantEntryButton(
          semanticLabel: UITextConstants.globalXiaoquSearchAsk,
          showLabel: false,
          onTap: () => GlobalAssistantLauncher.open(context, ref),
        ),
        if (showQuickAction) ...[
          SizedBox(width: AppSpacing.intraGroupXs),
          GlobalTopBarIconButton(
            icon: CupertinoIcons.add,
            surface: surface,
            foregroundColor: foregroundColor,
            onTap: () => GlobalQuickActionSheet.show(
              context,
              priority: quickActionPriority,
            ),
          ),
        ],
      ],
    );
  }
}

class GlobalAssistantLauncher {
  const GlobalAssistantLauncher._();

  static Future<void> open(BuildContext context, WidgetRef ref) {
    final route = _routeForContext(context);
    final target = VisitTarget.page('global_assistant_$route');
    final experience = ref
        .read(visitRecorderServiceProvider)
        .getExperience(target);
    final openContext = AssistantOpenContext(
      source: _sourceForRoute(route),
      visitTarget: target,
      experienceLevel: experience,
      tab: route,
    );
    return context.push(AppRoutePaths.assistantPersonal, extra: openContext);
  }

  static String _routeForContext(BuildContext context) {
    try {
      return GoRouterState.of(context).uri.path;
    } catch (_) {
      return AppRoutePaths.home;
    }
  }

  static AssistantSource _sourceForRoute(String route) {
    if (route == AppRoutePaths.circles || route.startsWith('/circle/')) {
      return AssistantSource.circles;
    }
    if (route.startsWith(AppRoutePaths.chat)) {
      return AssistantSource.chat;
    }
    if (route.startsWith(AppRoutePaths.createPathTemplate)) {
      return AssistantSource.create;
    }
    if (route.startsWith(AppRoutePaths.globalSearch)) {
      return AssistantSource.search;
    }
    if (route == AppRoutePaths.profile || route.startsWith('/user/')) {
      return AssistantSource.profile;
    }
    return AssistantSource.discovery;
  }
}

class GlobalSearchLauncher {
  const GlobalSearchLauncher._();

  static Future<void> open(
    BuildContext context, {
    SearchLaunchContext? launchContext,
    SearchScope initialScope = SearchScope.all,
    String prefilledQuery = '',
  }) {
    final effectiveLaunchContext =
        launchContext ??
        SearchLaunchContext(
          entrySurfaceId: _entrySurfaceIdForContext(context),
          initialScope: initialScope,
          prefilledQuery: prefilledQuery,
        );
    return context.push(
      AppRoutePaths.globalSearch,
      extra: effectiveLaunchContext,
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
    this.hint = UITextConstants.globalXiaoquSearchHint,
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
                initialScope: initialSearchScope.searchScope,
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
          semanticLabel: UITextConstants.globalXiaoquSearchAsk,
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
  });

  final VoidCallback onTap;
  final String? semanticLabel;
  final bool showLabel;
  final AppChromeSurface surface;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final circleSize = AppSpacing.globalAssistantEntryMarkSize;
    final elevatedSurface = surface != AppChromeSurface.standard;
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
                  UITextConstants.globalXiaoquSearchAsk,
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

  static Future<void> show(
    BuildContext context, {
    CreateActionSheetPriority priority =
        CreateActionSheetPriority.createPrimary,
  }) {
    return showCupertinoModalPopup<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (sheetContext) =>
          _QuickActionSheet(rootContext: context, priority: priority),
    );
  }

  /// 进入创建流（写文章/发图片/发视频）。/create 路由门负责未登录拦截与登录后回源。
  static void openCreateAction(BuildContext context, EditorStartAction action) {
    context.go(AppRoutePaths.create(type: action.name));
  }

  /// 发起群聊。已登录直接进入；登录后续接由 [OpenSheetContinuation] 在外壳消费。
  static void openStartGroupChat(BuildContext context) {
    context.push(AppRoutePaths.startGroupChat);
  }

  /// 打开「添加联系人」面板（账号态动作）。
  static void openAddContact(BuildContext context) {
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (_) => const _AddContactSheet(),
    );
  }

  /// 打开「建圈子」编辑页（账号态动作）。
  static void openCreateCircle(BuildContext context) {
    Navigator.of(context)
        .push<String>(
          CupertinoPageRoute<String>(
            settings: const RouteSettings(
              name: PageAccessInternalRoutes.globalSurfaceCircleEditCreate,
            ),
            builder: (_) => const CircleEditSettingsPage.create(),
          ),
        )
        .then((circleId) {
          if (!context.mounted || circleId == null || circleId.isEmpty) {
            return;
          }
          context.push(AppRoutePaths.circleDetail(id: circleId));
        });
  }

  /// 登录成功后消费 [OpenSheetContinuation]：续接打开对应面板/流程。
  /// 由始终在场的外壳（MainAppShell）调用，确保 context 在路由树内、续接稳定。
  static void resumeSheetContinuation(
    BuildContext context,
    AuthContinuationSheet sheet,
  ) {
    switch (sheet) {
      case AuthContinuationSheet.addContact:
        openAddContact(context);
      case AuthContinuationSheet.startGroupChat:
        openStartGroupChat(context);
      case AuthContinuationSheet.createCircle:
        openCreateCircle(context);
    }
  }
}

class _QuickActionSheet extends ConsumerWidget {
  const _QuickActionSheet({required this.rootContext, required this.priority});

  final BuildContext rootContext;
  final CreateActionSheetPriority priority;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return CreateActionSheet(
      onCreateAction: (action) => _openCreateAction(context, action),
      onContinueFromDraft: () => _openContinueFromDraft(context, ref),
      onStartGroupChat: () => _openStartGroupChat(context, ref),
      onAddContact: () => _openAddContact(context, ref),
      onCreateCircle: () => _openCreateCircle(context, ref),
      onCancel: () => Navigator.of(context).pop(),
      priority: priority,
    );
  }

  void _openContinueFromDraft(BuildContext sheetContext, WidgetRef ref) {
    Navigator.of(sheetContext).pop();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) {
        return;
      }
      // 草稿属账号资产：未登录先引导登录（登录后用户回到加号面板再续）。
      if (!ref.read(authSessionControllerProvider).isAuthenticated) {
        unawaited(requireLogin(ref, rootContext, AuthGateReason.createPost));
        return;
      }
      unawaited(
        presentCreateDraftPickerAndGo(rootContext, GoRouter.of(rootContext)),
      );
    });
  }

  void _openCreateAction(BuildContext sheetContext, EditorStartAction action) {
    Navigator.of(sheetContext).pop();
    // Wait for the transparent quick-action sheet to finish dismissing before
    // replacing the root route, otherwise the entry sheet reverse transition
    // and CreatePage's immediate picker/camera push can flash a black frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) {
        return;
      }
      // /create 路由门负责未登录拦截与登录后按 redirect 回源。
      GlobalQuickActionSheet.openCreateAction(rootContext, action);
    });
  }

  void _openStartGroupChat(BuildContext sheetContext, WidgetRef ref) {
    Navigator.of(sheetContext).pop();
    _gatedSheetAction(
      ref,
      reason: AuthGateReason.startGroupChat,
      sheet: AuthContinuationSheet.startGroupChat,
      openNow: () => GlobalQuickActionSheet.openStartGroupChat(rootContext),
    );
  }

  void _openAddContact(BuildContext sheetContext, WidgetRef ref) {
    Navigator.of(sheetContext).pop();
    _gatedSheetAction(
      ref,
      reason: AuthGateReason.addContact,
      sheet: AuthContinuationSheet.addContact,
      openNow: () => GlobalQuickActionSheet.openAddContact(rootContext),
    );
  }

  void _openCreateCircle(BuildContext sheetContext, WidgetRef ref) {
    Navigator.of(sheetContext).pop();
    _gatedSheetAction(
      ref,
      reason: AuthGateReason.createCircle,
      sheet: AuthContinuationSheet.createCircle,
      openNow: () => GlobalQuickActionSheet.openCreateCircle(rootContext),
    );
  }

  /// 账号态动作门：已登录直接执行；未登录先登记续接再引导登录，登录成功后由
  /// 外壳消费 [OpenSheetContinuation] 自动续接，避免「登录回来什么都没发生」。
  void _gatedSheetAction(
    WidgetRef ref, {
    required AuthGateReason reason,
    required AuthContinuationSheet sheet,
    required VoidCallback openNow,
  }) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) {
        return;
      }
      if (ref.read(authSessionControllerProvider).isAuthenticated) {
        openNow();
        return;
      }
      ref
          .read(authContinuationProvider.notifier)
          .set(OpenSheetContinuation(sheet));
      unawaited(requireLogin(ref, rootContext, reason));
    });
  }
}

class _AddContactSheet extends ConsumerStatefulWidget {
  const _AddContactSheet();

  @override
  ConsumerState<_AddContactSheet> createState() => _AddContactSheetState();
}

class _AddContactSheetState extends ConsumerState<_AddContactSheet> {
  late final Future<List<ChatContactRowDto>> _contactsFuture;

  @override
  void initState() {
    super.initState();
    _contactsFuture = ref
        .read(chatRepositoryProvider)
        .listContacts(limit: 8.clamp(1, CloudApiDefaults.pageLimit));
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: backgroundColor,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final maxListHeight = constraints.maxHeight.isFinite
              ? (constraints.maxHeight -
                        AppSpacing.modalHeaderHeight -
                        SettingsSemanticConstants.conversationSheetSectionGap -
                        AppSpacing.buttonHeight)
                    .clamp(AppSpacing.minInteractiveSize * 2, double.infinity)
                    .toDouble()
              : double.infinity;

          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ConversationSheetHeader(
                isDark: isDark,
                title: UITextConstants.addContactSheetTitle,
              ),
              FutureBuilder<List<ChatContactRowDto>>(
                future: _contactsFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return ConversationSheetListCard(
                      isDark: isDark,
                      child: SizedBox(
                        height: AppSpacing.minInteractiveSize * 2,
                        child: Center(
                          child: CupertinoActivityIndicator(
                            color: CupertinoColors.label.resolveFrom(context),
                          ),
                        ),
                      ),
                    );
                  }
                  final contacts = snapshot.data ?? const <ChatContactRowDto>[];
                  if (contacts.isEmpty) {
                    return ConversationSheetListCard(
                      isDark: isDark,
                      child: Padding(
                        padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
                        child: Text(
                          UITextConstants.noAddableContacts,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: AppTypography.base,
                            color: CupertinoColors.secondaryLabel.resolveFrom(
                              context,
                            ),
                          ),
                        ),
                      ),
                    );
                  }
                  return ConversationSheetListCard(
                    isDark: isDark,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(maxHeight: maxListHeight),
                      child: ListView.separated(
                        shrinkWrap: true,
                        primary: false,
                        padding: EdgeInsets.zero,
                        physics: const BouncingScrollPhysics(),
                        itemCount: contacts.length,
                        separatorBuilder: (context, index) =>
                            ConversationSheetDivider(
                              isDark: isDark,
                              dividerLeftInset:
                                  _AddContactSheetRow.dividerLeftInset,
                            ),
                        itemBuilder: (context, index) => _AddContactSheetRow(
                          isDark: isDark,
                          contact: contacts[index],
                          onAdd: (displayName) {
                            Navigator.of(context).pop();
                            AppToast.show(context, '已将 $displayName 加入联系候选');
                          },
                        ),
                      ),
                    ),
                  );
                },
              ),
              SizedBox(
                height: SettingsSemanticConstants.conversationSheetSectionGap,
              ),
              ConversationSheetCancelBar(
                isDark: isDark,
                label: UITextConstants.cancel,
                onTap: () => Navigator.of(context).pop(),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _AddContactSheetRow extends StatelessWidget {
  const _AddContactSheetRow({
    required this.isDark,
    required this.contact,
    required this.onAdd,
  });

  final bool isDark;
  final ChatContactRowDto contact;
  final ValueChanged<String> onAdd;

  static double get dividerLeftInset =>
      AppSpacing.containerMd + AppSpacing.avatarUserSm + AppSpacing.containerSm;

  @override
  Widget build(BuildContext context) {
    final displayName = contact.displayName.trim().isNotEmpty
        ? contact.displayName
        : contact.userId;
    final username = contact.userId;
    final avatarUrl = contact.avatarUrl.trim();
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerXs,
      ),
      child: Row(
        children: [
          _AddContactAvatar(isDark: isDark, avatarUrl: avatarUrl),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                    color: primary,
                    height: AppTypography.lineHeightCompact,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  username,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.regular,
                    color: secondary,
                    height: AppTypography.lineHeightCompact,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(width: AppSpacing.containerSm),
          ConversationSheetPrimaryActionButton(
            isDark: isDark,
            label: UITextConstants.addContact,
            onTap: () => onAdd(displayName),
          ),
        ],
      ),
    );
  }
}

class _AddContactAvatar extends StatelessWidget {
  const _AddContactAvatar({required this.isDark, required this.avatarUrl});

  final bool isDark;
  final String avatarUrl;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.avatarUserSm,
      height: AppSpacing.avatarUserSm,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isDark
            ? AppColors.white.withValues(alpha: 0.08)
            : AppColors.black.withValues(alpha: 0.06),
        image: avatarUrl.isEmpty
            ? null
            : DecorationImage(
                image: NetworkImage(avatarUrl),
                fit: BoxFit.cover,
              ),
      ),
      alignment: Alignment.center,
      child: avatarUrl.isEmpty
          ? Icon(
              CupertinoIcons.person_fill,
              size: AppSpacing.iconSmall,
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
            )
          : null,
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
      initialScope: initialScope.searchScope,
    );
  }
}

enum GlobalSearchScope { all, content, circles, contacts, messages }

extension GlobalSearchScopeX on GlobalSearchScope {
  SearchScope get searchScope => switch (this) {
    GlobalSearchScope.all => SearchScope.all,
    GlobalSearchScope.content => SearchScope.content,
    GlobalSearchScope.circles => SearchScope.circles,
    GlobalSearchScope.contacts => SearchScope.socialRelation,
    GlobalSearchScope.messages => SearchScope.messages,
  };
}
