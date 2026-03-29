import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/search_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';

/// 全屏群成员搜索：灰带内搜索框 + 「取消」+ 下方列表区。
class EmbeddedMemberSearchPageShell extends StatelessWidget {
  const EmbeddedMemberSearchPageShell({
    super.key,
    required this.isDark,
    required this.searchController,
    required this.placeholder,
    required this.onQueryChanged,
    required this.onCancel,
    required this.listBody,
  });

  final bool isDark;
  final TextEditingController searchController;
  final String placeholder;
  final ValueChanged<String> onQueryChanged;
  final VoidCallback onCancel;
  final Widget listBody;

  @override
  Widget build(BuildContext context) {
    final chrome = SearchSemanticConstants.embeddedMemberSearchChromeBackground(
      isDark,
    );
    final cancelColor =
        SearchSemanticConstants.embeddedMemberSearchActionLabelColor(isDark);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ColoredBox(
          color: chrome,
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerSm,
                AppSpacing.sm,
                AppSpacing.containerSm,
                AppSpacing.sm,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: AppSearchField(
                      controller: searchController,
                      placeholder: placeholder,
                      onChanged: onQueryChanged,
                      autofocus: true,
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.only(left: AppSpacing.intraGroupSm),
                    minimumSize: Size.zero,
                    onPressed: onCancel,
                    child: Text(
                      UITextConstants.cancel,
                      style: TextStyle(
                        fontSize: AppTypography.iosCallout,
                        fontWeight: AppTypography.medium,
                        color: cancelColor,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        Expanded(child: listBody),
      ],
    );
  }
}
