import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class SuggestHomepagePage extends ConsumerStatefulWidget {
  const SuggestHomepagePage({super.key, this.initialQuery = ''});

  final String initialQuery;

  @override
  ConsumerState<SuggestHomepagePage> createState() =>
      _SuggestHomepagePageState();
}

class _SuggestHomepagePageState extends ConsumerState<SuggestHomepagePage> {
  static const List<_HomepageTypeOption> _typeOptions = <_HomepageTypeOption>[
    _HomepageTypeOption(
      id: 'sight',
      label: UITextConstants.homepageTypeSight,
      cluePlaceholder: UITextConstants.addHomepageSightCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'hotel',
      label: UITextConstants.homepageTypeHotel,
      cluePlaceholder: UITextConstants.addHomepageHotelCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'restaurant',
      label: UITextConstants.homepageTypeRestaurant,
      cluePlaceholder: UITextConstants.addHomepageRestaurantCluePlaceholder,
      usesLocationFields: true,
    ),
    _HomepageTypeOption(
      id: 'vehicle',
      label: UITextConstants.homepageTypeVehicle,
      cluePlaceholder: UITextConstants.addHomepageVehicleCluePlaceholder,
      usesLocationFields: false,
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return IosSelectionPageScaffold(
      pageKey: TestKeys.suggestHomepagePage,
      title: UITextConstants.addHomepageTitle,
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
            UITextConstants.addHomepageFutureTypeHint,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ),
      bottomBar: IosSelectionBottomBar(
        confirmButtonKey: TestKeys.suggestHomepageSubmitButton,
        confirmLabel: UITextConstants.addHomepageSubmit,
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
        _SectionTitle(title: UITextConstants.addHomepageTypeSectionTitle),
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
                      option.label,
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
            _FormInputRow(
              label: UITextConstants.addHomepageNameLabel,
              child: _PlainFormTextField(
                controller: _titleController,
                placeholder: UITextConstants.addHomepageNamePlaceholder,
              ),
            ),
            _buildDivider(),
            _FormInputRow(
              label: UITextConstants.addHomepageClueLabel,
              child: _PlainFormTextField(
                controller: _clueController,
                placeholder: _selectedType.cluePlaceholder,
              ),
            ),
            _buildDivider(),
            _FormInputRow(
              label: UITextConstants.addHomepageCityLabel,
              child: _PlainFormTextField(
                controller: _cityController,
                placeholder: UITextConstants.addHomepageCityPlaceholder,
              ),
            ),
            _buildDivider(),
            _FormInputRow(
              label: UITextConstants.addHomepageAddressLabel,
              child: _PlainFormTextField(
                controller: _addressController,
                placeholder: UITextConstants.addHomepageAddressPlaceholder,
                maxLines: 2,
              ),
            ),
          ] else ...<Widget>[
            _FormInputRow(
              label: UITextConstants.addHomepageVehicleManufacturerLabel,
              child: _PlainFormTextField(
                controller: _vehicleManufacturerController,
                placeholder:
                    UITextConstants.addHomepageVehicleManufacturerPlaceholder,
              ),
            ),
            _buildDivider(),
            _FormInputRow(
              label: UITextConstants.addHomepageVehicleSeriesLabel,
              child: _PlainFormTextField(
                controller: _vehicleSeriesController,
                placeholder: UITextConstants.addHomepageVehicleSeriesPlaceholder,
              ),
            ),
            _buildDivider(),
            _FormInputRow(
              label: UITextConstants.addHomepageVehicleTrimLabel,
              child: _PlainFormTextField(
                controller: _vehicleTrimController,
                placeholder: UITextConstants.addHomepageVehicleTrimPlaceholder,
              ),
            ),
            _buildDivider(),
            _FormInputRow(
              label: UITextConstants.addHomepageClueLabel,
              child: _PlainFormTextField(
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

  Future<void> _handleCloseRequest() async {
    if (_isSubmitting) {
      return;
    }
    if (!_isDirty) {
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

  Future<void> _submit() async {
    if (!_canSubmit) {
      AppToast.show(
        context,
        _selectedType.usesLocationFields
            ? UITextConstants.addHomepageNameRequired
            : UITextConstants.addHomepageVehicleRequired,
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
    try {
      await ref.read(homepageRepositoryProvider).suggestHomepageCandidate(
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
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.addHomepageSubmitted);
      Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.addHomepageSubmitFailed);
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  String _buildVehicleTitle() {
    final manufacturer = _vehicleManufacturerController.text.trim();
    final series = _vehicleSeriesController.text.trim();
    return <String>[manufacturer, series]
        .where((item) => item.isNotEmpty)
        .join(' ');
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
    required this.label,
    required this.cluePlaceholder,
    required this.usesLocationFields,
  });

  final String id;
  final String label;
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

class _FormInputRow extends StatelessWidget {
  const _FormInputRow({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          child,
        ],
      ),
    );
  }
}

class _PlainFormTextField extends StatelessWidget {
  const _PlainFormTextField({
    required this.controller,
    required this.placeholder,
    this.maxLines = 1,
  });

  final TextEditingController controller;
  final String placeholder;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return CupertinoTextField(
      controller: controller,
      maxLines: maxLines,
      minLines: maxLines,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerXs,
        vertical: maxLines > 1 ? AppSpacing.intraGroupSm : AppSpacing.intraGroupXs,
      ),
      style: TextStyle(
        fontSize: AppTypography.iosBody,
        color: AppColors.iosLabel(context),
      ),
      placeholder: placeholder,
      placeholderStyle: TextStyle(
        fontSize: AppTypography.iosBody,
        color: SettingsSemanticConstants.createInputHintColor(isDark),
      ),
      decoration: const BoxDecoration(),
      cursorColor: AppColors.iosAccent(context),
    );
  }
}
