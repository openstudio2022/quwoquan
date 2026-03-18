import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

/// 子账号管理页面 - 对应 /profile/sub-accounts 路由
///
/// 展示当前 OwnerAccount 下的所有 SubAccount，支持：
/// - 查看与激活切换
/// - 创建新子账号（最多5个）
/// - 删除非主子账号
class SubAccountManagementPage extends ConsumerStatefulWidget {
  const SubAccountManagementPage({super.key});

  @override
  ConsumerState<SubAccountManagementPage> createState() =>
      _SubAccountManagementPageState();
}

class _SubAccountManagementPageState
    extends ConsumerState<SubAccountManagementPage> {
  static const int _maxSubAccounts = 5;
  List<Map<String, dynamic>> _subAccounts = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _loadSubAccounts();
    });
  }

  Future<void> _loadSubAccounts() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(authRepositoryProvider);
      final accounts = await repo.listSubAccounts();
      if (mounted) {
        setState(() {
          _subAccounts = accounts;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  Future<void> _activate(Map<String, dynamic> account) async {
    final subAccountId = account['subAccountId'] as String? ?? '';
    if (subAccountId.isEmpty) return;
    try {
      final repo = ref.read(authRepositoryProvider);
      await repo.activateSubAccount(subAccountId);
      await _loadSubAccounts();
    } catch (e) {
      _showError('${UITextConstants.profileSubAccountSwitchFailed}: $e');
    }
  }

  Future<void> _delete(Map<String, dynamic> account) async {
    final subAccountId = account['subAccountId'] as String? ?? '';
    if (subAccountId.isEmpty) return;

    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text(UITextConstants.profileSubAccountDeleteTitle),
        content: Text(
          UITextConstants.profileSubAccountDeleteConfirmTemplate.replaceFirst(
            '%s',
            '${account['displayName'] ?? ''}',
          ),
        ),
        actions: [
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text(UITextConstants.messageActionDelete),
          ),
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text(UITextConstants.cancel),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      final repo = ref.read(authRepositoryProvider);
      await repo.deleteSubAccount(subAccountId);
      await _loadSubAccounts();
    } catch (e) {
      _showError('${UITextConstants.profileSubAccountDeleteFailed}: $e');
    }
  }

  Future<void> _createNew() async {
    if (_subAccounts.length >= _maxSubAccounts) {
      _showError(
        UITextConstants.profileSubAccountMaxReachedTemplate.replaceFirst(
          '%s',
          '$_maxSubAccounts',
        ),
      );
      return;
    }

    String displayName = '';
    String isolationLevel = 'open';

    await showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => CupertinoAlertDialog(
          title: const Text(UITextConstants.profileSubAccountCreateTitle),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: AppSpacing.md),
              CupertinoTextField(
                placeholder: UITextConstants.profileSubAccountNamePlaceholder,
                onChanged: (v) => displayName = v,
              ),
              const SizedBox(height: AppSpacing.sm),
              CupertinoSegmentedControl<String>(
                children: const <String, Widget>{
                  'open': Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    child: Text(UITextConstants.profileSubAccountOpen),
                  ),
                  'semi': Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    child: Text(UITextConstants.profileSubAccountSemi),
                  ),
                  'strict': Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    child: Text(UITextConstants.profileSubAccountStrict),
                  ),
                },
                groupValue: isolationLevel,
                onValueChanged: (v) {
                  setDialogState(() => isolationLevel = v);
                },
              ),
            ],
          ),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text(UITextConstants.cancel),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () async {
                if (displayName.trim().isEmpty) return;
                Navigator.of(ctx).pop();
                try {
                  final repo = ref.read(authRepositoryProvider);
                  await repo.createSubAccount(
                    displayName: displayName.trim(),
                    isolationLevel: isolationLevel,
                  );
                  await _loadSubAccounts();
                } catch (e) {
                  _showError('${UITextConstants.profileSubAccountCreateFailed}: $e');
                }
              },
              child: const Text(UITextConstants.create),
            ),
          ],
        ),
      ),
    );
  }

  void _showError(String msg) {
    if (!mounted) return;
    showCupertinoDialog(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text(UITextConstants.operationFailed),
        content: Text(msg),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text(UITextConstants.confirm),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      navigationBar: AppNavigationBar(
        middle: const Text(UITextConstants.profileSubAccountManagement),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _subAccounts.length < _maxSubAccounts ? _createNew : null,
          child: const Icon(CupertinoIcons.add),
        ),
      ),
      child: SafeArea(
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_error!, style: const TextStyle(color: AppColors.error)),
            const SizedBox(height: AppSpacing.md),
            CupertinoButton(
              onPressed: _loadSubAccounts,
              child: const Text(UITextConstants.retry),
            ),
          ],
        ),
      );
    }
    if (_subAccounts.isEmpty) {
      return const Center(
        child: Text(
          UITextConstants.profileSubAccountEmpty,
          style: TextStyle(color: CupertinoColors.secondaryLabel),
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      itemCount: _subAccounts.length,
      separatorBuilder: (context, index) => const SizedBox.shrink(),
      itemBuilder: (context, i) => _SubAccountTile(
        account: _subAccounts[i],
        onActivate: () => _activate(_subAccounts[i]),
        onDelete: () => _delete(_subAccounts[i]),
      ),
    );
  }
}

