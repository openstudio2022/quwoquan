import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/assistant/assistant/skill_user_setting/presentation/assistant_skill_setup_schema.dart';

final class AssistantSkillConsentScopePresentation {
  const AssistantSkillConsentScopePresentation({
    required this.displayText,
    required this.description,
    required this.granted,
  });

  final String displayText;
  final String description;
  final bool granted;
}

Future<void> showAssistantSkillSetupSheet({
  required BuildContext context,
  required String title,
  required String valueDescription,
  required String dataUseSummary,
  required List<String> targetUserLabels,
  required List<String> surfaceLabels,
  required List<AssistantSkillConsentScopePresentation>
  requiredPermissionScopes,
  required List<AssistantSkillConsentScopePresentation>
  optionalPermissionScopes,
  required AssistantSkillSetupSchema? schema,
  required Map<String, Object?> initialConfiguration,
  required Future<void> Function(Map<String, Object?> value)? onSave,
}) {
  return showCupertinoModalPopup<void>(
    context: context,
    barrierDismissible: true,
    builder: (context) => AssistantSkillSetupSheet(
      title: title,
      valueDescription: valueDescription,
      dataUseSummary: dataUseSummary,
      targetUserLabels: targetUserLabels,
      surfaceLabels: surfaceLabels,
      requiredPermissionScopes: requiredPermissionScopes,
      optionalPermissionScopes: optionalPermissionScopes,
      schema: schema,
      initialConfiguration: initialConfiguration,
      onSave: onSave,
    ),
  );
}

class AssistantSkillSetupSheet extends StatefulWidget {
  const AssistantSkillSetupSheet({
    super.key,
    required this.title,
    required this.valueDescription,
    required this.dataUseSummary,
    required this.targetUserLabels,
    required this.surfaceLabels,
    required this.requiredPermissionScopes,
    required this.optionalPermissionScopes,
    required this.schema,
    required this.initialConfiguration,
    required this.onSave,
  });

  final String title;
  final String valueDescription;
  final String dataUseSummary;
  final List<String> targetUserLabels;
  final List<String> surfaceLabels;
  final List<AssistantSkillConsentScopePresentation> requiredPermissionScopes;
  final List<AssistantSkillConsentScopePresentation> optionalPermissionScopes;
  final AssistantSkillSetupSchema? schema;
  final Map<String, Object?> initialConfiguration;
  final Future<void> Function(Map<String, Object?> value)? onSave;

  @override
  State<AssistantSkillSetupSheet> createState() =>
      _AssistantSkillSetupSheetState();
}

class _AssistantSkillSetupSheetState extends State<AssistantSkillSetupSheet> {
  final Map<String, TextEditingController> _controllers =
      <String, TextEditingController>{};
  final Map<String, String?> _choices = <String, String?>{};
  final Map<String, String> _fieldErrors = <String, String>{};
  bool _saving = false;
  String? _saveError;

