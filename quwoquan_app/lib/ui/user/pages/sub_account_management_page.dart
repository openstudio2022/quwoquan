import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

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
  List<PersonaManagementItemViewData> _subAccounts = const [];
  PersonaManagementQuotaViewData? _quota;
  ActivePersonaContextViewData? _activeContext;
  bool _loading = true;
  String? _error;

  int get _maxSubAccounts => _quota?.maxSubAccounts ?? 5;

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
      final repo = ref.read(userRepositoryProvider);
      final summary = await repo.getPersonaManagementSummary();
      if (mounted) {
        setState(() {
          _subAccounts = summary.items;
          _quota = summary.quota;
          _activeContext = summary.activeContext;
          _loading = false;
        });
      }
    } catch (e) {
      try {
        final repo = ref.read(userRepositoryProvider);
        final accounts = await repo.listSubAccounts();
        final activeContext = await repo.getActivePersonaContext();
        if (mounted) {
          setState(() {
            _subAccounts = accounts;
            _quota = PersonaManagementQuotaViewData(
              maxSubAccounts: 5,
              usedSubAccounts: accounts.length,
            );
            _activeContext = activeContext;
            _loading = false;
          });
        }
      } catch (_) {
        if (mounted) {
          setState(() {
            _error = e.toString();
            _loading = false;
          });
        }
      }
    }
  }

  Future<void> _activate(PersonaManagementItemViewData account) async {
    final subAccountId = account.subAccountId;
    if (subAccountId.isEmpty) return;
    try {
      final repo = ref.read(userRepositoryProvider);
      await repo.activateSubAccount(subAccountId);
      await _loadSubAccounts();
    } catch (e) {
      _showError('${UITextConstants.profileSubAccountSwitchFailed}: $e');
    }
  }

  Future<void> _delete(PersonaManagementItemViewData account) async {
    final subAccountId = account.subAccountId;
    if (subAccountId.isEmpty) return;

    final repo = ref.read(userRepositoryProvider);
    PersonaLifecycleGuardViewData? guard;
    try {
      guard = await repo.getSubAccountLifecycleGuard(subAccountId);
    } catch (_) {
      guard = null;
    }
    if (guard != null && !guard.canDelete) {
      if (guard.canRetire) {
        final retire = await showCupertinoDialog<bool>(
          context: context,
          builder: (ctx) => CupertinoAlertDialog(
            title: const Text('退役子账号'),
            content: Text(
              guard!.message.isNotEmpty
                  ? guard.message
                  : '该子账号仍有关联历史，需先退役后再删除。',
            ),
            actions: [
              CupertinoDialogAction(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text(UITextConstants.cancel),
              ),
              CupertinoDialogAction(
                isDefaultAction: true,
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('退役'),
              ),
            ],
          ),
        );
        if (retire == true) {
          try {
            await repo.retireSubAccount(subAccountId);
            await _loadSubAccounts();
          } catch (e) {
            _showError('退役失败: $e');
          }
        }
        return;
      }
      _showError(
        guard.message.isNotEmpty ? guard.message : UITextConstants.profileSubAccountDeleteFailed,
      );
      return;
    }

    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text(UITextConstants.profileSubAccountDeleteTitle),
        content: Text(
          UITextConstants.profileSubAccountDeleteConfirmTemplate.replaceFirst(
            '%s',
            account.displayName,
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
      await repo.deleteEmptySubAccount(subAccountId);
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
                  final repo = ref.read(userRepositoryProvider);
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
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(
          context,
        ).withValues(alpha: 0.94),
        border: Border(
          bottom: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.28),
            width: AppSpacing.hairline,
          ),
        ),
        middle: Text(
          UITextConstants.profileSubAccountManagement,
          style: TextStyle(
            fontSize: AppTypography.iosNavTitle,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _subAccounts.length < _maxSubAccounts ? _createNew : null,
          child: Icon(
            CupertinoIcons.add,
            color: AppColors.iosAccent(context),
          ),
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

    return ListView(
      padding: EdgeInsets.only(
        top: AppSpacing.containerSm,
        bottom: MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg,
      ),
      children: <Widget>[
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
          child: ProfileIosSectionCard(
            child: Text(
              '当前 Owner 下共有 ${_subAccounts.length}/$_maxSubAccounts 个子账号。'
              '当前激活：${_activeContext?.displayName ?? '未同步'}。'
              '可在此切换当前激活账号，或管理账号隔离级别。',
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
                height: 1.35,
              ),
            ),
          ),
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        ProfileIosGroupedSection(
          header: '子账号列表',
          children: _subAccounts
              .map(
                (account) => _SubAccountTile(
                  account: account,
                  onActivate: () => _activate(account),
                  onDelete: () => _delete(account),
                ),
              )
              .toList(growable: false),
        ),
      ],
    );
  }
}

class _SubAccountTile extends StatelessWidget {
  const _SubAccountTile({
    required this.account,
    required this.onActivate,
    required this.onDelete,
  });

  final PersonaManagementItemViewData account;
  final VoidCallback onActivate;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final displayName = account.displayName;
    final isActive = account.isActive;
    final isPrimary = account.isPrimary;
    final isolationLevel = account.isolationLevel;

    return ProfileIosGroupedCell(
      leading: _IsolationBadge(level: isolationLevel),
      title: displayName,
      subtitle: _isolationLabel(isolationLevel),
      onTap: isActive ? null : onActivate,
      showChevron: !isActive,
      minHeight: 62,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (isPrimary)
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs / 2,
              ),
              decoration: BoxDecoration(
                color: AppColors.iosTintedFill(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              ),
              child: Text(
                UITextConstants.personaPrimary,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: AppColors.iosAccent(context),
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
          if (isActive) ...<Widget>[
            if (isPrimary) const SizedBox(width: AppSpacing.sm),
            const Icon(
              CupertinoIcons.check_mark_circled_solid,
              color: CupertinoColors.activeBlue,
              size: AppSpacing.iconMedium,
            ),
          ],
          if (!isPrimary) ...<Widget>[
            SizedBox(width: AppSpacing.sm),
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(AppSpacing.minInteractiveSize),
              onPressed: onDelete,
              child: const Icon(
                CupertinoIcons.delete,
                size: AppSpacing.iconSmall,
                color: CupertinoColors.destructiveRed,
              ),
            ),
          ],
        ],
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
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Icon(
        icon,
        color: color,
        size: AppSpacing.iconMedium,
      ),
    );
  }
}