class _SubAccountTile extends StatelessWidget {
  const _SubAccountTile({
    required this.account,
    required this.onActivate,
    required this.onDelete,
  });

  final Map<String, dynamic> account;
  final VoidCallback onActivate;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final displayName = account['displayName'] as String? ?? '';
    final isActive = account['isActive'] as bool? ?? false;
    final isPrimary = account['isPrimary'] as bool? ?? false;
    final isolationLevel = account['isolationLevel'] as String? ?? 'open';

    return GestureDetector(
      onTap: isActive ? null : onActivate,
      child: Container(
        color: CupertinoColors.systemBackground,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.md - AppSpacing.xs,
        ),
        child: Row(
          children: [
            _IsolationBadge(level: isolationLevel),
            const SizedBox(width: AppSpacing.md - AppSpacing.xs),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        displayName,
                        style: const TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (isPrimary) ...[
                        const SizedBox(width: AppSpacing.sm - AppSpacing.xs / 2),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: AppSpacing.sm - AppSpacing.xs / 2,
                            vertical: AppSpacing.xs / 2,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.primaryColor.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.smallBorderRadius,
                            ),
                          ),
                          child: Text(
                            UITextConstants.personaPrimary,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs / 2),
                  Text(
                    _isolationLabel(isolationLevel),
                    style: const TextStyle(
                      fontSize: AppTypography.sm,
                      color: CupertinoColors.secondaryLabel,
                    ),
                  ),
                ],
              ),
            ),
            if (isActive)
              const Icon(
                CupertinoIcons.check_mark,
                color: CupertinoColors.activeBlue,
                size: AppTypography.xxl,
              ),
            if (!isPrimary) ...[
              const SizedBox(width: AppSpacing.sm),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size.square(AppSpacing.minInteractiveSize),
                onPressed: onDelete,
                child: const Icon(
                  CupertinoIcons.delete,
                  size: AppTypography.xl,
                  color: CupertinoColors.destructiveRed,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _isolationLabel(String level) {
    return switch (level) {
      'strict' => UITextConstants.profileSubAccountStrictDescription,
      'semi' => UITextConstants.profileSubAccountSemiDescription,
      _ => UITextConstants.profileSubAccountOpenDescription,
    };
  }
}

class _IsolationBadge extends StatelessWidget {
  const _IsolationBadge({required this.level});
  final String level;

  @override
  Widget build(BuildContext context) {
    final color = switch (level) {
      'strict' => CupertinoColors.systemRed,
      'semi'   => CupertinoColors.systemOrange,
      _        => CupertinoColors.activeBlue,
    };
    final icon = switch (level) {
      'strict' => CupertinoIcons.lock_shield_fill,
      'semi'   => CupertinoIcons.eye_slash_fill,
      _        => CupertinoIcons.person_fill,
    };
    return Container(
      width: AppSpacing.minInteractiveSize,
      height: AppSpacing.minInteractiveSize,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Icon(
        icon,
        color: color,
        size: AppTypography.xxxl,
      ),
    );
  }
}
