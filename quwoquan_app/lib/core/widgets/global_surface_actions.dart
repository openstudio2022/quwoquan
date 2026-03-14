import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

class GlobalTopActions extends StatelessWidget {
  const GlobalTopActions({
    super.key,
    this.showSearch = true,
    this.initialSearchScope = GlobalSearchScope.all,
  });

  final bool showSearch;
  final GlobalSearchScope initialSearchScope;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (showSearch)
          _TopActionIcon(
            icon: CupertinoIcons.search,
            onTap: () => GlobalSearchSheet.show(
              context,
              initialScope: initialSearchScope,
            ),
          ),
        _TopActionIcon(
          icon: CupertinoIcons.add,
          onTap: () => GlobalQuickActionSheet.show(context),
        ),
      ],
    );
  }
}

class _TopActionIcon extends StatelessWidget {
  const _TopActionIcon({
    required this.icon,
    required this.onTap,
  });

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
      minSize: AppSpacing.minInteractiveSize,
      onPressed: onTap,
      child: Icon(
        icon,
        size: AppSpacing.iconMedium,
        color: AppColorsFunctional.getColor(
          Theme.of(context).brightness == Brightness.dark,
          ColorType.foregroundPrimary,
        ),
      ),
    );
  }
}

class GlobalQuickActionSheet {
  const GlobalQuickActionSheet._();

  static Future<void> show(BuildContext context) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => _QuickActionSheet(rootContext: context),
    );
  }
}

class _QuickActionSheet extends StatelessWidget {
  const _QuickActionSheet({required this.rootContext});

  final BuildContext rootContext;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.containerLg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              UITextConstants.globalActionSheetTitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _ActionTile(
              icon: CupertinoIcons.photo_on_rectangle,
              title: UITextConstants.createActionGallery,
              subtitle: UITextConstants.createActionGalleryHint,
              onTap: () => _openCreateAction(
                context,
                EditorStartAction.gallery,
              ),
            ),
            _ActionTile(
              icon: CupertinoIcons.camera,
              title: UITextConstants.createActionCamera,
              subtitle: UITextConstants.createActionCaptureHint,
              onTap: () => _openCreateAction(
                context,
                EditorStartAction.capture,
              ),
            ),
            _ActionTile(
              icon: CupertinoIcons.pencil,
              title: UITextConstants.createActionTextShort,
              subtitle: UITextConstants.createActionWriteHint,
              onTap: () => _openCreateAction(
                context,
                EditorStartAction.write,
              ),
            ),
            SizedBox(height: AppSpacing.interGroupXs),
            _ActionTile(
              icon: CupertinoIcons.person_3,
              title: UITextConstants.startGroupChat,
              subtitle: UITextConstants.createActionGroupChatHint,
              onTap: () => _openStartGroupChat(context),
            ),
            _ActionTile(
              icon: CupertinoIcons.person_add,
              title: UITextConstants.addContact,
              subtitle: UITextConstants.createActionContactHint,
              onTap: () => _openAddContact(context),
            ),
          ],
        ),
      ),
    );
  }

  void _openCreateAction(BuildContext sheetContext, EditorStartAction action) {
    Navigator.of(sheetContext).pop();
    rootContext.go(AppRoutePaths.create(type: action.name));
  }

  void _openStartGroupChat(BuildContext sheetContext) {
    Navigator.of(sheetContext).pop();
    final route =
        '${AppRoutePaths.chatDetail(id: AppConceptConstants.assistantConversationId)}/${AppRoutePaths.chatAddMembersSegment}';
    rootContext.push(route);
  }

  void _openAddContact(BuildContext sheetContext) {
    Navigator.of(sheetContext).pop();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!rootContext.mounted) return;
      showModalBottomSheet<void>(
        context: rootContext,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (_) => const _AddContactSheet(),
      );
    });
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.symmetric(
        horizontal: AppSpacing.xs,
        vertical: AppSpacing.xs,
      ),
      leading: Container(
        width: AppSpacing.largeButtonSize,
        height: AppSpacing.largeButtonSize,
        decoration: BoxDecoration(
          color: AppColors.primaryColor.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Icon(icon, color: AppColors.primaryColor),
      ),
      title: Text(
        title,
        style: TextStyle(
          fontSize: AppTypography.base,
          fontWeight: AppTypography.semiBold,
        ),
      ),
      subtitle: Text(
        subtitle,
        style: TextStyle(
          fontSize: AppTypography.sm,
          color: Colors.black54,
        ),
      ),
      onTap: onTap,
    );
  }
}

