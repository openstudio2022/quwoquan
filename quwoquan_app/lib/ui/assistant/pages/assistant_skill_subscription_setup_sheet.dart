import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

const String assistantSkillSubscriptionDefaultTimezone = 'Asia/Shanghai';

final class AssistantSkillSubscriptionSetup {
  const AssistantSkillSubscriptionSetup({
    required this.rawText,
    required this.hour,
    required this.minute,
    this.timezone = assistantSkillSubscriptionDefaultTimezone,
  });

  final String rawText;
  final int hour;
  final int minute;
  final String timezone;

  String get cron => '$minute $hour * * *';
}

Future<AssistantSkillSubscriptionSetup?>
showAssistantSkillSubscriptionSetupSheet({
  required BuildContext context,
  required String skillName,
}) {
  return showCupertinoModalPopup<AssistantSkillSubscriptionSetup>(
    context: context,
    barrierDismissible: true,
    builder: (context) =>
        _AssistantSkillSubscriptionSetupSheet(skillName: skillName),
  );
}

class _AssistantSkillSubscriptionSetupSheet extends StatefulWidget {
  const _AssistantSkillSubscriptionSetupSheet({required this.skillName});

  final String skillName;

  @override
  State<_AssistantSkillSubscriptionSetupSheet> createState() =>
      _AssistantSkillSubscriptionSetupSheetState();
}

class _AssistantSkillSubscriptionSetupSheetState
    extends State<_AssistantSkillSubscriptionSetupSheet> {
  late final TextEditingController _topicController;
  DateTime _time = DateTime(2026, 1, 1, 8);
  String? _validationError;

  @override
  void initState() {
    super.initState();
    _topicController = TextEditingController(
      text: AssistantText.assistantSkillSubscriptionDefaultTopic(
        widget.skillName,
      ),
    );
  }

  @override
  void dispose() {
    _topicController.dispose();
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
    return CupertinoPopupSurface(
      isSurfacePainted: true,
      child: Container(
        key: const ValueKey<String>('assistant_skill_subscription_setup_sheet'),
        height:
            MediaQuery.sizeOf(context).height *
            AppSpacing.modalSheetMaxHeightRatio,
        color: background,
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              Padding(
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
                        AssistantText.assistantSkillSubscriptionSetupTitle,
                        style: theme.textTheme.navLargeTitleTextStyle.copyWith(
                          color: primary,
                          fontSize: AppTypography.iosTitle2,
                        ),
                      ),
                    ),
                    CupertinoButton(
                      key: const ValueKey<String>(
                        'assistant_skill_subscription_setup_close',
                      ),
                      padding: const EdgeInsets.all(AppSpacing.sm),
                      minimumSize: const Size.square(
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () => Navigator.of(context).pop(),
                      child: Icon(
                        CupertinoIcons.xmark_circle_fill,
                        color: secondary,
                      ),
                    ),
                  ],
                ),
              ),
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
                      Text(
                        AssistantText
                            .assistantSkillSubscriptionSetupDescription,
                        style: theme.textTheme.textStyle.copyWith(
                          color: secondary,
                          fontSize: AppTypography.smPlus,
                          height: AppTypography.bodyLineHeight,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.eighteen),
                      Text(
                        AssistantText.assistantSkillSubscriptionTopicTitle,
                        style: theme.textTheme.navTitleTextStyle.copyWith(
                          color: primary,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      CupertinoTextField(
                        key: const ValueKey<String>(
                          'assistant_skill_subscription_setup_topic',
                        ),
                        controller: _topicController,
                        minLines: 2,
                        maxLines: 4,
                        placeholder: AssistantText
                            .assistantSkillSubscriptionTopicPlaceholder,
                        padding: const EdgeInsets.all(
                          AppSpacing.sm + AppSpacing.xs,
                        ),
                      ),
                      if (_validationError != null) ...[
                        const SizedBox(height: AppSpacing.six),
                        Text(
                          _validationError!,
                          key: const ValueKey<String>(
                            'assistant_skill_subscription_setup_error',
                          ),
                          style: theme.textTheme.textStyle.copyWith(
                            color: CupertinoColors.systemRed.resolveFrom(
                              context,
                            ),
                            fontSize: AppTypography.smPlus,
                          ),
                        ),
                      ],
                      const SizedBox(height: AppSpacing.twenty),
                      Text(
                        AssistantText.assistantSkillSubscriptionTimeTitle,
                        style: theme.textTheme.navTitleTextStyle.copyWith(
                          color: primary,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.six),
                      Text(
                        AssistantText.assistantSkillSubscriptionTimezoneLabel,
                        style: theme.textTheme.textStyle.copyWith(
                          color: secondary,
                          fontSize: AppTypography.smPlus,
                        ),
                      ),
                      Container(
                        margin: const EdgeInsets.only(top: AppSpacing.sm),
                        height: AppSpacing.oneHundredSixty + AppSpacing.sm,
                        decoration: BoxDecoration(
                          color: grouped,
                          borderRadius: BorderRadius.circular(
                            AppSpacing.largeBorderRadius,
                          ),
                        ),
                        child: CupertinoDatePicker(
                          key: const ValueKey<String>(
                            'assistant_skill_subscription_setup_time',
                          ),
                          mode: CupertinoDatePickerMode.time,
                          use24hFormat: true,
                          minuteInterval: 5,
                          initialDateTime: _time,
                          onDateTimeChanged: (value) => _time = value,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.eighteen),
                      CupertinoButton.filled(
                        key: const ValueKey<String>(
                          'assistant_skill_subscription_setup_save',
                        ),
                        onPressed: _save,
                        child: const Text(
                          AssistantText.assistantSkillSubscriptionEnable,
                        ),
                      ),
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

  void _save() {
    final rawText = _topicController.text.trim();
    if (rawText.isEmpty) {
      setState(
        () => _validationError =
            AssistantText.assistantSkillSubscriptionTopicRequired,
      );
      return;
    }
    Navigator.of(context).pop(
      AssistantSkillSubscriptionSetup(
        rawText: rawText,
        hour: _time.hour,
        minute: _time.minute,
      ),
    );
  }
}
