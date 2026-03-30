import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';

class GlobalTopActions extends StatelessWidget {
  const GlobalTopActions({
    super.key,
    this.showSearch = true,
    this.initialSearchScope = GlobalSearchScope.all,
    this.quickActionPriority = CreateActionSheetPriority.createPrimary,
  });

  final bool showSearch;
  final GlobalSearchScope initialSearchScope;
  final CreateActionSheetPriority quickActionPriority;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (showSearch)
          GlobalTopBarIconButton(
            key: TestKeys.globalSearchLauncherButton,
            icon: CupertinoIcons.search,
            onTap: () => GlobalSearchLauncher.open(
              context,
              initialScope: initialSearchScope.searchScope,
            ),
          ),
        if (showSearch) SizedBox(width: AppSpacing.intraGroupXs),
        GlobalTopBarIconButton(
          icon: CupertinoIcons.add,
          onTap: () => GlobalQuickActionSheet.show(
            context,
            priority: quickActionPriority,
          ),
        ),
      ],
    );
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

/// 首页顶栏等与 [GlobalTopActions] 一致的圆形热区 + 主标签色图标（非强调蓝）。
class GlobalTopBarIconButton extends StatelessWidget {
  const GlobalTopBarIconButton({
    super.key,
    required this.icon,
    required this.onTap,
  });

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      child: SizedBox(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        child: Center(
          child: Icon(
            icon,
            size: AppNavigationSemanticConstants.barIconSize,
            color: AppNavigationSemanticConstants.barIconColor(isDark),
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
}

class _QuickActionSheet extends StatelessWidget {
  const _QuickActionSheet({required this.rootContext, required this.priority});

  final BuildContext rootContext;
  final CreateActionSheetPriority priority;

  @override
  Widget build(BuildContext context) {
    return CreateActionSheet(
      onCreateAction: (action) => _openCreateAction(context, action),
      onStartGroupChat: () => _openStartGroupChat(context),
      onAddContact: () => _openAddContact(context),
      onCreateCircle: () => _openCreateCircle(context),
      onCancel: () => Navigator.of(context).pop(),
      priority: priority,
    );
  }

  void _openCreateAction(BuildContext sheetContext, EditorStartAction action) {
    Navigator.of(sheetContext).pop();
    rootContext.go(AppRoutePaths.create(type: action.name));
  }

  void _openStartGroupChat(BuildContext sheetContext) {
    Navigator.of(sheetContext).pop();
    rootContext.push(AppRoutePaths.startGroupChat);
  }

  void _openAddContact(BuildContext sheetContext) {
    Navigator.of(sheetContext).pop();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) return;
      showCupertinoModalPopup<void>(
        context: rootContext,
        barrierColor: Colors.transparent,
        builder: (_) => const _AddContactSheet(),
      );
    });
  }

  void _openCreateCircle(BuildContext sheetContext) {
    Navigator.of(sheetContext).pop();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) return;
      Navigator.of(rootContext)
          .push<String>(
            CupertinoPageRoute<String>(
              settings: const RouteSettings(
                name: PageAccessInternalRoutes.globalSurfaceCircleEditCreate,
              ),
              builder: (_) => const CircleEditSettingsPage.create(),
            ),
          )
          .then((circleId) {
            if (!rootContext.mounted || circleId == null || circleId.isEmpty) {
              return;
            }
            rootContext.push(AppRoutePaths.circleDetail(id: circleId));
          });
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
    _contactsFuture = ref.read(chatRepositoryProvider).listContacts(
          limit: 8.clamp(1, CloudApiDefaults.pageLimit),
        );
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
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            UITextConstants.addContact,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
              color: CupertinoColors.label.resolveFrom(context),
            ),
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Flexible(
            child: FutureBuilder<List<ChatContactRowDto>>(
              future: _contactsFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return SizedBox(
                    height: AppSpacing.minInteractiveSize * 2,
                    child: Center(
                      child: CupertinoActivityIndicator(
                        color: CupertinoColors.label.resolveFrom(context),
                      ),
                    ),
                  );
                }
                final contacts = snapshot.data ?? const <ChatContactRowDto>[];
                if (contacts.isEmpty) {
                  return Padding(
                    padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
                    child: Text(
                      '暂无可添加联系人',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
                      ),
                    ),
                  );
                }
                return CupertinoScrollbar(
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: contacts.length.clamp(0, 8),
                    separatorBuilder: (context, index) => Container(
                      margin: EdgeInsets.only(
                        left: AppSpacing.largeAvatarSize + AppSpacing.md,
                      ),
                      height: SettingsSemanticConstants.dividerThickness,
                      color: SettingsSemanticConstants.dividerColor(isDark),
                    ),
                    itemBuilder: (context, index) {
                      final item = contacts[index];
                      final displayName = item.displayName.trim().isNotEmpty
                          ? item.displayName
                          : item.userId;
                      final username = item.userId;
                      final avatarUrl = item.avatarUrl.trim();
                      return CupertinoListTile(
                        leading: Container(
                          width: AppSpacing.avatarUserMd,
                          height: AppSpacing.avatarUserMd,
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
                                  color: CupertinoColors.secondaryLabel
                                      .resolveFrom(context),
                                )
                              : null,
                        ),
                        title: Text(
                          displayName,
                          style: TextStyle(
                            color: CupertinoColors.label.resolveFrom(context),
                          ),
                        ),
                        subtitle: Text(
                          username,
                          style: TextStyle(
                            color: CupertinoColors.secondaryLabel.resolveFrom(
                              context,
                            ),
                          ),
                        ),
                        trailing: CupertinoButton(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.sm,
                            vertical: AppSpacing.xs,
                          ),
                          color: AppColors.primaryColor.withValues(alpha: 0.12),
                          onPressed: () {
                            Navigator.of(context).pop();
                            AppToast.show(
                              context,
                              '已将 $displayName 加入联系候选',
                            );
                          },
                          child: Text(
                            UITextConstants.addContact,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                );
              },
            ),
          ),
          SizedBox(height: AppSpacing.md),
          CupertinoButton(
            child: const Text(UITextConstants.cancel),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
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
