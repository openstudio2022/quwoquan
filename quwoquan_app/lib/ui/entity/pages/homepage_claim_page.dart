import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/application/entity/homepage_view_data.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_action_observability.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_write_access.dart';

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
  bool _didStartLoad = false;
  bool _authResumeScheduled = false;
  UiErrorSemantic? _pageErrorSemantic;
  UiErrorSemantic? _submitErrorSemantic;
  String? _phoneValidationMessage;
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
      return ObjectHomepageText.homepageClaimAlreadyClaimed;
    }
    if ((_detail?.status ?? '') == 'offline') {
      return ObjectHomepageText.homepageClaimHomepageOffline;
    }
    return ObjectHomepageText.homepageClaimSubmit;
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
    _phoneController.dispose();
    _licenseController.dispose();
    _idFrontController.dispose();
    _idBackController.dispose();
    _noteController.dispose();
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
    if (_pageErrorSemantic != null && !_isLoading) {
      return IosSelectionPageScaffold(
        title: ObjectHomepageText.homepageClaimAction,
        onBack: _handleCloseRequest,
        leadingStyle: IosSelectionHeaderLeadingStyle.close,
        backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
        body: AppPageErrorState(
          semantic: ensureRetryUiErrorSemantic(_pageErrorSemantic!),
          onRecovery: _handlePageErrorAction,
        ),
      );
    }
    final canSubmit =
        !_isLoading &&
        !_isSubmitting &&
        (_detail?.status ?? '') != 'offline' &&
        (_detail?.claimStatus ?? '') != 'claimed';
    return IosSelectionPageScaffold(
      title: ObjectHomepageText.homepageClaimAction,
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
                      (_detail?.status ?? '') == 'offline'
                          ? ObjectHomepageText.homepageClaimOfflineDescription
                          : (_detail?.claimStatus ?? '') == 'claimed'
                          ? ObjectHomepageText.homepageClaimClaimedDescription
                          : ObjectHomepageText.homepageClaimReviewDescription,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
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
              title: ObjectHomepageText.homepageClaimMaterialsSection,
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
            ),
            IosSelectionSection(
              child: Column(
                children: <Widget>[
                  Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.containerSm,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          ObjectHomepageText.homepageClaimTier,
                          style: TextStyle(
                            fontSize: AppTypography.iosCaption1,
                            color: AppColors.iosSecondaryLabel(context),
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupSm),
                        CupertinoSlidingSegmentedControl<String>(
                          groupValue: _claimTier,
                          children: const <String, Widget>{
                            'basic': Padding(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.containerSm,
                              ),
                              child: Text(
                                ObjectHomepageText.homepageClaimTierBasic,
                              ),
                            ),
                            'verified': Padding(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.containerSm,
                              ),
                              child: Text(
                                ObjectHomepageText.homepageClaimTierVerified,
                              ),
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
                      ],
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageClaimContactPhone,
                    validationMessage: _phoneValidationMessage,
                    child: IosSelectionTextField(
                      controller: _phoneController,
                      enabled: canSubmit,
                      keyboardType: TextInputType.phone,
                      placeholder:
                          ObjectHomepageText.homepageClaimContactPhoneHint,
                      onChanged: (_) {
                        if (_phoneValidationMessage != null) {
                          setState(() => _phoneValidationMessage = null);
                        }
                      },
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageClaimBusinessLicense,
                    child: IosSelectionTextField(
                      controller: _licenseController,
                      enabled: canSubmit,
                      placeholder:
                          ObjectHomepageText.homepageClaimOptionalMaterialHint,
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageClaimIdentityCardFront,
                    child: IosSelectionTextField(
                      controller: _idFrontController,
                      enabled: canSubmit,
                      placeholder:
                          ObjectHomepageText.homepageClaimOptionalMaterialHint,
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageClaimIdentityCardBack,
                    child: IosSelectionTextField(
                      controller: _idBackController,
                      enabled: canSubmit,
                      placeholder:
                          ObjectHomepageText.homepageClaimOptionalMaterialHint,
                    ),
                  ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label: ObjectHomepageText.homepageClaimNote,
                    child: IosSelectionTextField(
                      controller: _noteController,
                      enabled: canSubmit,
                      placeholder: ObjectHomepageText.homepageClaimNoteHint,
                      maxLines: 4,
                    ),
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

  Future<void> _gateEntryAndLoad() async {
    final allowed = await requireHomepageWriteAccess(
      ref,
      context,
      action: HomepageWriteContinuationAction.claim,
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
        action: HomepageWriteContinuationAction.claim,
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
      action: HomepageWriteContinuationAction.claim,
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
      _pop();
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
      _pop();
    }
  }

  void _pop() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.homepageDetail(id: widget.homepageId));
  }

  Future<void> _load() async {
    _pageErrorSemantic = null;
    try {
      final detail = await ref
          .read(homepageQueryProvider)
          .getHomepageDetail(widget.homepageId);
      if (!mounted) {
        return;
      }
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
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      setState(() {
        _phoneValidationMessage = ObjectHomepageText.homepageClaimPhoneRequired;
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
      await trackHomepageProductAction(
        ref,
        action: 'claim_request_submit',
        pageName: 'homepageClaim',
        result: 'success',
        startedAt: startedAt,
        homepageId: widget.homepageId,
      );
      if (!mounted) {
        return;
      }
      AppToast.show(context, ObjectHomepageText.homepageClaimSubmitted);
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
          scope: UiErrorScope.section,
        );
      });
      await trackHomepageProductAction(
        ref,
        action: 'claim_request_submit',
        pageName: 'homepageClaim',
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
        return UiRecoveryOutcome.cancelled;
      case UiErrorActionType.openSettings:
      case UiErrorActionType.openUpdate:
      case UiErrorActionType.login:
        return UiRecoveryOutcome.cancelled;
    }
  }
}
