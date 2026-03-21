import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/assistant/config/assistant_prompt_config.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';

/// 小趣半弹窗：约 50% 屏高、可拖拽，展示欢迎句、推荐 chips、「当前适合干啥」、输入框与「进入完整对话」。
class AssistantHalfSheet extends StatelessWidget {
  const AssistantHalfSheet({
    super.key,
    required this.openContext,
  });

  final AssistantOpenContext openContext;

  /// 展示半弹窗；调用方需传入已组装的 [AssistantOpenContext]。
  static Future<void> show(
    BuildContext modalContext,
    AssistantOpenContext assistantOpenContext,
  ) async {
    await Future<void>.delayed(Duration.zero);
    if (!modalContext.mounted) return;
    modalContext.push(
      AppRoutePaths.chatDetail(id: AppConceptConstants.assistantConversationId),
      extra: assistantOpenContext,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final containerMd = AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd;
    final intraSm = AppSpacing.semantic[DesignSemanticConstants.intraGroup]?[DesignSemanticConstants.sm] ?? AppSpacing.intraGroupSm;

    final welcome = AssistantPromptConfig.getWelcomeMessage(openContext);
    final chips = AssistantPromptConfig.getChips(openContext);
    final suggestions = AssistantPromptConfig.getSuggestionLines(openContext);

    return Container(
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.borderRadius * 2),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(height: intraSm),
            Container(
              width: AppSpacing.createEntrySheetHandleWidth,
              height: AppSpacing.createEntrySheetHandleHeight,
              decoration: BoxDecoration(
                color: fgSecondary.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            SizedBox(height: containerMd),
            Row(
              children: [
                SizedBox(width: containerMd),
                AssistantAvatar(radius: AppSpacing.avatarUserSm / 2),
                SizedBox(width: intraSm),
                Expanded(
                  child: Text(
                    AppConceptConstants.assistantLabel,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                ),
                IconButton(
                  icon: Icon(Icons.close, color: fgSecondary, size: AppSpacing.iconMedium),
                  onPressed: () => Navigator.of(context).pop(),
                  style: IconButton.styleFrom(
                    minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                  ),
                  tooltip: UITextConstants.cancel,
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
              ],
            ),
            SizedBox(height: containerMd),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: containerMd),
              child: Text(
                welcome,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: fgPrimary,
                ),
              ),
            ),
            SizedBox(height: containerMd),
            Wrap(
              spacing: intraSm,
              runSpacing: intraSm,
              children: chips
                  .map(
                    (c) => ActionChip(
                      label: c.label,
                      onPressed: () {
                        // TODO: 根据 actionType/value 发指令或跳转
                      },
                    ),
                  )
                  .toList(),
            ),
            if (suggestions.isNotEmpty) ...[
              SizedBox(height: containerMd),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: containerMd),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    UITextConstants.assistantHalfSheetSuggestionTitle,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.medium,
                      color: fgSecondary,
                    ),
                  ),
                ),
              ),
              SizedBox(height: intraSm),
              ...suggestions.map(
                (s) => Padding(
                  padding: EdgeInsets.symmetric(horizontal: containerMd),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      s,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ),
                ),
              ),
            ],
            const Spacer(),
            Padding(
              padding: EdgeInsets.fromLTRB(containerMd, intraSm, containerMd, containerMd),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      decoration: InputDecoration(
                        hintText: UITextConstants.assistantHalfSheetInputPlaceholder,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                        ),
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: containerMd,
                          vertical: intraSm,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: intraSm),
                  FilledButton(
                    onPressed: () {
                      Navigator.of(context).pop();
                      context.push(
                        AppRoutePaths.chatDetail(
                          id: AppConceptConstants.assistantConversationId,
                        ),
                        extra: openContext,
                      );
                    },
                    child: Text(UITextConstants.assistantHalfSheetEnterFullChat),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ActionChip extends StatelessWidget {
  const ActionChip({
    super.key,
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final surface =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);

    return Material(
      color: surface,
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.sm + AppSpacing.xs,
            vertical: AppSpacing.xs,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: fgPrimary,
            ),
          ),
        ),
      ),
    );
  }
}
