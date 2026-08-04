import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/application/entity/homepage_view_data.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_action_observability.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_write_access.dart';

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
  bool _didStartLoad = false;
  bool _authResumeScheduled = false;
  UiErrorSemantic? _pageErrorSemantic;
  UiErrorSemantic? _permissionSemantic;
  UiErrorSemantic? _submitErrorSemantic;
  String? _titleValidationMessage;

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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_gateEntryAndLoad());
    });
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
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      if (next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated)) {
        _scheduleAuthContinuationResume();
      }
    });
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scheduleAuthContinuationResume();
      });
    }

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final blockingSemantic = _permissionSemantic ?? _pageErrorSemantic;
    if (blockingSemantic != null && !_isLoading) {
      return IosSelectionPageScaffold(
        title: ObjectHomepageText.homepageMaintainAction,
        onBack: _safeReturn,
        leadingStyle: IosSelectionHeaderLeadingStyle.close,
        backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
        body: AppPageErrorState(
          semantic: _permissionSemantic == null
              ? ensureRetryUiErrorSemantic(blockingSemantic)
              : blockingSemantic,
          onRecovery: _permissionSemantic == null
              ? _handlePageErrorAction
              : _handlePermissionAction,
        ),
      );
    }

    final canSubmit = !_isLoading && !_isSubmitting && _detail != null;
    return IosSelectionPageScaffold(
      title: ObjectHomepageText.homepageMaintainAction,
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
            AppRequestFeedback.section()
          else ...<Widget>[
            const IosSelectionSectionHeader(
              title: ObjectHomepageText.homepageFormOverviewSection,
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
            ),
            IosSelectionSection(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.containerMd),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      _detail?.title ??
                          ObjectHomepageText.homepageClaimHomepageFallback,
                      style: const TextStyle(
                        fontSize: AppTypography.iosTitle3,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      ObjectHomepageText.homepageMaintenanceOwnedDescription,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                    if (_submitErrorSemantic != null) ...<Widget>[
                      SizedBox(height: AppSpacing.containerSm),
                      AppFormErrorCard(
                        semantic: _submitErrorSemantic!,
                        onAction: _handleSubmitErrorAction,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            SizedBox(height: AppSpacing.containerSm),
            const IosSelectionSectionHeader(
              title: ObjectHomepageText.homepageFormDetailsSection,
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
            ),
            IosSelectionSection(
              child: Column(
                children: <Widget>[
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageMaintenanceNameLabel,
                    validationMessage: _titleValidationMessage,
                    child: IosSelectionTextField(
                      controller: _titleController,
                      enabled: canSubmit,
                      placeholder:
                          ObjectHomepageText.homepageMaintenanceNamePlaceholder,
                      onChanged: (_) {
                        if (_titleValidationMessage != null) {
                          setState(() => _titleValidationMessage = null);
                        }
                      },
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageMaintenanceSubtitleLabel,
                    child: IosSelectionTextField(
                      controller: _subtitleController,
                      enabled: canSubmit,
                      placeholder: ObjectHomepageText
                          .homepageMaintenanceSubtitlePlaceholder,
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageMaintenanceCityLabel,
                    child: IosSelectionTextField(
                      controller: _cityController,
                      enabled: canSubmit,
                      placeholder:
                          ObjectHomepageText.homepageMaintenanceCityPlaceholder,
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageMaintenanceAddressLabel,
                    child: IosSelectionTextField(
                      controller: _addressController,
                      enabled: canSubmit,
                      placeholder: ObjectHomepageText
                          .homepageMaintenanceAddressPlaceholder,
                      maxLines: 3,
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageMaintenanceTagsLabel,
                    child: IosSelectionTextField(
                      controller: _tagsController,
                      enabled: canSubmit,
                      placeholder:
                          ObjectHomepageText.homepageMaintenanceTagsPlaceholder,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
      bottomBar: IosSelectionBottomBar(
        confirmLabel: ObjectHomepageText.homepageMaintenanceSave,
        confirmEnabled: canSubmit,
        confirmLoading: _isSubmitting,
        onConfirm: _submit,
      ),
    );
  }

  Future<void> _gateEntryAndLoad() async {
    final allowed = await requireHomepageWriteAccess(
      ref,
      context,
      action: HomepageWriteContinuationAction.maintenance,
      homepageId: widget.homepageId,
      dismissFallback: AppRoutePaths.homepageDetail(id: widget.homepageId),
    );
    if (allowed && mounted) {
      await _loadOnce();
    }
  }

  void _scheduleAuthContinuationResume({int remainingFrames = 30}) {
    if (!mounted || !AuthGate.isAuthenticated(ref) || _authResumeScheduled) {
      return;
    }
    _authResumeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _authResumeScheduled = false;
      if (!mounted || !AuthGate.isAuthenticated(ref)) {
        return;
      }
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) {
        if (remainingFrames > 0) {
          _scheduleAuthContinuationResume(remainingFrames: remainingFrames - 1);
        }
        return;
      }
      final pending = takeHomepageWriteContinuation(
        ref,
        action: HomepageWriteContinuationAction.maintenance,
        homepageId: widget.homepageId,
      );
      if (pending == null) {
        unawaited(_loadOnce());
        return;
      }
      if (pending.submitAfterLogin) {
        unawaited(_submit());
      } else {
        unawaited(_loadOnce());
      }
    });
  }

  Future<void> _loadOnce() async {
    if (_didStartLoad) {
      return;
    }
    _didStartLoad = true;
    await _load();
  }

  Future<bool> _ensureSubmitAuthentication() {
    return requireHomepageWriteAccess(
      ref,
      context,
      action: HomepageWriteContinuationAction.maintenance,
      homepageId: widget.homepageId,
      dismissFallback: AppRoutePaths.homepageDetail(id: widget.homepageId),
      submitAfterLogin: true,
    );
  }

  Future<void> _handleCloseRequest() async {
    if (_isSubmitting) {
      return;
    }
    if (!_hasUnsavedChanges) {
      _safeReturn();
      return;
    }
    final discardChanges = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(CreationText.unsavedChangesTitle),
        content: const Text(CreationText.unsavedChangesMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(CreationText.continueEditing),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(CreationText.discard),
          ),
        ],
      ),
    );
    if (discardChanges == true && mounted) {
      _safeReturn();
    }
  }

  void _safeReturn() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.homepageDetail(id: widget.homepageId));
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _pageErrorSemantic = null;
      _permissionSemantic = null;
    });
    try {
      final detail = await ref
          .read(homepageQueryProvider)
          .getHomepageDetail(widget.homepageId);
      final activeContext = await ref.read(activePersonaContextProvider.future);
      if (!mounted) {
        return;
      }
      final ownerUserId = (detail.ownerUserId ?? '').trim();
      final ownerPersonaId = (detail.ownerPersonaId ?? '').trim();
      final isOwner =
          (detail.claimStatus ?? '').trim() == 'claimed' &&
          ((ownerUserId.isNotEmpty &&
                  ownerUserId == activeContext.ownerUserId.trim()) ||
              (ownerPersonaId.isNotEmpty &&
                  ownerPersonaId == activeContext.personaId.trim()));
      if (!isOwner) {
        setState(() {
          _detail = detail;
          _isLoading = false;
          _permissionSemantic = AppUserRecoveryContract.semanticFor(
            group: AppUserRecoveryGroup.noAccess,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            presentation: UiErrorPresentation.gateCard,
          );
        });
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
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isLoading = false;
        _pageErrorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    }
  }

  Future<void> _submit() async {
    if (!await _ensureSubmitAuthentication() || !mounted) {
      return;
    }
    if (_permissionSemantic != null || _detail == null) {
      return;
    }
    if (_titleController.text.trim().isEmpty) {
      setState(() {
        _titleValidationMessage =
            ObjectHomepageText.homepageMaintenanceNameRequired;
      });
      return;
    }
    setState(() {
      _isSubmitting = true;
      _submitErrorSemantic = null;
    });
    final startedAt = DateTime.now();
    try {
      await ref
          .read(homepageCommandWriterProvider)
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
      await trackHomepageProductAction(
        ref,
        action: 'maintenance_submit',
        pageName: 'homepageMaintenance',
        result: 'success',
        startedAt: startedAt,
        homepageId: widget.homepageId,
      );
      if (!mounted) {
        return;
      }
      AppToast.show(context, ObjectHomepageText.homepageMaintenanceUpdated);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _submitErrorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.form,
        );
      });
      await trackHomepageProductAction(
        ref,
        action: 'maintenance_submit',
        pageName: 'homepageMaintenance',
        result: 'failure',
        startedAt: startedAt,
        homepageId: widget.homepageId,
        error: error,
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  Future<void> _handleSubmitErrorAction(UiErrorAction action) async {
    if (_submitErrorSemantic?.sourceCode ==
        EntityErrorCode.versionConflict.code) {
      if (mounted) {
        setState(() => _submitErrorSemantic = null);
      }
      await _load();
      return;
    }
    switch (action.type) {
      case UiErrorActionType.retry:
      case UiErrorActionType.resubmit:
        await _submit();
        return;
      case UiErrorActionType.dismiss:
        if (mounted) {
          setState(() => _submitErrorSemantic = null);
        }
        return;
      case UiErrorActionType.openSettings:
      case UiErrorActionType.openUpdate:
      case UiErrorActionType.login:
        return;
    }
  }

  Future<UiRecoveryOutcome> _handlePageErrorAction(UiErrorAction action) async {
    switch (action.type) {
      case UiErrorActionType.retry:
      case UiErrorActionType.resubmit:
        await _load();
        return _pageErrorSemantic == null
            ? UiRecoveryOutcome.recovered
            : UiRecoveryOutcome.stillBlocked;
      case UiErrorActionType.dismiss:
        _safeReturn();
        return UiRecoveryOutcome.handedOff;
      case UiErrorActionType.openSettings:
      case UiErrorActionType.openUpdate:
      case UiErrorActionType.login:
        return UiRecoveryOutcome.cancelled;
    }
  }

  Future<UiRecoveryOutcome> _handlePermissionAction(
    UiErrorAction action,
  ) async {
    _safeReturn();
    return UiRecoveryOutcome.handedOff;
  }
}
