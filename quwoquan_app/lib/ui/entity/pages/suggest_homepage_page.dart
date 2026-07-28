import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_action_observability.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_type_labels.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_write_access.dart';

class SuggestHomepagePage extends ConsumerStatefulWidget {
  const SuggestHomepagePage({
    super.key,
    this.initialQuery = '',
    this.sourcePlaceId = '',
  });

  final String initialQuery;
  final String sourcePlaceId;

  @override
  ConsumerState<SuggestHomepagePage> createState() =>
      _SuggestHomepagePageState();
}

class _SuggestHomepagePageState extends ConsumerState<SuggestHomepagePage> {
  static const List<_HomepageTypeOption> _typeOptions = <_HomepageTypeOption>[
    _HomepageTypeOption(
      id: 'sight',
      cluePlaceholder: CreationText.addHomepageSightCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'hotel',
      cluePlaceholder: CreationText.addHomepageHotelCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'restaurant',
      cluePlaceholder: CreationText.addHomepageRestaurantCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'vehicle',
      cluePlaceholder: CreationText.addHomepageVehicleCluePlaceholder,
      usesLocationFields: false,
    ),
    _HomepageTypeOption(
      id: 'university',
      cluePlaceholder: CreationText.addHomepageUniversityCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'travel_photo',
      cluePlaceholder: CreationText.addHomepageTravelPhotoCluePlaceholder,
      usesLocationFields: true,
    ),
  ];

  late final TextEditingController _titleController;
  late final TextEditingController _vehicleSeriesController;
  final TextEditingController _clueController = TextEditingController();
  final TextEditingController _cityController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();
  final TextEditingController _vehicleManufacturerController =
      TextEditingController();
  final TextEditingController _vehicleTrimController = TextEditingController();

  String _homepageType = 'sight';
  bool _isSubmitting = false;
  bool _authResumeScheduled = false;

  _HomepageTypeOption get _selectedType => _typeOptions.firstWhere(
    (option) => option.id == _homepageType,
    orElse: () => _typeOptions.first,
  );

  bool get _canSubmit {
    if (_isSubmitting) {
      return false;
    }
    if (_selectedType.usesLocationFields) {
      return _titleController.text.trim().isNotEmpty;
    }
    return _vehicleManufacturerController.text.trim().isNotEmpty &&
        _vehicleSeriesController.text.trim().isNotEmpty;
  }

  bool get _isDirty {
    final initialQuery = widget.initialQuery.trim();
    return _homepageType != _typeOptions.first.id ||
        _titleController.text.trim() != initialQuery ||
        _vehicleSeriesController.text.trim() != initialQuery ||
        _clueController.text.trim().isNotEmpty ||
        _cityController.text.trim().isNotEmpty ||
        _addressController.text.trim().isNotEmpty ||
        _vehicleManufacturerController.text.trim().isNotEmpty ||
        _vehicleTrimController.text.trim().isNotEmpty;
  }

  void _handleFieldChanged() {
    if (!mounted) {
      return;
    }
    setState(() {});
  }