  @override
  void initState() {
    super.initState();
    for (final field
        in widget.schema?.fields ?? const <AssistantSkillSetupField>[]) {
      final initial = widget.initialConfiguration[field.id];
      if (field.kind == AssistantSkillSetupFieldKind.choice) {
        _choices[field.id] =
            initial is String && field.options.contains(initial)
            ? initial
            : null;
        continue;
      }
      _controllers[field.id] = TextEditingController(
        text: switch (field.kind) {
          AssistantSkillSetupFieldKind.stringList =>
            initial is List ? initial.whereType<String>().join('，') : '',
          _ => initial?.toString() ?? '',
        },
      );
    }
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = CupertinoTheme.of(context);
    final primary = theme.textTheme.textStyle.color ?? CupertinoColors.label;
    final secondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final grouped = CupertinoColors.secondarySystemGroupedBackground
        .resolveFrom(context);
    final schema = widget.schema;
    return CupertinoPopupSurface(
      isSurfacePainted: true,
      child: Container(
        key: const ValueKey<String>('assistant_skill_detail_sheet'),
        height:
            MediaQuery.sizeOf(context).height *
            AppSpacing.modalSheetMaxHeightRatio,
        color: background,
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              _buildHeader(context, primary, secondary),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.twenty,
                    AppSpacing.sm,
                    AppSpacing.twenty,
                    AppSpacing.twentyEight,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (widget.valueDescription.trim().isNotEmpty)
                        Text(
                          widget.valueDescription.trim(),
                          style: theme.textTheme.textStyle.copyWith(
                            height: AppTypography.lineHeightRelaxed,
                          ),
                        ),
                      const SizedBox(height: AppSpacing.eighteen),
                      _buildDetailCard(
                        background: grouped,
                        primary: primary,
                        secondary: secondary,
                      ),
                      const SizedBox(height: AppSpacing.twenty),
                      if (schema == null)
                        _buildUnavailableCard(grouped, primary, secondary)
                      else if (schema.fields.isNotEmpty) ...[
                        Text(
                          schema.title.isEmpty
                              ? AssistantText.assistantSkillSetupPersonalization
                              : schema.title,
                          style: theme.textTheme.navTitleTextStyle.copyWith(
                            color: primary,
                          ),
                        ),
                        if (schema.description.isNotEmpty) ...[
                          const SizedBox(height: AppSpacing.six),
                          Text(
                            schema.description,
                            style: theme.textTheme.textStyle.copyWith(
                              color: secondary,
                              fontSize: AppTypography.smPlus,
                              height: AppTypography.bodyLineHeight,
                            ),
                          ),
                        ],
                        const SizedBox(height: AppSpacing.sm + AppSpacing.xs),
                        ...schema.fields.map(
                          (field) => _buildField(
                            field,
                            background: grouped,
                            primary: primary,
                            secondary: secondary,
                          ),
                        ),
                        if (_saveError != null) ...[
                          const SizedBox(height: AppSpacing.sm),
                          Text(
                            _saveError!,
                            key: const ValueKey<String>(
                              'assistant_skill_setup_save_error',
                            ),
                            style: theme.textTheme.textStyle.copyWith(
                              color: CupertinoColors.systemRed.resolveFrom(
                                context,
                              ),
                              fontSize: AppTypography.smPlus,
                            ),
                          ),
                        ],
                        const SizedBox(height: AppSpacing.sm),
                        CupertinoButton.filled(
                          key: const ValueKey<String>(
                            'assistant_skill_setup_save',
                          ),
                          onPressed: _saving || widget.onSave == null
                              ? null
                              : _save,
                          child: _saving
                              ? AppRequestFeedback.inline()
                              : const Text(
                                  AssistantText.assistantSkillSetupSave,
                                ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, Color primary, Color secondary) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm + AppSpacing.xs,
        AppSpacing.sm + AppSpacing.xs,
        AppSpacing.sm,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              widget.title,
              style: CupertinoTheme.of(context).textTheme.navLargeTitleTextStyle
                  .copyWith(color: primary, fontSize: AppTypography.iosTitle2),
            ),
          ),
          CupertinoButton(
            key: const ValueKey<String>('assistant_skill_detail_close'),
            padding: const EdgeInsets.all(AppSpacing.sm),
            minimumSize: const Size.square(AppSpacing.minInteractiveSize),
            onPressed: () => Navigator.of(context).pop(),
            child: Icon(CupertinoIcons.xmark_circle_fill, color: secondary),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailCard({
    required Color background,
    required Color primary,
    required Color secondary,
  }) {
    final rows = <(String, String)>[
      if (widget.targetUserLabels.isNotEmpty)
        (
          AssistantText.assistantSkillSetupTargetUsers,
          widget.targetUserLabels.join('、'),
        ),
      if (widget.surfaceLabels.isNotEmpty)
        (
          AssistantText.assistantSkillSetupSurfaces,
          widget.surfaceLabels.join('、'),
        ),
      if (widget.dataUseSummary.trim().isNotEmpty)
        (
          AssistantText.assistantSkillSetupDataUse,
          widget.dataUseSummary.trim(),
        ),
      if (widget.requiredPermissionScopes.isNotEmpty)
        (
          AssistantText.assistantSkillRequiredConsentScopes,
          _permissionScopeSummary(widget.requiredPermissionScopes),
        ),
      if (widget.optionalPermissionScopes.isNotEmpty)
        (
          AssistantText.assistantSkillOptionalConsentScopes,
          _permissionScopeSummary(widget.optionalPermissionScopes),
        ),
    ];
    return Container(
      padding: const EdgeInsets.all(AppSpacing.fourteen),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Column(
        children: rows
            .map(
              (row) => Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.six),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: AppSpacing.minInteractiveSize + AppSpacing.xl,
                      child: Text(
                        row.$1,
                        style: TextStyle(
                          color: secondary,
                          fontSize: AppTypography.smPlus,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        row.$2,
                        style: TextStyle(
                          color: primary,
                          fontSize: AppTypography.smPlus,
                          height: AppTypography.bodyLineHeight,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            )
            .toList(growable: false),
      ),
    );
  }

  String _permissionScopeSummary(
    List<AssistantSkillConsentScopePresentation> scopes,
  ) {
    return scopes
        .map(
          (scope) =>
              '${scope.description.trim().isEmpty ? scope.displayText : '${scope.displayText}：${scope.description.trim()}'} · '
              '${scope.granted ? AssistantText.assistantSkillConsentGranted : AssistantText.assistantSkillConsentRequired}',
        )
        .join('、');
  }

  Widget _buildUnavailableCard(
    Color background,
    Color primary,
    Color secondary,
  ) {
    return Container(
      key: const ValueKey<String>('assistant_skill_setup_unavailable'),
      padding: const EdgeInsets.all(AppSpacing.fourteen),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            AssistantText.assistantSkillSetupUnavailable,
            style: TextStyle(color: primary),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            AssistantText.assistantSkillSetupUnavailableDescription,
            style: TextStyle(
              color: secondary,
              fontSize: AppTypography.smPlus,
              height: AppTypography.bodyLineHeight,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildField(
    AssistantSkillSetupField field, {
    required Color background,
    required Color primary,
    required Color secondary,
  }) {
    final error = _fieldErrors[field.id];
    return Container(
      key: ValueKey<String>('assistant_skill_setup_field_${field.id}'),
      margin: const EdgeInsets.only(bottom: AppSpacing.sm + AppSpacing.xs),
      padding: const EdgeInsets.all(AppSpacing.fourteen),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '${field.title}${field.required ? AssistantText.assistantSkillSetupRequiredFieldMarker : ''}',
            style: TextStyle(
              color: primary,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          if (field.description.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              field.description,
              style: TextStyle(
                color: secondary,
                fontSize: AppTypography.sm,
                height: AppSpacing.textLineHeightBody,
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.ten),
          if (field.kind == AssistantSkillSetupFieldKind.choice)
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: field.options
                  .map(
                    (option) => CupertinoButton(
                      key: ValueKey<String>(
                        'assistant_skill_setup_${field.id}_$option',
                      ),
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.fourteen,
                        vertical: AppSpacing.sm,
                      ),
                      color: _choices[field.id] == option
                          ? CupertinoColors.activeBlue.resolveFrom(context)
                          : CupertinoColors.tertiarySystemFill.resolveFrom(
                              context,
                            ),
                      onPressed: () => setState(() {
                        _choices[field.id] = option;
                        _fieldErrors.remove(field.id);
                      }),
                      child: Text(field.labelFor(option)),
                    ),
                  )
                  .toList(growable: false),
            )
          else
            CupertinoTextField(
              key: ValueKey<String>('assistant_skill_setup_input_${field.id}'),
              controller: _controllers[field.id],
              keyboardType: field.kind == AssistantSkillSetupFieldKind.integer
                  ? TextInputType.number
                  : field.kind == AssistantSkillSetupFieldKind.stringList
                  ? TextInputType.multiline
                  : TextInputType.text,
              minLines: field.kind == AssistantSkillSetupFieldKind.stringList
                  ? 2
                  : 1,
              maxLines: field.kind == AssistantSkillSetupFieldKind.stringList
                  ? 4
                  : 1,
              placeholder: field.kind == AssistantSkillSetupFieldKind.stringList
                  ? AssistantText.assistantSkillSetupListPlaceholder
                  : null,
              onChanged: (_) => setState(() {
                _fieldErrors.remove(field.id);
              }),
            ),
          if (error != null) ...[
            const SizedBox(height: AppSpacing.six),
            Text(
              error,
              style: TextStyle(
                color: CupertinoColors.systemRed.resolveFrom(context),
                fontSize: AppTypography.sm,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _save() async {
    final schema = widget.schema;
    final onSave = widget.onSave;
    if (schema == null || onSave == null) return;
    final value = <String, Object?>{};
    final errors = <String, String>{};
    for (final field in schema.fields) {
      final parsed = _valueFor(field);
      final error = field.validate(parsed);
      if (error != null) {
        errors[field.id] = error;
      } else if (parsed != null &&
          parsed != '' &&
          !(parsed is List && parsed.isEmpty)) {
        value[field.id] = parsed;
      }
    }
    if (errors.isNotEmpty) {
      setState(() {
        _fieldErrors
          ..clear()
          ..addAll(errors);
        _saveError = null;
      });
      return;
    }
    setState(() {
      _saving = true;
      _saveError = null;
    });
    try {
      await onSave(value);
      if (mounted) Navigator.of(context).pop();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saveError = AssistantText.assistantSkillSetupSaveFailed;
      });
    }
  }

  Object? _valueFor(AssistantSkillSetupField field) {
    if (field.kind == AssistantSkillSetupFieldKind.choice) {
      return _choices[field.id];
    }
    final raw = _controllers[field.id]?.text.trim() ?? '';
    return switch (field.kind) {
      AssistantSkillSetupFieldKind.integer =>
        raw.isEmpty ? null : int.tryParse(raw) ?? raw,
      AssistantSkillSetupFieldKind.stringList =>
        raw
            .split(RegExp(r'[,，\n]'))
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toSet()
            .toList(growable: false),
      _ => raw,
    };
  }
}
