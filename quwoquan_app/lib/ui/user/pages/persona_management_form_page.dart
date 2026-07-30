import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/providers/persona_management_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show PersonaIsolationLevel;

class PersonaFormResult {
  const PersonaFormResult({this.createdPersona});

  final PersonaManagementItemViewData? createdPersona;
}

/// 分身创建/编辑正式表单页（设置类 A 类 inset grouped 表单，
/// 替代既往 CupertinoAlertDialog 内嵌表单原型）。
class PersonaFormPage extends ConsumerStatefulWidget {
  const PersonaFormPage.create({super.key, required this.notifier})
    : persona = null;

  const PersonaFormPage.edit({
    super.key,
    required this.notifier,
    required PersonaManagementItemViewData this.persona,
  });

  final PersonaManagementNotifier notifier;
  final PersonaManagementItemViewData? persona;

  bool get isCreate => persona == null;

  @override
  ConsumerState<PersonaFormPage> createState() => _PersonaFormPageState();
}

class _PersonaFormPageState extends ConsumerState<PersonaFormPage> {
  late final TextEditingController _displayNameController;
  late final TextEditingController _purposeController;
  late PersonaIsolationLevel _isolationLevel;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final persona = widget.persona;
    _displayNameController = TextEditingController(
      text: persona?.displayName ?? '',
    )..addListener(() => setState(() {}));
    _purposeController = TextEditingController();
    _isolationLevel = persona == null
        ? PersonaIsolationLevel.open
        : PersonaIsolationLevel.fromWire(persona.isolationLevel);
  }

  @override
  void dispose() {
    _displayNameController.dispose();
    _purposeController.dispose();
    super.dispose();
  }

  bool get _canSave =>
      !_saving && _displayNameController.text.trim().isNotEmpty;

  Future<void> _submit() async {
    final displayName = _displayNameController.text.trim();
    if (displayName.isEmpty) {
      AppToast.show(context, ProfileText.personaFormNameRequiredHint);
      return;
    }
    setState(() => _saving = true);
    try {
      if (widget.isCreate) {
        final purposeHint = _purposeController.text.trim();
        final created = await widget.notifier.createPersona(
          displayName: displayName,
          isolationLevel: _isolationLevel.wireValue,
          purposeHint: purposeHint.isEmpty ? null : purposeHint,
        );
        if (!mounted) return;
        Navigator.of(context).pop(PersonaFormResult(createdPersona: created));
      } else {
        await widget.notifier.updatePersona(
          widget.persona!.personaId,
          displayName: displayName,
          isolationLevel: _isolationLevel.wireValue,
        );
        if (!mounted) return;
        Navigator.of(context).pop(const PersonaFormResult());
      }
    } catch (error) {
      if (!mounted) return;
      setState(() => _saving = false);
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: UiErrorSemantic(
          category: resolved.category,
          scope: resolved.scope,
          title: widget.isCreate
              ? ContentText.personaCreateErrorTitle
              : ContentText.personaEditErrorTitle,
          message: resolved.message,
          secondaryMessage: resolved.secondaryMessage,
          primaryAction:
              resolved.primaryAction ??
              const UiErrorAction(
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
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submit();
          }
        },
      );
      return;
    }
  }

  Widget _textFieldRow({
    required bool isDark,
    required String label,
    required TextEditingController controller,
    required String placeholder,
    TextInputType? keyboardType,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: SettingsSemanticConstants.insetFormRowMinHeight,
        ),
        child: Row(
          children: <Widget>[
            SizedBox(
              width: AppSpacing.oneHundred,
              child: Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.regular,
                  color: SettingsSemanticConstants.labelColor(isDark),
                ),
              ),
            ),
            Expanded(
              child: CupertinoTextField.borderless(
                controller: controller,
                placeholder: placeholder,
                keyboardType: keyboardType,
                padding: EdgeInsets.zero,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  color: SettingsSemanticConstants.labelColor(isDark),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _isolationOptionRow({
    required bool isDark,
    required PersonaIsolationLevel level,
    required String description,
  }) {
    final selected = _isolationLevel == level;
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () => setState(() => _isolationLevel = level),
        child: Padding(
          padding: EdgeInsets.symmetric(
            vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: SettingsSemanticConstants.insetFormRowMinHeight,
            ),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    description,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.regular,
                      color: SettingsSemanticConstants.labelColor(isDark),
                    ),
                  ),
                ),
                Icon(
                  selected
                      ? CupertinoIcons.check_mark_circled_solid
                      : CupertinoIcons.circle,
                  color: selected
                      ? AppColors.iosAccent(context)
                      : AppColors.iosTertiaryLabel(context),
                  size: AppSpacing.iconMedium,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final persona = widget.persona;
    final divider = SettingsInsetFormSectionDivider(isDark: isDark);
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: widget.isCreate
          ? ProfileText.personaCreateTitle
          : ProfileText.personaEditTitle,
      onBack: () => Navigator.of(context).pop(),
      trailing: _saving
          ? AppRequestFeedback.inline()
          : CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: _canSave ? _submit : null,
              child: Text(
                widget.isCreate
                    ? DiscoveryText.create
                    : ProfileText.editProfileSaveAction,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  color: _canSave
                      ? AppColors.iosAccent(context)
                      : AppColors.iosTertiaryLabel(context),
                ),
              ),
            ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          SettingsSemanticConstants.insetFormListHorizontalPadding,
          AppSpacing.containerSm,
          SettingsSemanticConstants.insetFormListHorizontalPadding,
          MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg,
        ),
        children: <Widget>[
          SettingsInsetGroupedSection(
            isDark: isDark,
            header: ProfileText.personaFormBasicSection,
            density: SettingsInsetSectionDensity.compact,
            child: Column(
              children: <Widget>[
                _textFieldRow(
                  isDark: isDark,
                  label: ProfileText.editProfileNicknameLabel,
                  controller: _displayNameController,
                  placeholder: ProfileText.profilePersonaNamePlaceholder,
                ),
                if (widget.isCreate) ...<Widget>[
                  divider,
                  _textFieldRow(
                    isDark: isDark,
                    label: ProfileText.personaCreateTitle,
                    controller: _purposeController,
                    placeholder: ProfileText.personaFormPurposePlaceholder,
                  ),
                ] else ...<Widget>[
                  divider,
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: ProfileText.personaUserHandleLabel,
                    trailing: Text(
                      persona!.userHandle.isEmpty ? '-' : persona.userHandle,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          SettingsInsetGroupedSection(
            isDark: isDark,
            header: ProfileText.personaFormVisibilitySection,
            density: SettingsInsetSectionDensity.compact,
            child: Column(
              children: <Widget>[
                _isolationOptionRow(
                  isDark: isDark,
                  level: PersonaIsolationLevel.open,
                  description: ProfileText.profilePersonaOpenDescription,
                ),
                divider,
                _isolationOptionRow(
                  isDark: isDark,
                  level: PersonaIsolationLevel.semi,
                  description: ProfileText.profilePersonaSemiDescription,
                ),
                divider,
                _isolationOptionRow(
                  isDark: isDark,
                  level: PersonaIsolationLevel.strict,
                  description: ProfileText.profilePersonaStrictDescription,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
