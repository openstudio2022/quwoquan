import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

/// 群主转让页 — 选择成员后确认弹窗
class TransferOwnershipPage extends ConsumerStatefulWidget {
  const TransferOwnershipPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<TransferOwnershipPage> createState() =>
      _TransferOwnershipPageState();
}

class _TransferOwnershipPageState extends ConsumerState<TransferOwnershipPage> {
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onMemberSelected(Map<String, dynamic> member) {
    final name =
        member['displayName'] as String? ?? member['name'] as String? ?? '';

    showCupertinoDialog<void>(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        content: Text(
          '${UITextConstants.transferOwnershipConfirmPrefix}'
          '$name'
          '${UITextConstants.transferOwnershipConfirmSuffix}',
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(UITextConstants.cancel),
            onPressed: () => Navigator.pop(context),
          ),
          CupertinoDialogAction(
            child: Text(UITextConstants.confirm),
            onPressed: () async {
              Navigator.pop(context);
              try {
                await ref
                    .read(
                      conversationMembersProvider(
                        widget.conversationId,
                      ).notifier,
                    )
                    .transferOwnership(member['userId'] as String? ?? '');
                if (mounted) context.pop();
              } catch (_) {}
            },
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final bgColor = SettingsSemanticConstants.pageBackground(isDark);
    final toolbarBg = SettingsSemanticConstants.selectionToolbarBackground(
      isDark,
    );

    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );

    // 排除群主（当前用户）自身
    final candidates = membersState.members
        .where((m) => m['role'] != 'owner' && m['isCurrentUser'] != true)
        .toList();

    final filtered = _searchQuery.isEmpty
        ? candidates
        : candidates.where((m) {
            final name = (m['displayName'] ?? m['name'] ?? '') as String;
            return name.toLowerCase().contains(_searchQuery.toLowerCase());
          }).toList();

    return AppScaffold(
      backgroundColor: bgColor,
      navigationBar: AppNavigationBar(
        backgroundColor: toolbarBg,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.selectNewOwner,
          style: TextStyle(
            color: fgPrimary,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w600,
          ),
        ),
        border: Border(
          bottom: BorderSide(
            color: SettingsSemanticConstants.dividerColor(isDark),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.sm,
              AppSpacing.containerMd,
              AppSpacing.sm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: UITextConstants.search,
              onChanged: (v) => setState(() => _searchQuery = v),
            ),
          ),
          Expanded(
            child: membersState.isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          color: SettingsSemanticConstants.blockBackground(
                            isDark,
                          ),
                          borderRadius: BorderRadius.circular(
                            SettingsSemanticConstants.selectionCardBorderRadius,
                          ),
                          border: Border.all(
                            color: SettingsSemanticConstants.blockBorderColor(
                              isDark,
                            ),
                          ),
                        ),
                        child: Column(
                          children: [
                            for (var i = 0; i < filtered.length; i++) ...[
                              Builder(
                                builder: (context) {
                                  final m = filtered[i];
                                  final name =
                                      m['displayName'] as String? ??
                                      m['name'] as String? ??
                                      '';
                                  final avatar =
                                      m['avatarUrl'] as String? ??
                                      m['avatar'] as String? ??
                                      '';
                                  return CupertinoListTile(
                                    backgroundColor: Colors.transparent,
                                    onTap: () => _onMemberSelected(m),
                                    padding: EdgeInsets.symmetric(
                                      horizontal: SettingsSemanticConstants
                                          .blockHorizontalPadding,
                                      vertical: AppSpacing.sm,
                                    ),
                                    leading: RoundedSquareAvatar(
                                      size: AppSpacing.largeButtonSize,
                                      imageUrl: avatar,
                                      name: name,
                                      backgroundColor:
                                          SettingsSemanticConstants.blockBackground(
                                            isDark,
                                          ),
                                    ),
                                    title: Text(
                                      name,
                                      style: TextStyle(
                                        fontSize: AppTypography.lg,
                                        color: fgPrimary,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    trailing: Icon(
                                      CupertinoIcons.chevron_forward,
                                      size: AppSpacing.iconMedium,
                                      color:
                                          SettingsSemanticConstants.selectionChevronColor(
                                            isDark,
                                          ),
                                    ),
                                  );
                                },
                              ),
                              if (i < filtered.length - 1)
                                Container(
                                  height: SettingsSemanticConstants
                                      .dividerThickness,
                                  margin: EdgeInsets.only(
                                    left:
                                        SettingsSemanticConstants
                                            .blockHorizontalPadding +
                                        AppSpacing.largeButtonSize +
                                        AppSpacing.interGroupSm,
                                    right: SettingsSemanticConstants
                                        .blockHorizontalPadding,
                                  ),
                                  color: SettingsSemanticConstants.dividerColor(
                                    isDark,
                                  ),
                                ),
                            ],
                          ],
                        ),
                      ),
                      if (filtered.isEmpty)
                        Padding(
                          padding: EdgeInsets.only(top: AppSpacing.xl),
                          child: Center(
                            child: Text(
                              '暂无匹配成员',
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                color: fgSecondary,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