class _AddContactSheet extends ConsumerWidget {
  const _AddContactSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final contacts = ref.read(appContentRepositoryProvider).chatMockContacts;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
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
              ),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            SizedBox(
              height: AppSpacing.largeButtonSize * 6,
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: contacts.length.clamp(0, 8),
                separatorBuilder: (_, __) => Divider(
                  height: AppSpacing.interGroupXs,
                  color: Colors.black12,
                ),
                itemBuilder: (context, index) {
                  final item = contacts[index];
                  final displayName =
                      item['displayName']?.toString() ??
                      item['title']?.toString() ??
                      '';
                  final username = item['userId']?.toString() ?? '';
                  return ListTile(
                    leading: CircleAvatar(
                      backgroundImage: NetworkImage(
                        item['avatarUrl']?.toString() ?? '',
                      ),
                      onBackgroundImageError: (_, _) {},
                    ),
                    title: Text(displayName),
                    subtitle: Text(username),
                    trailing: CupertinoButton(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.sm,
                        vertical: AppSpacing.xs,
                      ),
                      color: AppColors.primaryColor.withValues(alpha: 0.12),
                      onPressed: () {
                        final messenger = ScaffoldMessenger.of(context);
                        Navigator.of(context).pop();
                        messenger.showSnackBar(
                          SnackBar(content: Text('已将 $displayName 加入联系候选')),
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
            ),
          ],
        ),
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
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _GlobalSearchPanel(initialScope: initialScope),
    );
  }
}

enum GlobalSearchScope { all, content, circles, contacts, messages }

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

    List<Map<String, dynamic>> filterList(
      List<Map<String, dynamic>> source,
      List<String> keys,
    ) {
      if (query.isEmpty) {
        return source.take(8).toList(growable: false);
      }
      return source
          .where((item) => keys.any((key) {
                final value = item[key]?.toString().toLowerCase() ?? '';
                return value.contains(query);
              }))
          .take(8)
          .toList(growable: false);
    }

    final contentResults = filterList(contentPool, ['title', 'content']);
    final circleResults = filterList(circlePool, ['name', 'subCategory']);
    final contactResults = filterList(contactPool, ['displayName', 'userId']);
    final messageResults = filterList(messagePool, ['title', 'lastMessage']);

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.containerLg,
        ),
        child: Column(
          children: [
            TextField(
              controller: _controller,
              autofocus: true,
              decoration: InputDecoration(
                hintText: UITextConstants.globalSearchTitle,
                prefixIcon: const Icon(CupertinoIcons.search),
                filled: true,
                fillColor: Colors.black.withValues(alpha: 0.04),
                border: OutlineInputBorder(
                  borderSide: BorderSide.none,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
              ),
              onChanged: (_) => setState(() {}),
            ),
            SizedBox(height: AppSpacing.interGroupSm),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: GlobalSearchScope.values.map((scope) {
                  final selected = _scope == scope;
                  return Padding(
                    padding: EdgeInsets.only(right: AppSpacing.sm),
                    child: ChoiceChip(
                      label: Text(_scopeLabel(scope)),
                      selected: selected,
                      onSelected: (_) => setState(() => _scope = scope),
                    ),
                  );
                }).toList(growable: false),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Expanded(
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
                      title: '圈子',
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
          ],
        ),
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
        return '圈子';
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
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...items.map(
            (item) => ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(item[titleKey]?.toString() ?? ''),
              subtitle: Text(item[subtitleKey]?.toString() ?? ''),
              onTap: onTap == null ? null : () => onTap!(item),
            ),
          ),
        ],
      ),
    );
  }
}
