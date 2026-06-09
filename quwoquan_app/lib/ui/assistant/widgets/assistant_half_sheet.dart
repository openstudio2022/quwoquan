import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/assistant/config/assistant_prompt_config.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';

final assistantHalfSheetPersonalizationProvider =
    FutureProvider.autoDispose
        .family<AssistantHalfSheetPersonalization, AssistantOpenContext>((
          ref,
          openContext,
        ) async {
          final repository = ref.read(assistantRepositoryProvider);
          await repository.reportPageContext(
            context: openContext,
            userAction: 'open_assistant_entry',
          );
          final personalization = await repository.getEntryPersonalization(
            context: openContext,
          );
          final suggestedActions = await repository.getSuggestedActions(
            context: openContext,
          );
          return AssistantHalfSheetPersonalization(
            welcomeMessage: personalization.welcomeMessage.trim().isEmpty
                ? AssistantPromptConfig.getWelcomeMessage(openContext)
                : personalization.welcomeMessage.trim(),
            chips: personalization.chips.isEmpty
                ? AssistantPromptConfig.getChips(openContext)
                : personalization.chips
                      .map(
                        (chip) => AssistantChipEntry(
                          label: chip.label,
                          actionType: chip.actionType,
                          value: chip.value,
                        ),
                      )
                      .toList(growable: false),
            suggestionLines: suggestedActions.items.isEmpty
                ? (personalization.suggestionLines.isEmpty
                      ? AssistantPromptConfig.getSuggestionLines(openContext)
                      : personalization.suggestionLines)
                : suggestedActions.items
                      .map((item) => item.label.trim())
                      .where((label) => label.isNotEmpty)
                      .take(2)
                      .toList(growable: false),
          );
        });

class AssistantHalfSheetPersonalization {
  const AssistantHalfSheetPersonalization({
    required this.welcomeMessage,
    required this.chips,
    required this.suggestionLines,
  });

  final String welcomeMessage;
  final List<AssistantChipEntry> chips;
  final List<String> suggestionLines;
}

/// 私助半弹窗：约 50% 屏高、可拖拽，展示欢迎句、推荐 chips、「当前适合干啥」、输入框与「进入完整对话」。
class AssistantHalfSheet extends ConsumerWidget {
  const AssistantHalfSheet({super.key, required this.openContext});

  final AssistantOpenContext openContext;

  /// 展示半弹窗；调用方需传入已组装的 [AssistantOpenContext]。
  static Future<void> show(
    BuildContext modalContext,
    AssistantOpenContext assistantOpenContext,
  ) async {
    await Future<void>.delayed(Duration.zero);
    if (!modalContext.mounted) return;
    modalContext.push(
      AppRoutePaths.assistantPersonal,
      extra: assistantOpenContext,
    );
  }

  /// chip 点击真实分发（B4）：按 actionType 落地真实指令/跳转，消除 TODO 占位。
  /// command → 进入会话页并携带指令；route → 跳转目标路由；setting → 打开设置。
  /// 仅在用户主动打开半弹窗时出现，无自动弹窗骚扰（克制出现）。
  void _dispatchChip(BuildContext context, AssistantChipEntry chip) {
    Navigator.of(context).pop();
    switch (chip.actionType) {
      case 'route':
        switch (chip.value) {
          case 'circles':
            context.push(AppRoutePaths.circles);
            return;
          case 'create':
            context.push(AppRoutePaths.create());
            return;
        }
        context.push(AppRoutePaths.assistantPersonal, extra: openContext);
        return;
      case 'setting':
        context.push(AppRoutePaths.settings);
        return;
      case 'command':
      default:
        context.push(
          AppRoutePaths.assistantPersonal,
          extra: openContext.copyWith(
            hints: <String, dynamic>{
              ...openContext.hints,
              'command': chip.value ?? '',
            },
          ),
        );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final containerMd =
        AppSpacing.semantic[DesignSemanticConstants
            .container]?[DesignSemanticConstants.md] ??
        AppSpacing.containerMd;
    final intraSm =
        AppSpacing.semantic[DesignSemanticConstants
            .intraGroup]?[DesignSemanticConstants.sm] ??
        AppSpacing.intraGroupSm;

    final fallback = AssistantHalfSheetPersonalization(
      welcomeMessage: AssistantPromptConfig.getWelcomeMessage(openContext),
      chips: AssistantPromptConfig.getChips(openContext),
      suggestionLines: AssistantPromptConfig.getSuggestionLines(openContext),
    );
    final personalization = ref
        .watch(assistantHalfSheetPersonalizationProvider(openContext))
        .maybeWhen(data: (value) => value, orElse: () => fallback);
    final welcome = personalization.welcomeMessage;
    final chips = personalization.chips;
    final suggestions = personalization.suggestionLines;

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
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
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
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                  onPressed: () => Navigator.of(context).pop(),
                  child: Icon(
                    CupertinoIcons.xmark,
                    color: fgSecondary,
                    size: AppSpacing.iconMedium,
                  ),
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
                      onPressed: () => _dispatchChip(context, c),
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
              padding: EdgeInsets.fromLTRB(
                containerMd,
                intraSm,
                containerMd,
                containerMd,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      decoration: InputDecoration(
                        hintText:
                            UITextConstants.assistantHalfSheetInputPlaceholder,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.borderRadius,
                          ),
                        ),
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: containerMd,
                          vertical: intraSm,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: intraSm),
                  CupertinoButton.filled(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.sm,
                    ),
                    onPressed: () {
                      Navigator.of(context).pop();
                      context.push(
                        AppRoutePaths.assistantPersonal,
                        extra: openContext,
                      );
                    },
                    child: Text(
                      UITextConstants.assistantHalfSheetEnterFullChat,
                    ),
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
  const ActionChip({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );

    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm + AppSpacing.xs,
          vertical: AppSpacing.xs,
        ),
        minimumSize: Size.zero,
        onPressed: onPressed,
        child: Text(
          label,
          style: TextStyle(fontSize: AppTypography.sm, color: fgPrimary),
        ),
      ),
    );
  }
}
