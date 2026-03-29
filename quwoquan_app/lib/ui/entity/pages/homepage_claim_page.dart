import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class HomepageClaimPage extends ConsumerStatefulWidget {
  const HomepageClaimPage({super.key, required this.homepageId});

  final String homepageId;

  @override
  ConsumerState<HomepageClaimPage> createState() => _HomepageClaimPageState();
}

class _HomepageClaimPageState extends ConsumerState<HomepageClaimPage> {
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _licenseController = TextEditingController();
  final TextEditingController _idFrontController = TextEditingController();
  final TextEditingController _idBackController = TextEditingController();
  final TextEditingController _noteController = TextEditingController();

  HomepageDetail? _detail;
  bool _isLoading = true;
  bool _isSubmitting = false;
  String? _errorText;
  String _claimTier = 'basic';

  bool get _hasUnsavedChanges =>
      _claimTier != 'basic' ||
      _phoneController.text.trim().isNotEmpty ||
      _licenseController.text.trim().isNotEmpty ||
      _idFrontController.text.trim().isNotEmpty ||
      _idBackController.text.trim().isNotEmpty ||
      _noteController.text.trim().isNotEmpty;

  String get _confirmLabel {
    if ((_detail?.claimStatus ?? '') == 'claimed') {
      return '该主页已被认领';
    }
    if ((_detail?.status ?? '') == 'offline') {
      return '主页已下线';
    }
    return '提交认领申请';
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _licenseController.dispose();
    _idFrontController.dispose();
    _idBackController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final canSubmit =
        !_isLoading &&
        !_isSubmitting &&
        (_detail?.status ?? '') != 'offline' &&
        (_detail?.claimStatus ?? '') != 'claimed';
    return IosSelectionPageScaffold(
      title: '认领主页',
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
            _EntityFormCard(
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
                    (_detail?.status ?? '') == 'offline'
                        ? '该主页已下线，仅保留历史内容，当前不可继续认领。'
                        : (_detail?.claimStatus ?? '') == 'claimed'
                        ? '该主页已被认领，如信息有误可通过状态上报反馈。'
                        : '提交后会进入审核，审核通过后即可维护主页基本信息。',
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
            _EntityFormCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _EntityFieldLabel('认领等级'),
                  CupertinoSlidingSegmentedControl<String>(
                    groupValue: _claimTier,
                    children: const <String, Widget>{
                      'basic': Padding(
                        padding: EdgeInsets.symmetric(horizontal: 12),
                        child: Text('基础'),
                      ),
                      'verified': Padding(
                        padding: EdgeInsets.symmetric(horizontal: 12),
                        child: Text('认证'),
                      ),
                    },
                    onValueChanged: (value) {
                      if (!canSubmit || value == null) {
                        return;
                      }
                      setState(() {
                        _claimTier = value;
                      });
                    },
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _EntityFieldLabel('联系电话'),
                  CupertinoTextField(
                    controller: _phoneController,
                    enabled: canSubmit,
                    keyboardType: TextInputType.phone,
                    placeholder: '用于审核联系',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _EntityFieldLabel('营业执照材料链接'),
                  CupertinoTextField(
                    controller: _licenseController,
                    enabled: canSubmit,
                    placeholder: '可选，上传后填入链接',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _EntityFieldLabel('身份证正面材料链接'),
                  CupertinoTextField(
                    controller: _idFrontController,
                    enabled: canSubmit,
                    placeholder: '可选，上传后填入链接',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _EntityFieldLabel('身份证反面材料链接'),
                  CupertinoTextField(
                    controller: _idBackController,
                    enabled: canSubmit,
                    placeholder: '可选，上传后填入链接',
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  _EntityFieldLabel('补充说明'),
                  CupertinoTextField(
                    controller: _noteController,
                    enabled: canSubmit,
                    placeholder: '说明你与该主页的关系',
                    maxLines: 4,
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
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      AppToast.show(context, '请填写联系电话');
      return;
    }
    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });
    try {
      await ref
          .read(homepageRepositoryProvider)
          .createHomepageClaimRequest(
            homepageId: widget.homepageId,
            draft: HomepageClaimRequestDraft(
              claimTier: _claimTier,
              contactPhone: phone,
              businessLicenseUrl: _licenseController.text.trim(),
              identityCardFrontUrl: _idFrontController.text.trim(),
              identityCardBackUrl: _idBackController.text.trim(),
              note: _noteController.text.trim(),
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, '认领申请已提交');
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

class _EntityFormCard extends StatelessWidget {
  const _EntityFormCard({required this.child});

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

class _EntityFieldLabel extends StatelessWidget {
  const _EntityFieldLabel(this.label);

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
