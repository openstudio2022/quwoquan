import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class HomepageStatusReportPage extends ConsumerStatefulWidget {
  const HomepageStatusReportPage({super.key, required this.homepageId});

  final String homepageId;

  @override
  ConsumerState<HomepageStatusReportPage> createState() =>
      _HomepageStatusReportPageState();
}

class _HomepageStatusReportPageState
    extends ConsumerState<HomepageStatusReportPage> {
  static const List<_ReportReasonOption> _reasons = <_ReportReasonOption>[
    _ReportReasonOption('offline', '已停业 / 已关闭'),
    _ReportReasonOption('incorrect_info', '信息不准确'),
    _ReportReasonOption('duplicate_entry', '重复主页'),
    _ReportReasonOption('inactive', '长期失效'),
  ];

  final TextEditingController _descriptionController = TextEditingController();

  HomepageDetail? _detail;
  bool _isLoading = true;
  bool _isSubmitting = false;
  String? _errorText;
  String _reason = 'offline';

  bool get _hasUnsavedChanges =>
      _reason != _reasons.first.value ||
      _descriptionController.text.trim().isNotEmpty;

  String get _confirmLabel =>
      (_detail?.status ?? '') == 'offline' ? '主页已下线' : '提交状态上报';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _descriptionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final canSubmit =
        !_isLoading && !_isSubmitting && (_detail?.status ?? '') != 'offline';
    return IosSelectionPageScaffold(
      title: '状态上报',
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
            _ReportCard(
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
                        ? '该主页已经下线，历史内容会继续保留供浏览。'
                        : '如果主页信息失效、重复或长期停用，可以发起状态上报。',
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
            _ReportCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '选择原因',
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  for (var i = 0; i < _reasons.length; i++) ...<Widget>[
                    if (i > 0) const Divider(height: AppSpacing.one),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: canSubmit
                          ? () {
                              setState(() {
                                _reason = _reasons[i].value;
                              });
                            }
                          : null,
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          vertical: AppSpacing.containerSm,
                        ),
                        child: Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                _reasons[i].label,
                                style: const TextStyle(
                                  fontSize: AppTypography.iosBody,
                                  fontWeight: AppTypography.medium,
                                ),
                              ),
                            ),
                            Icon(
                              _reason == _reasons[i].value
                                  ? CupertinoIcons.check_mark_circled_solid
                                  : CupertinoIcons.circle,
                              color: _reason == _reasons[i].value
                                  ? AppColors.primaryColor
                                  : CupertinoColors.secondaryLabel.resolveFrom(
                                      context,
                                    ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  SizedBox(height: AppSpacing.containerSm),
                  Text(
                    '补充说明',
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  CupertinoTextField(
                    controller: _descriptionController,
                    enabled: canSubmit,
                    placeholder: '补充说明当前状态，例如已停业、地址变更或重复来源',
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
    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });
    try {
      await ref
          .read(homepageRepositoryProvider)
          .createHomepageStatusReport(
            homepageId: widget.homepageId,
            draft: HomepageStatusReportDraft(
              reason: _reason,
              description: _descriptionController.text.trim(),
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, '状态上报已提交');
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

class _ReportReasonOption {
  const _ReportReasonOption(this.value, this.label);

  final String value;
  final String label;
}

class _ReportCard extends StatelessWidget {
  const _ReportCard({required this.child});

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
