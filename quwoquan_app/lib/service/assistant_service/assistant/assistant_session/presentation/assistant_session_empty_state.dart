import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_prompt_config.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';

class AssistantSessionEmptyState extends StatelessWidget {
  const AssistantSessionEmptyState({
    super.key,
    required this.openContext,
    required this.foreground,
    required this.onSuggestionSelected,
  });

  final AssistantOpenContext? openContext;
  final Color foreground;
  final ValueChanged<String> onSuggestionSelected;

  @override
  Widget build(BuildContext context) {
    final contextValue = openContext;
    final chips = contextValue == null
        ? <AssistantChipEntry>[
            AssistantChipEntry(label: AssistantText.assistantCommandFind),
            AssistantChipEntry(label: AssistantText.assistantCommandRemember),
            AssistantChipEntry(label: AssistantText.assistantCommandPlan),
          ]
        : AssistantSessionPromptConfig.getChips(contextValue)
              .where((chip) => chip.actionType == 'command')
              .toList(growable: false);
    final suggestions = contextValue == null
        ? const <String>[]
        : AssistantSessionPromptConfig.getSuggestionLines(contextValue);
    return Center(
      child: SingleChildScrollView(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.sparkles,
              size: AppSpacing.iconLarge,
              color: foreground,
            ),
            SizedBox(height: AppSpacing.interGroupSm),
            Text(
              contextValue == null
                  ? AssistantText.assistantWelcomeHeadline
                  : AssistantSessionPromptConfig.getWelcomeMessage(
                      contextValue,
                    ),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
                color: foreground,
              ),
            ),
            if (suggestions.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                suggestions.first,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: foreground.withValues(alpha: 0.72),
                ),
              ),
            ],
            if (chips.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: AppSpacing.intraGroupSm,
                runSpacing: AppSpacing.intraGroupSm,
                children: chips
                    .map(
                      (chip) => CupertinoButton(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerSm,
                          vertical: AppSpacing.intraGroupXs,
                        ),
                        onPressed: () => onSuggestionSelected(chip.label),
                        child: Text(chip.label),
                      ),
                    )
                    .toList(growable: false),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
