import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_setup_schema.dart';

Future<void> showAssistantSkillSetupSheet({
  required BuildContext context,
  required String title,
  required String valueDescription,
  required String dataUseSummary,
  required List<String> targetUserLabels,
  required List<String> surfaceLabels,
  required List<String> permissionLabels,
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
      permissionLabels: permissionLabels,
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
    required this.permissionLabels,
    required this.schema,
    required this.initialConfiguration,
    required this.onSave,
  });

  final String title;
  final String valueDescription;
  final String dataUseSummary;
  final List<String> targetUserLabels;
  final List<String> surfaceLabels;
  final List<String> permissionLabels;
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
        height: MediaQuery.sizeOf(context).height * 0.88,
        color: background,
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              _buildHeader(context, primary, secondary),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (widget.valueDescription.trim().isNotEmpty)
                        Text(
                          widget.valueDescription.trim(),
                          style: theme.textTheme.textStyle.copyWith(
                            height: 1.45,
                          ),
                        ),
                      const SizedBox(height: 18),
                      _buildDetailCard(
                        background: grouped,
                        primary: primary,
                        secondary: secondary,
                      ),
                      const SizedBox(height: 20),
                      if (schema == null)
                        _buildUnavailableCard(grouped, primary, secondary)
                      else if (schema.fields.isNotEmpty) ...[
                        Text(
                          schema.title.isEmpty ? '个性化设置' : schema.title,
                          style: theme.textTheme.navTitleTextStyle.copyWith(
                            color: primary,
                          ),
                        ),
                        if (schema.description.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text(
                            schema.description,
                            style: theme.textTheme.textStyle.copyWith(
                              color: secondary,
                              fontSize: 13,
                              height: 1.4,
                            ),
                          ),
                        ],
                        const SizedBox(height: 12),
                        ...schema.fields.map(
                          (field) => _buildField(
                            field,
                            background: grouped,
                            primary: primary,
                            secondary: secondary,
                          ),
                        ),
                        if (_saveError != null) ...[
                          const SizedBox(height: 8),
                          Text(
                            _saveError!,
                            key: const ValueKey<String>(
                              'assistant_skill_setup_save_error',
                            ),
                            style: theme.textTheme.textStyle.copyWith(
                              color: CupertinoColors.systemRed.resolveFrom(
                                context,
                              ),
                              fontSize: 13,
                            ),
                          ),
                        ],
                        const SizedBox(height: 8),
                        CupertinoButton.filled(
                          key: const ValueKey<String>(
                            'assistant_skill_setup_save',
                          ),
                          onPressed: _saving || widget.onSave == null
                              ? null
                              : _save,
                          child: _saving
                              ? const CupertinoActivityIndicator()
                              : const Text('保存设置'),
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
      padding: const EdgeInsets.fromLTRB(16, 12, 12, 8),
      child: Row(
        children: [
          Expanded(
            child: Text(
              widget.title,
              style: CupertinoTheme.of(context).textTheme.navLargeTitleTextStyle
                  .copyWith(color: primary, fontSize: 24),
            ),
          ),
          CupertinoButton(
            key: const ValueKey<String>('assistant_skill_detail_close'),
            padding: const EdgeInsets.all(8),
            minimumSize: const Size.square(44),
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
        ('适合谁', widget.targetUserLabels.join('、')),
      if (widget.surfaceLabels.isNotEmpty)
        ('可使用位置', widget.surfaceLabels.join('、')),
      if (widget.dataUseSummary.trim().isNotEmpty)
        ('数据使用', widget.dataUseSummary.trim()),
      if (widget.permissionLabels.isNotEmpty)
        ('需要授权', widget.permissionLabels.join('、')),
    ];
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: rows
            .map(
              (row) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 76,
                      child: Text(
                        row.$1,
                        style: TextStyle(color: secondary, fontSize: 13),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        row.$2,
                        style: TextStyle(
                          color: primary,
                          fontSize: 13,
                          height: 1.4,
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

  Widget _buildUnavailableCard(
    Color background,
    Color primary,
    Color secondary,
  ) {
    return Container(
      key: const ValueKey<String>('assistant_skill_setup_unavailable'),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('设置暂不可用', style: TextStyle(color: primary)),
          const SizedBox(height: 4),
          Text(
            '当前 Skill package 没有提供此版本可安全渲染的设置定义。你仍可使用或停用该 Skill。',
            style: TextStyle(color: secondary, fontSize: 13, height: 1.4),
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
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '${field.title}${field.required ? ' *' : ''}',
            style: TextStyle(color: primary, fontWeight: FontWeight.w600),
          ),
          if (field.description.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              field.description,
              style: TextStyle(color: secondary, fontSize: 12, height: 1.35),
            ),
          ],
          const SizedBox(height: 10),
          if (field.kind == AssistantSkillSetupFieldKind.choice)
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: field.options
                  .map(
                    (option) => CupertinoButton(
                      key: ValueKey<String>(
                        'assistant_skill_setup_${field.id}_$option',
                      ),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 8,
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
                  ? '多项请用逗号分隔'
                  : null,
              onChanged: (_) => setState(() {
                _fieldErrors.remove(field.id);
              }),
            ),
          if (error != null) ...[
            const SizedBox(height: 6),
            Text(
              error,
              style: TextStyle(
                color: CupertinoColors.systemRed.resolveFrom(context),
                fontSize: 12,
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
        _saveError = '设置没有保存，请稍后重试。';
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
