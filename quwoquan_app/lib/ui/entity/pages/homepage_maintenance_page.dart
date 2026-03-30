import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class HomepageMaintenancePage extends ConsumerStatefulWidget {
  const HomepageMaintenancePage({super.key, required this.homepageId});

  final String homepageId;

  @override
  ConsumerState<HomepageMaintenancePage> createState() =>
      _HomepageMaintenancePageState();
}

class _HomepageMaintenancePageState
    extends ConsumerState<HomepageMaintenancePage> {
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _subtitleController = TextEditingController();
  final TextEditingController _cityController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();
  final TextEditingController _tagsController = TextEditingController();

  HomepageDetail? _detail;
  bool _isLoading = true;
  bool _isSubmitting = false;
  String? _errorText;

  bool get _hasUnsavedChanges {
    final detail = _detail;
    if (detail == null) {
      return _titleController.text.trim().isNotEmpty ||
          _subtitleController.text.trim().isNotEmpty ||
          _cityController.text.trim().isNotEmpty ||
          _addressController.text.trim().isNotEmpty ||
          _tagsController.text.trim().isNotEmpty;
    }
    return _titleController.text.trim() != detail.title ||
        _subtitleController.text.trim() != (detail.subtitle ?? '') ||
        _cityController.text.trim() != (detail.city ?? '') ||
        _addressController.text.trim() != (detail.address ?? '') ||
        _tagsController.text.trim() != detail.categoryTags.join(' ');
  }

  String get _confirmLabel =>
      (_detail?.claimStatus ?? '') == 'claimed' ? '保存主页信息' : '需先完成认领';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _titleController.dispose();
    _subtitleController.dispose();
    _cityController.dispose();
    _addressController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final canSubmit =
        !_isLoading &&
        !_isSubmitting &&
        (_detail?.claimStatus ?? '') == 'claimed';
    return IosSelectionPageScaffold(
      title: '维护主页',
      onBack: _handleCloseRequest,
      leadingStyle: IosSelectionHeaderLeadingStyle.close,
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.containerLg,
        ),
        children: <Widget>[
          if (_isLoading)
            const Center(child: CupertinoActivityIndicator())
          else ...<Widget>[
            _MaintenanceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    _detail?.title ?? '共享主页',
                    style: const TextStyle(
                      fontSize: AppTypography.iosTitle3,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    (_detail?.claimStatus ?? '') == 'claimed'
                        ? '已认领主页可维护标题、简介、位置与标签，历史内容会继续聚合保留。'
                        : '当前主页尚未完成认领，暂不可维护。',
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    ),
                  ),
                  if (_errorText != null) ...<Widget>[
                    SizedBox(height: AppSpacing.containerSm),
                    Text(
                      _errorText!,
                      style: const TextStyle(color: AppColors.error),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(height: AppSpacing.containerSm),
            _MaintenanceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _MaintenanceLabel('主页名称'),
                  CupertinoTextField(
                    controller: _titleController,
                    enabled: canSubmit,
                    placeholder: '主页名称',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _MaintenanceLabel('一句话简介'),
                  CupertinoTextField(
                    controller: _subtitleController,
                    enabled: canSubmit,
                    placeholder: '简介',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _MaintenanceLabel('城市'),
                  CupertinoTextField(
                    controller: _cityController,
                    enabled: canSubmit,
                    placeholder: '城市',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _MaintenanceLabel('地址'),
                  CupertinoTextField(
                    controller: _addressController,
                    enabled: canSubmit,
                    placeholder: '地址',
                    maxLines: 3,
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _MaintenanceLabel('分类标签'),
                  CupertinoTextField(
                    controller: _tagsController,
                    enabled: canSubmit,
                    placeholder: '用空格分隔，例如 景点 城市地标 赏景',
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
      bottomBar: IosSelectionBottomBar(
        confirmLabel: _confirmLabel,
        confirmEnabled: canSubmit,
        confirmLoading: _isSubmitting,
        onConfirm: _submit,
      ),
    );
  }

  Future<void> _handleCloseRequest() async {
    if (_isSubmitting) {
      return;
    }
    if (!_hasUnsavedChanges) {
      _pop();
      return;
    }
    final discardChanges = await showCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(UITextConstants.unsavedChangesTitle),
        content: const Text(UITextConstants.unsavedChangesMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(UITextConstants.continueEditing),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(UITextConstants.discard),
          ),
        ],
      ),
    );
    if (discardChanges == true && mounted) {
      _pop();
    }
  }

  void _pop() {
    final navigator = Navigator.of(context);
    if (navigator.canPop()) {
      navigator.pop();
    }
  }

  Future<void> _load() async {
    try {
      final detail = await ref
          .read(homepageRepositoryProvider)
          .getHomepageDetail(widget.homepageId);
      if (!mounted) {
        return;
      }
      _titleController.text = detail.title;
      _subtitleController.text = detail.subtitle ?? '';
      _cityController.text = detail.city ?? '';
      _addressController.text = detail.address ?? '';
      _tagsController.text = detail.categoryTags.join(' ');
      setState(() {
        _detail = detail;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isLoading = false;
        _errorText = '主页详情加载失败，请稍后重试';
      });
    }
  }

  Future<void> _submit() async {
    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });
    try {
      await ref
          .read(homepageRepositoryProvider)
          .updateClaimedHomepageBasics(
            homepageId: widget.homepageId,
            draft: HomepageBasicDraft(
              title: _titleController.text.trim(),
              subtitle: _subtitleController.text.trim(),
              city: _cityController.text.trim(),
              address: _addressController.text.trim(),
              categoryTags: _tagsController.text
                  .split(RegExp(r'\s+'))
                  .map((item) => item.trim())
                  .where((item) => item.isNotEmpty)
                  .toList(growable: false),
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, '主页信息已更新');
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorText = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }
}

class _MaintenanceCard extends StatelessWidget {
  const _MaintenanceCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        border: Border.all(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ),
        ),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: child,
    );
  }
}

class _MaintenanceLabel extends StatelessWidget {
  const _MaintenanceLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          color: CupertinoColors.secondaryLabel.resolveFrom(context),
        ),
      ),
    );
  }
}
