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
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_draft_picker_flow.dart';

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
      onContinueFromDraft: () => _openContinueFromDraft(context),
      onStartGroupChat: () => _openStartGroupChat(context),
      onAddContact: () => _openAddContact(context),
      onCreateCircle: () => _openCreateCircle(context),
      onCancel: () => Navigator.of(context).pop(),
      priority: priority,
    );
  }

  void _openContinueFromDraft(BuildContext sheetContext) {
    Navigator.of(sheetContext).pop();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) {
        return;
      }
      unawaited(
        presentCreateDraftPickerAndGo(rootContext, GoRouter.of(rootContext)),
      );
    });
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
                title: UITextConstants.addSameInterest,
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
                          UITextConstants.noAddableSameInterest,
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
