import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

final class GatheringChoice<T> {
  const GatheringChoice({required this.value, required this.label});

  final T value;
  final String label;
}

class GatheringPageBody extends StatelessWidget {
  const GatheringPageBody({super.key, required this.children, this.bottom});

  final List<Widget> children;
  final Widget? bottom;

  @override
  Widget build(BuildContext context) {
    final horizontal = AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.containerSm,
      regular: AppSpacing.containerMd,
      expanded: AppSpacing.containerXl,
    );
    return SafeArea(
      top: false,
      child: Column(
        children: <Widget>[
          Expanded(
            child: SingleChildScrollView(
              padding: EdgeInsets.symmetric(
                horizontal: horizontal,
                vertical: AppSpacing.containerMd,
              ),
              child: Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.feedMaxContentWidth,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: children,
                  ),
                ),
              ),
            ),
          ),
          if (bottom != null)
            Padding(
              padding: EdgeInsets.fromLTRB(
                horizontal,
                AppSpacing.containerSm,
                horizontal,
                AppSpacing.containerMd,
              ),
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: AppSpacing.feedMaxContentWidth,
                ),
                child: bottom,
              ),
            ),
        ],
      ),
    );
  }
}

class GatheringSectionCard extends StatelessWidget {
  const GatheringSectionCard({
    super.key,
    required this.title,
    required this.child,
  });

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Semantics(
      container: true,
      label: title,
      child: Container(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        decoration: BoxDecoration(
          color: AppColors.iosProfileSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              title,
              style: TextStyle(
                color: foreground,
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            child,
          ],
        ),
      ),
    );
  }
}

class GatheringLabeledTextField extends StatelessWidget {
  const GatheringLabeledTextField({
    super.key,
    required this.label,
    required this.controller,
    required this.placeholder,
    this.keyboardType,
    this.maxLines = 1,
    this.enabled = true,
  });

  final String label;
  final TextEditingController controller;
  final String placeholder;
  final TextInputType? keyboardType;
  final int maxLines;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    return Semantics(
      textField: true,
      label: label,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            label,
            style: TextStyle(
              color: secondary,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          CupertinoTextField(
            controller: controller,
            enabled: enabled,
            keyboardType: keyboardType,
            maxLines: maxLines,
            minLines: maxLines,
            placeholder: placeholder,
            padding: EdgeInsets.all(AppSpacing.containerSm),
            decoration: BoxDecoration(
              color: AppColors.iosPageBackground(context),
              borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
              border: Border.all(color: border, width: AppSpacing.hairline),
            ),
            style: TextStyle(color: foreground, fontSize: AppTypography.base),
            placeholderStyle: TextStyle(
              color: secondary,
              fontSize: AppTypography.base,
            ),
          ),
        ],
      ),
    );
  }
}

class GatheringChoiceField<T> extends StatelessWidget {
  const GatheringChoiceField({
    super.key,
    required this.label,
    required this.value,
    required this.choices,
    required this.onChanged,
  });

  final String label;
  final T value;
  final List<GatheringChoice<T>> choices;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Semantics(
      container: true,
      label: label,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            label,
            style: TextStyle(
              color: secondary,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Wrap(
            spacing: AppSpacing.intraGroupXs,
            runSpacing: AppSpacing.intraGroupXs,
            children: choices
                .map(
                  (choice) => Semantics(
                    selected: choice.value == value,
                    button: true,
                    label: choice.label,
                    child: CupertinoButton(
                      minimumSize: const Size(
                        AppSpacing.minInteractiveSize,
                        AppSpacing.minInteractiveSize,
                      ),
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                        vertical: AppSpacing.containerXs,
                      ),
                      color: choice.value == value
                          ? AppColors.primaryColor
                          : AppColors.iosPageBackground(context),
                      onPressed: () => onChanged(choice.value),
                      child: Text(
                        choice.label,
                        style: TextStyle(
                          color: choice.value == value
                              ? CupertinoColors.white
                              : foreground,
                          fontSize: AppTypography.sm,
                        ),
                      ),
                    ),
                  ),
                )
                .toList(growable: false),
          ),
        ],
      ),
    );
  }
}

class GatheringFactRow extends StatelessWidget {
  const GatheringFactRow({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: Text(
              label,
              style: TextStyle(color: secondary, fontSize: AppTypography.sm),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            flex: 2,
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: TextStyle(color: primary, fontSize: AppTypography.base),
            ),
          ),
        ],
      ),
    );
  }
}
