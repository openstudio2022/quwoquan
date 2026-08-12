part of 'homepage_status_report_page.dart';

class _HomepageStatusReportPageState
    extends ConsumerState<HomepageStatusReportPage> {
  static const List<(String, String)> _reasons = <(String, String)>[
    ('offline', ObjectHomepageText.homepageStatusReportReasonOffline),
    (
      'incorrect_info',
      ObjectHomepageText.homepageStatusReportReasonIncorrectInfo,
    ),
    ('duplicate_entry', ObjectHomepageText.homepageStatusReportReasonDuplicate),
    ('inactive', ObjectHomepageText.homepageStatusReportReasonInactive),
  ];

  final TextEditingController _descriptionController = TextEditingController();
  HomepageWriteTarget? _detail;
  bool _isLoading = true;
  bool _isSubmitting = false;
  bool _didStartLoad = false;
  bool _authResumeScheduled = false;
  UiErrorSemantic? _pageErrorSemantic;
  UiErrorSemantic? _submitErrorSemantic;
  String? _reasonValidationMessage;
  String _reason = '';
  String? _pendingSubmitIntentId;
  int? _pendingSubmitFingerprint;

  bool get _hasUnsavedChanges =>
      _reason.isNotEmpty || _descriptionController.text.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => unawaited(_gateEntryAndLoad()),
    );
  }

  @override
  void dispose() {
    _descriptionController.dispose();
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
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _scheduleAuthContinuationResume(),
      );
    }

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    if (_pageErrorSemantic != null && !_isLoading) {
      return IosSelectionPageScaffold(
        title: ObjectHomepageText.homepageStatusReportAction,
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
        !_isLoading && !_isSubmitting && (_detail?.status ?? '') != 'offline';
    return IosSelectionPageScaffold(
      title: ObjectHomepageText.homepageStatusReportAction,
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
                          ? ObjectHomepageText
                                .homepageStatusReportOfflineDescription
                          : ObjectHomepageText.homepageStatusReportDescription,
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
              title: ObjectHomepageText.homepageStatusReportReasonSection,
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
            ),
            IosSelectionSection(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      AppSpacing.containerSm,
                      AppSpacing.containerMd,
                      AppSpacing.intraGroupXs,
                    ),
                    child: Text(
                      ObjectHomepageText.homepageStatusReportSelectReason,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ),
                  for (var index = 0; index < _reasons.length; index++) ...[
                    if (index > 0)
                      const IosSelectionInlineDivider(
                        indent: AppSpacing.containerMd,
                      ),
                    IosSelectionOptionTile(
                      title: Text(
                        _reasons[index].$2,
                        style: TextStyle(
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.medium,
                          color: AppColors.iosLabel(context),
                        ),
                      ),
                      trailing: Icon(
                        _reason == _reasons[index].$1
                            ? CupertinoIcons.check_mark_circled_solid
                            : CupertinoIcons.circle,
                        color: _reason == _reasons[index].$1
                            ? AppColors.primaryColor
                            : AppColors.iosSecondaryLabel(context),
                      ),
                      onTap: canSubmit
                          ? () {
                              setState(() {
                                _reason = _reasons[index].$1;
                                _reasonValidationMessage = null;
                              });
                            }
                          : null,
                    ),
                  ],
                  if ((_reasonValidationMessage ?? '').isNotEmpty)
                    Padding(
                      padding: EdgeInsets.fromLTRB(
                        AppSpacing.containerMd,
                        AppSpacing.intraGroupXs,
                        AppSpacing.containerMd,
                        AppSpacing.containerSm,
                      ),
                      child: AppInlineFieldError(
                        message: _reasonValidationMessage!,
                      ),
                    ),
                  const IosSelectionInlineDivider(
                    indent: AppSpacing.containerMd,
                  ),
                  IosSelectionFormFieldRow(
                    label:
                        ObjectHomepageText.homepageStatusReportDescriptionLabel,
                    child: IosSelectionTextField(
                      controller: _descriptionController,
                      enabled: canSubmit,
                      placeholder: ObjectHomepageText
                          .homepageStatusReportDescriptionPlaceholder,
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
        confirmLabel: (_detail?.status ?? '') == 'offline'
            ? ObjectHomepageText.homepageStatusReportAlreadyOffline
            : ObjectHomepageText.homepageStatusReportSubmit,
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
      action: HomepageWriteContinuationAction.statusReport,
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
        action: HomepageWriteContinuationAction.statusReport,
        homepageId: widget.homepageId,
      );
      if (pending?.submitAfterLogin == true) {
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
      action: HomepageWriteContinuationAction.statusReport,
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
    final navigator = Navigator.of(context);
    if (navigator.canPop()) {
      navigator.pop();
    }
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _pageErrorSemantic = null;
    });
    try {
      final detail = await widget.writeTargetReader.getHomepageWriteTarget(
        widget.homepageId,
      );
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
    if (_reason.isEmpty) {
      setState(() {
        _reasonValidationMessage =
            ObjectHomepageText.homepageStatusReportReasonRequired;
      });
      return;
    }
    final draft = HomepageStatusReportDraft(
      reason: _reason,
      description: _descriptionController.text.trim(),
    );
    final fingerprint = Object.hashAll(<Object?>[
      widget.homepageId,
      draft.reason,
      draft.description,
      ...draft.evidenceUrls,
    ]);
    if (_pendingSubmitFingerprint != fingerprint ||
        (_pendingSubmitIntentId ?? '').isEmpty) {
      _pendingSubmitFingerprint = fingerprint;
      _pendingSubmitIntentId = const Uuid().v4();
    }
    final submitIntentId = _pendingSubmitIntentId!;
    setState(() {
      _isSubmitting = true;
      _submitErrorSemantic = null;
    });
    final startedAt = DateTime.now();
    try {
      final receipt = await widget.commandWriter.createStatusReport(
        homepageId: widget.homepageId,
        draft: draft,
        clientRequestId: submitIntentId,
      );
      if (!_isCanonicalPendingStatusReceipt(receipt)) {
        throw _invalidStatusReceiptFailure(receipt);
      }
      final readback = await widget.queryReader.getMyPendingStatusReport(
        homepageId: widget.homepageId,
        reason: draft.reason,
      );
      if (!_isSamePendingStatusReport(receipt, readback)) {
        throw _invalidStatusReadbackFailure(receipt, readback);
      }
      if (!mounted) {
        return;
      }
      await widget.actionTracker.trackSubmit(
        homepageId: widget.homepageId,
        succeeded: true,
        startedAt: startedAt,
      );
      if (!mounted) {
        return;
      }
      _pendingSubmitIntentId = null;
      _pendingSubmitFingerprint = null;
      AppToast.show(context, ObjectHomepageText.homepageStatusReportSubmitted);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _submitErrorSemantic = ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.submit,
            scope: UiErrorScope.form,
          ),
        );
      });
      await widget.actionTracker.trackSubmit(
        homepageId: widget.homepageId,
        succeeded: false,
        startedAt: startedAt,
        error: error,
      );
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  bool _isCanonicalPendingStatusReceipt(HomepageStatusReportView receipt) {
    return receipt.reportId.trim().isNotEmpty &&
        receipt.homepageId == widget.homepageId &&
        receipt.reason.wireName == _reason &&
        receipt.status == HomepageStatusReportStatus.pendingReview &&
        receipt.reviewedAt == null;
  }

  bool _isSamePendingStatusReport(
    HomepageStatusReportView receipt,
    HomepageStatusReportView readback,
  ) {
    return _isCanonicalPendingStatusReceipt(readback) &&
        readback.reportId == receipt.reportId &&
        readback.reporterPersonaId == receipt.reporterPersonaId &&
        readback.createdAt.isAtSameMomentAs(receipt.createdAt);
  }

  RuntimeFailure _invalidStatusReceiptFailure(
    HomepageStatusReportView receipt,
  ) {
    return RuntimeFailure(
      code: RuntimeFailureCodes.appContractInvalidResponse,
      semanticReason: 'homepage_status_report_receipt_not_pending',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.contract,
      nature: RuntimeFailureNature.bug,
      location: const RuntimeFailureLocation(
        businessObject: 'entity.homepage_status_report',
        functionModule: 'homepage_status_report_page',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'homepageMatches',
            value: (receipt.homepageId == widget.homepageId).toString(),
          ),
          RuntimeContextAttribute(
            key: 'status',
            value: receipt.status.wireName,
          ),
          RuntimeContextAttribute(
            key: 'reasonMatches',
            value: (receipt.reason.wireName == _reason).toString(),
          ),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'inlineCard',
      ),
    );
  }

  RuntimeFailure _invalidStatusReadbackFailure(
    HomepageStatusReportView receipt,
    HomepageStatusReportView readback,
  ) {
    return RuntimeFailure(
      code: RuntimeFailureCodes.appContractInvalidResponse,
      semanticReason: 'homepage_status_report_readback_not_converged',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.contract,
      nature: RuntimeFailureNature.bug,
      location: const RuntimeFailureLocation(
        businessObject: 'entity.homepage_status_report',
        functionModule: 'homepage_status_report_page',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'reportIdMatches',
            value: (readback.reportId == receipt.reportId).toString(),
          ),
          RuntimeContextAttribute(
            key: 'reporterMatches',
            value: (readback.reporterPersonaId == receipt.reporterPersonaId)
                .toString(),
          ),
          RuntimeContextAttribute(
            key: 'status',
            value: readback.status.wireName,
          ),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'inlineCard',
      ),
    );
  }

  Future<void> _handleSubmitErrorAction(UiErrorAction action) async {
    if (action.type == UiErrorActionType.retry ||
        action.type == UiErrorActionType.resubmit) {
      await _submit();
    } else if (action.type == UiErrorActionType.dismiss && mounted) {
      setState(() => _submitErrorSemantic = null);
    }
  }

  Future<UiRecoveryOutcome> _handlePageErrorAction(UiErrorAction action) async {
    if (action.type == UiErrorActionType.retry ||
        action.type == UiErrorActionType.resubmit) {
      await _load();
      return _pageErrorSemantic == null
          ? UiRecoveryOutcome.recovered
          : UiRecoveryOutcome.stillBlocked;
    }
    return UiRecoveryOutcome.cancelled;
  }
}
