part of 'assistant_message_bubble.dart';

class _AssistantFollowupCard extends StatelessWidget {
  const _AssistantFollowupCard({
    required this.followupPrompt,
    required this.actionHints,
    this.onActionHintTap,
  });

  final String followupPrompt;
  final List<String> actionHints;
  final Future<void> Function(String hint)? onActionHintTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (followupPrompt.isNotEmpty)
            Text(
              followupPrompt,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
              ),
            ),
          if (actionHints.isNotEmpty) ...[
            if (followupPrompt.isNotEmpty) SizedBox(height: AppSpacing.xs),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: actionHints
                  .map(
                    (hint) => CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: onActionHintTap == null
                          ? null
                          : () => onActionHintTap!(hint),
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerSm,
                          vertical: AppSpacing.xs,
                        ),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.fullBorderRadius,
                          ),
                          color: AppColors.white.withValues(alpha: 0.8),
                        ),
                        child: Text(
                          hint,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: AppColors.primaryColor,
                          ),
                        ),
                      ),
                    ),
                  )
                  .toList(growable: false),
            ),
          ],
        ],
      ),
    );
  }
}
