import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 群管理页 — 群主/管理员专属管理入口
class GroupManagePage extends ConsumerStatefulWidget {
  const GroupManagePage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<GroupManagePage> createState() => _GroupManagePageState();
}

class _GroupManagePageState extends ConsumerState<GroupManagePage> {
  bool _qrCodeJoinEnabled = true;
  bool _joinRequiresApproval = false;
  bool _nameEditableByAdminOnly = false;
  final String _currentUserRole = 'owner';

  bool get _isOwner => _currentUserRole == 'owner';

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final settings = await repo.getGroupSettings(widget.conversationId);
      if (mounted) {
        setState(() {
          _qrCodeJoinEnabled =
              settings['qrCodeJoinEnabled'] as bool? ?? true;
          _joinRequiresApproval =
              settings['joinRequiresApproval'] as bool? ?? false;
          _nameEditableByAdminOnly =
              settings['nameEditableByAdminOnly'] as bool? ?? false;
        });
      }
    } catch (_) {}
  }

  Future<void> _updateSetting(String key, bool value) async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      await repo.updateGroupSettings(
        widget.conversationId,
        {key: value},
      );
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final blockSurface = SettingsSemanticConstants.blockBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final secondaryColor = SettingsSemanticConstants.secondaryColor(isDark);
    final dividerColor = SettingsSemanticConstants.dividerColor(isDark);

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        backgroundColor: blockSurface,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.groupManagement,
          style: TextStyle(
            color: fgPrimary,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w600,
          ),
        ),
        border: Border(bottom: BorderSide(color: dividerColor, width: AppSpacing.one)),
      ),
      body: ListView(
        children: [
          _section(
            blockSurface: blockSurface,
            isDark: isDark,
            child: _buildSwitchRow(
              label: UITextConstants.qrCodeJoin,
              value: _qrCodeJoinEnabled,
              isDark: isDark,
              onChanged: (v) {
                setState(() => _qrCodeJoinEnabled = v);
                _updateSetting('qrCodeJoinEnabled', v);
              },
            ),
          ),
          SizedBox(height: SettingsSemanticConstants.blockSpacing),
          _section(
            blockSurface: blockSurface,
            isDark: isDark,
            child: Column(
              children: [
                _buildSwitchRow(
                  label: UITextConstants.joinRequiresApproval,
                  value: _joinRequiresApproval,
                  isDark: isDark,
                  onChanged: (v) {
                    setState(() => _joinRequiresApproval = v);
                    _updateSetting('joinRequiresApproval', v);
                  },
                ),
                _divider(isDark),
                _buildSwitchRow(
                  label: UITextConstants.nameEditableByAdminOnly,
                  value: _nameEditableByAdminOnly,
                  isDark: isDark,
                  onChanged: (v) {
                    setState(() => _nameEditableByAdminOnly = v);
                    _updateSetting('nameEditableByAdminOnly', v);
                  },
                ),
              ],
            ),
          ),
          if (_isOwner) ...[
            SizedBox(height: SettingsSemanticConstants.blockSpacing),
            _section(
              blockSurface: blockSurface,
              isDark: isDark,
              child: Column(
                children: [
                  _buildNavRow(
                    label: UITextConstants.transferOwnership,
                    fgPrimary: fgPrimary,
                    secondaryColor: secondaryColor,
                    onTap: () => context.push(
                      '/chat/${widget.conversationId}/transfer-ownership',
                    ),
                  ),
                  _divider(isDark),
                  _buildNavRow(
                    label: UITextConstants.groupAdmins,
                    fgPrimary: fgPrimary,
                    secondaryColor: secondaryColor,
                    onTap: () => context.push(
                      '/chat/${widget.conversationId}/admins',
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(height: SettingsSemanticConstants.blockSpacing),
            _section(
              blockSurface: blockSurface,
              isDark: isDark,
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () {
                    showCupertinoDialog<void>(
                      context: context,
                      builder: (_) => CupertinoAlertDialog(
                        title: Text(UITextConstants.dissolveGroupChat),
                        content: const Text('解散后所有成员将被移出群聊，此操作不可撤销。'),
                        actions: [
                          CupertinoDialogAction(
                            child: Text(UITextConstants.cancel),
                            onPressed: () => Navigator.pop(context),
                          ),
                          CupertinoDialogAction(
                            isDestructiveAction: true,
                            child: Text(UITextConstants.confirm),
                            onPressed: () {
                              Navigator.pop(context);
                            },
                          ),
                        ],
                      ),
                    );
                  },
                  child: SizedBox(
                    width: double.infinity,
                    height: AppSpacing.buttonHeight,
                    child: Center(
                      child: Text(
                        UITextConstants.dissolveGroupChat,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w500,
                          color: SettingsSemanticConstants.exitActionColor(isDark),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _section({
    required Color blockSurface,
    required bool isDark,
    required Widget child,
  }) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: SettingsSemanticConstants.blockHorizontalPadding,
        vertical: SettingsSemanticConstants.sectionVerticalPadding,
      ),
      decoration: BoxDecoration(
        color: blockSurface,
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(isDark),
        ),
      ),
      child: child,
    );
  }

  Widget _divider(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.xs / 2),
      child: Divider(
        height: AppSpacing.one,
        thickness: SettingsSemanticConstants.dividerThickness,
        color: SettingsSemanticConstants.dividerColor(isDark),
      ),
    );
  }

  Widget _buildSwitchRow({
    required String label,
    required bool value,
    required bool isDark,
    required ValueChanged<bool> onChanged,
  }) {
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    return ConstrainedBox(
      constraints: BoxConstraints(minHeight: AppSpacing.buttonHeight),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(fontSize: AppTypography.lg, color: fgPrimary),
              ),
            ),
            CupertinoSwitch(
              value: value,
              onChanged: onChanged,
              activeColor: SettingsSemanticConstants.switchActiveTrackColor,
              trackColor: SettingsSemanticConstants.switchInactiveTrackColor(isDark),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNavRow({
    required String label,
    required Color fgPrimary,
    required Color secondaryColor,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: AppSpacing.buttonHeight),
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    color: fgPrimary,
                  ),
                ),
              ),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconMedium,
                color: secondaryColor,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
