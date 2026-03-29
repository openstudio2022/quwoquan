import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/search_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';

/// 顶栏下方的内嵌搜索条（灰带 + [AppSearchField]）。
class EmbeddedMemberSearchBarPlain extends StatelessWidget {
  const EmbeddedMemberSearchBarPlain({
    super.key,
    required this.isDark,
    required this.controller,
    required this.placeholder,
    required this.onChanged,
  });

  final bool isDark;
  final TextEditingController controller;
  final String placeholder;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: SearchSemanticConstants.embeddedMemberSearchChromeBackground(
        isDark,
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.sm,
          AppSpacing.containerMd,
          AppSpacing.sm,
        ),
        child: AppSearchField(
          controller: controller,
          placeholder: placeholder,
          onChanged: onChanged,
        ),
      ),
    );
  }
}
