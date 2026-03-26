import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
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
          _TopActionIcon(
            key: TestKeys.globalSearchLauncherButton,
            icon: CupertinoIcons.search,
            onTap: () => GlobalSearchLauncher.open(
              context,
              initialScope: initialSearchScope.searchScope,
            ),
          ),
        if (showSearch) SizedBox(width: AppSpacing.intraGroupXs),
        _TopActionIcon(
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

class _TopActionIcon extends StatelessWidget {
  const _TopActionIcon({super.key, required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
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
            size: AppSpacing.iconMedium,
            color: AppColorsFunctional.getColor(
              Theme.of(context).brightness == Brightness.dark,
              ColorType.foregroundPrimary,
            ),
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

class _AddContactSheet extends ConsumerWidget {
  const _AddContactSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final contacts = ref.read(appContentRepositoryProvider).chatMockContacts;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor = SettingsSemanticConstants.pageBackground(isDark);

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: backgroundColor,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
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
            child: CupertinoScrollbar(
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
                  final displayName =
                      item['displayName']?.toString() ??
                      item['title']?.toString() ??
                      '';
                  final username = item['userId']?.toString() ?? '';
                  return CupertinoListTile(
                    leading: Container(
                      width: AppSpacing.avatarUserMd,
                      height: AppSpacing.avatarUserMd,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        image: DecorationImage(
                          image: NetworkImage(
                            item['avatarUrl']?.toString() ?? '',
                          ),
                          fit: BoxFit.cover,
                        ),
                      ),
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
                        AppToast.show(context, '已将 $displayName 加入联系候选');
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

class _GlobalSearchPanel extends ConsumerStatefulWidget {
  const _GlobalSearchPanel({required this.initialScope});

  final GlobalSearchScope initialScope;

  @override
  ConsumerState<_GlobalSearchPanel> createState() => _GlobalSearchPanelState();
}

class _GlobalSearchPanelState extends ConsumerState<_GlobalSearchPanel> {
  late final TextEditingController _controller;
  late GlobalSearchScope _scope;

  @override
  void initState() {
    super.initState();
    _scope = widget.initialScope;
    _controller = TextEditingController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final repository = ref.read(appContentRepositoryProvider);
    final query = _controller.text.trim().toLowerCase();
    final contentPool = repository.discoveryMomentData;
    final contactPool = repository.chatMockContacts;
    final messagePool = repository.chatMockConversations;
    final circlePool = CircleMockData.circles;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor = SettingsSemanticConstants.pageBackground(isDark);

    List<Map<String, dynamic>> filterList(
      List<Map<String, dynamic>> source,
      List<String> keys,
    ) {
      if (query.isEmpty) {
        return source.take(8).toList(growable: false);
      }
      return source
          .where(
            (item) => keys.any((key) {
              final value = item[key]?.toString().toLowerCase() ?? '';
              return value.contains(query);
            }),
          )
          .take(8)
          .toList(growable: false);
    }

    final contentResults = filterList(contentPool, ['title', 'content']);
    final circleResults = filterList(circlePool, ['name', 'subCategory']);
    final contactResults = filterList(contactPool, ['displayName', 'userId']);
    final messageResults = filterList(messagePool, ['title', 'lastMessage']);

    return AppFullscreenModalSurface(
      surfaceKey: TestKeys.fullscreenModalSurface,
      backgroundColor: backgroundColor,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: AppSearchField(
                  controller: _controller,
                  autofocus: true,
                  placeholder: UITextConstants.globalSearchTitle,
                  onChanged: (_) => setState(() {}),
                ),
              ),
              CupertinoButton(
                padding: EdgeInsets.only(left: AppSpacing.sm),
                child: const Text(UITextConstants.cancel),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.interGroupSm),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: CupertinoSlidingSegmentedControl<GlobalSearchScope>(
              groupValue: _scope,
              children: {
                for (var scope in GlobalSearchScope.values)
                  scope: Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    child: Text(
                      _scopeLabel(scope),
                      style: TextStyle(fontSize: AppTypography.xs),
                    ),
                  ),
              },
              onValueChanged: (scope) {
                if (scope != null) {
                  setState(() => _scope = scope);
                }
              },
            ),
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Expanded(
            child: CupertinoScrollbar(
              child: ListView(
                children: [
                  if (_scope == GlobalSearchScope.all ||
                      _scope == GlobalSearchScope.content)
                    _ResultSection(
                      title: '内容',
                      items: contentResults,
                      titleKey: 'title',
                      subtitleKey: 'content',
                    ),
                  if (_scope == GlobalSearchScope.all ||
                      _scope == GlobalSearchScope.circles)
                    _ResultSection(
                      title: '群组',
                      items: circleResults,
                      titleKey: 'name',
                      subtitleKey: 'subCategory',
                      onTap: (item) {
                        Navigator.of(context).pop();
                        context.push(
                          AppRoutePaths.circleDetail(
                            id: item['id']?.toString() ?? '',
                          ),
                        );
                      },
                    ),
                  if (_scope == GlobalSearchScope.all ||
                      _scope == GlobalSearchScope.contacts)
                    _ResultSection(
                      title: '联系人',
                      items: contactResults,
                      titleKey: 'displayName',
                      subtitleKey: 'userId',
                    ),
                  if (_scope == GlobalSearchScope.all ||
                      _scope == GlobalSearchScope.messages)
                    _ResultSection(
                      title: '消息',
                      items: messageResults,
                      titleKey: 'title',
                      subtitleKey: 'lastMessage',
                      onTap: (item) {
                        Navigator.of(context).pop();
                        context.push(
                          AppRoutePaths.chatDetail(
                            id: item['_id']?.toString() ?? '',
                          ),
                        );
                      },
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _scopeLabel(GlobalSearchScope scope) {
    switch (scope) {
      case GlobalSearchScope.all:
        return '全部';
      case GlobalSearchScope.content:
        return '内容';
      case GlobalSearchScope.circles:
        return '群组';
      case GlobalSearchScope.contacts:
        return '联系人';
      case GlobalSearchScope.messages:
        return '消息';
    }
  }
}

class _ResultSection extends StatelessWidget {
  const _ResultSection({
    required this.title,
    required this.items,
    required this.titleKey,
    required this.subtitleKey,
    this.onTap,
  });

  final String title;
  final List<Map<String, dynamic>> items;
  final String titleKey;
  final String subtitleKey;
  final ValueChanged<Map<String, dynamic>>? onTap;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: CupertinoColors.label.resolveFrom(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...items.map(
            (item) => CupertinoListTile(
              padding: EdgeInsets.zero,
              title: Text(
                item[titleKey]?.toString() ?? '',
                style: TextStyle(
                  color: CupertinoColors.label.resolveFrom(context),
                ),
              ),
              subtitle: Text(
                item[subtitleKey]?.toString() ?? '',
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                ),
              ),
              onTap: onTap == null ? null : () => onTap!(item),
            ),
          ),
        ],
      ),
    );
  }
}