  @override
  void initState() {
    super.initState();
    final initialQuery = widget.initialQuery.trim();
    _titleController = TextEditingController(text: initialQuery);
    _vehicleSeriesController = TextEditingController(text: initialQuery);
    for (final controller in <TextEditingController>[
      _titleController,
      _vehicleSeriesController,
      _clueController,
      _cityController,
      _addressController,
      _vehicleManufacturerController,
      _vehicleTrimController,
    ]) {
      controller.addListener(_handleFieldChanged);
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_gateEntry());
    });
  }

  @override
  void dispose() {
    for (final controller in <TextEditingController>[
      _titleController,
      _vehicleSeriesController,
      _clueController,
      _cityController,
      _addressController,
      _vehicleManufacturerController,
      _vehicleTrimController,
    ]) {
      controller.removeListener(_handleFieldChanged);
    }
    _titleController.dispose();
    _vehicleSeriesController.dispose();
    _clueController.dispose();
    _cityController.dispose();
    _addressController.dispose();
    _vehicleManufacturerController.dispose();
    _vehicleTrimController.dispose();
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
    return IosSelectionPageScaffold(
      pageKey: TestKeys.suggestHomepagePage,
      title: CreationText.addHomepageTitle,
      onBack: _handleCloseRequest,
      leadingStyle: IosSelectionHeaderLeadingStyle.close,
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.interGroupLg,
        ),
        children: <Widget>[
          _buildTypeSection(context),
          SizedBox(height: AppSpacing.interGroupMd),
          _buildFormSection(context),
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            CreationText.addHomepageFutureTypeHint,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ),
      bottomBar: IosSelectionBottomBar(
        confirmButtonKey: TestKeys.suggestHomepageSubmitButton,
        confirmLabel: CreationText.addHomepageSubmit,
        confirmEnabled: _canSubmit,
        confirmLoading: _isSubmitting,
        onConfirm: _submit,
      ),
    );
  }

  Widget _buildTypeSection(BuildContext context) {
    final background = AppColors.iosSecondaryFill(context);
    final selectedColor = AppColors.iosLabel(context);
    final unselectedColor = AppColors.iosSecondaryLabel(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _SectionTitle(title: CreationText.addHomepageTypeSectionTitle),
        SizedBox(height: AppSpacing.intraGroupSm),
        DecoratedBox(
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          ),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.two),
            child: CupertinoSlidingSegmentedControl<String>(
              groupValue: _homepageType,
              thumbColor: AppColors.iosSystemBackground(context),
              backgroundColor: background,
              children: <String, Widget>{
                for (final option in _typeOptions)
                  option.id: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerSm,
                      vertical: AppSpacing.intraGroupSm,
                    ),
                    child: Text(
                      homepageTypeLabel(option.id),
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.medium,
                        color: _homepageType == option.id
                            ? selectedColor
                            : unselectedColor,
                      ),
                    ),
                  ),
              },
              onValueChanged: (value) {
                if (value != null) {
                  _selectType(value);
                }
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFormSection(BuildContext context) {
    return IosSelectionSection(
      child: Column(
        children: <Widget>[
          if (_selectedType.usesLocationFields) ...<Widget>[
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageNameLabel,
              child: IosSelectionTextField(
                controller: _titleController,
                placeholder: CreationText.addHomepageNamePlaceholder,
              ),
            ),
            _buildDivider(),
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageClueLabel,
              child: IosSelectionTextField(
                controller: _clueController,
                placeholder: _selectedType.cluePlaceholder,
              ),
            ),
            _buildDivider(),
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageCityLabel,
              child: IosSelectionTextField(
                controller: _cityController,
                placeholder: CreationText.addHomepageCityPlaceholder,
              ),
            ),
            _buildDivider(),
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageAddressLabel,
              child: IosSelectionTextField(
                controller: _addressController,
                placeholder: CreationText.addHomepageAddressPlaceholder,
                maxLines: 2,
              ),
            ),
          ] else ...<Widget>[
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageVehicleManufacturerLabel,
              child: IosSelectionTextField(
                controller: _vehicleManufacturerController,
                placeholder:
                    CreationText.addHomepageVehicleManufacturerPlaceholder,
              ),
            ),
            _buildDivider(),
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageVehicleSeriesLabel,
              child: IosSelectionTextField(
                controller: _vehicleSeriesController,
                placeholder:
                    CreationText.addHomepageVehicleSeriesPlaceholder,
              ),
            ),
            _buildDivider(),
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageVehicleTrimLabel,
              child: IosSelectionTextField(
                controller: _vehicleTrimController,
                placeholder: CreationText.addHomepageVehicleTrimPlaceholder,
              ),
            ),
            _buildDivider(),
            IosSelectionFormFieldRow(
              label: CreationText.addHomepageClueLabel,
              child: IosSelectionTextField(
                controller: _clueController,
                placeholder: _selectedType.cluePlaceholder,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildDivider() {
    return const IosSelectionInlineDivider(indent: AppSpacing.containerMd);
  }

  void _selectType(String nextType) {
    if (_homepageType == nextType) {
      return;
    }
    if (nextType == 'vehicle' &&
        _vehicleSeriesController.text.trim().isEmpty &&
        _titleController.text.trim().isNotEmpty) {
      _vehicleSeriesController.text = _titleController.text.trim();
    }
    setState(() {
      _homepageType = nextType;
    });
  }

  Future<void> _gateEntry() async {
    await requireHomepageWriteAccess(
      ref,
      context,
      action: HomepageWriteContinuationAction.suggest,
      dismissFallback: AppRoutePaths.home,
    );
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
        action: HomepageWriteContinuationAction.suggest,
      );
      if (pending?.submitAfterLogin == true) {
        unawaited(_submit());
      }
    });
  }

  Future<bool> _ensureSubmitAuthentication() {
    return requireHomepageWriteAccess(
      ref,
      context,
      action: HomepageWriteContinuationAction.suggest,
      dismissFallback: AppRoutePaths.home,
      submitAfterLogin: true,
    );
  }

  Future<void> _handleCloseRequest() async {
    if (_isSubmitting) {
      return;
    }
    if (!_isDirty) {
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

  Future<void> _submit() async {
    if (!await _ensureSubmitAuthentication() || !mounted) {
      return;
    }
    if (!_canSubmit) {
      AppToast.show(
        context,
        _selectedType.usesLocationFields
            ? CreationText.addHomepageNameRequired
            : CreationText.addHomepageVehicleRequired,
      );
      return;
    }

    final title = _selectedType.usesLocationFields
        ? _titleController.text.trim()
        : _buildVehicleTitle();
    final subtitle = _selectedType.usesLocationFields
        ? _clueController.text.trim()
        : _buildVehicleSubtitle();

    setState(() {
      _isSubmitting = true;
    });
    UiErrorSemantic? submitErrorSemantic;
    final startedAt = DateTime.now();
    try {
      await ref
          .read(homepageCommandWriterProvider)
          .suggestHomepageCandidate(
            draft: HomepageSuggestionDraft(
              title: title,
              homepageType: _homepageType,
              subtitle: subtitle,
              city: _selectedType.usesLocationFields
                  ? _cityController.text.trim()
                  : '',
              address: _selectedType.usesLocationFields
                  ? _addressController.text.trim()
                  : '',
              categoryTags: _buildCategoryTags(),
              sourcePlaceId: widget.sourcePlaceId,
            ),
          );
      if (!mounted) {
        return;
      }
      await trackHomepageProductAction(
        ref,
        action: 'suggest_candidate_submit',
        pageName: 'suggestHomepage',
        result: 'success',
        startedAt: startedAt,
      );
      if (!mounted) {
        return;
      }
      AppToast.show(context, CreationText.addHomepageSubmitted);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        final resolved = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        submitErrorSemantic = UiErrorSemantic(
          category: resolved.category,
          scope: resolved.scope,
          title: CreationText.addHomepageSubmitFailedTitle,
          message: resolved.message,
          secondaryMessage: resolved.secondaryMessage,
          primaryAction: const UiErrorAction(
            type: UiErrorActionType.retry,
            label: ContentText.tryAgain,
          ),
          secondaryAction: resolved.secondaryAction,
          dismissible: resolved.dismissible,
          sourceCode: resolved.sourceCode,
          failureKind: resolved.failureKind,
          recoveryAction: resolved.recoveryAction,
          presentation: resolved.presentation,
          tone: resolved.tone,
        );
        await trackHomepageProductAction(
          ref,
          action: 'suggest_candidate_submit',
          pageName: 'suggestHomepage',
          result: 'failure',
          startedAt: startedAt,
          error: error,
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
    if (submitErrorSemantic != null && mounted) {
      await AppActionErrorFeedback.show(
        context,
        semantic: submitErrorSemantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submit();
          }
        },
      );
    }
  }

  String _buildVehicleTitle() {
    final manufacturer = _vehicleManufacturerController.text.trim();
    final series = _vehicleSeriesController.text.trim();
    return <String>[
      manufacturer,
      series,
    ].where((item) => item.isNotEmpty).join(' ');
  }

  String _buildVehicleSubtitle() {
    return <String>[
      _vehicleTrimController.text.trim(),
      _clueController.text.trim(),
    ].where((item) => item.isNotEmpty).join(' · ');
  }

  List<String> _buildCategoryTags() {
    if (_selectedType.id != 'vehicle') {
      return const <String>[];
    }
    final manufacturer = _vehicleManufacturerController.text.trim();
    if (manufacturer.isEmpty) {
      return const <String>[];
    }
    return <String>[manufacturer];
  }

  void _pop() {
    final navigator = Navigator.of(context);
    if (navigator.canPop()) {
      navigator.pop();
    }
  }
}

class _HomepageTypeOption {
  const _HomepageTypeOption({
    required this.id,
    required this.cluePlaceholder,
    required this.usesLocationFields,
  });

  final String id;
  final String cluePlaceholder;
  final bool usesLocationFields;
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: TextStyle(
        fontSize: AppTypography.iosFootnote,
        fontWeight: AppTypography.semiBold,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );
  }
}
