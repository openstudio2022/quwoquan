import 'package:flutter/cupertino.dart';

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
      text: '提醒我关注${widget.skillName}的重要变化和下一步',
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
        height: MediaQuery.sizeOf(context).height * 0.76,
        color: background,
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 12, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '设置主动提醒',
                        style: theme.textTheme.navLargeTitleTextStyle.copyWith(
                          color: primary,
                          fontSize: 24,
                        ),
                      ),
                    ),
                    CupertinoButton(
                      key: const ValueKey<String>(
                        'assistant_skill_subscription_setup_close',
                      ),
                      padding: const EdgeInsets.all(8),
                      minimumSize: const Size.square(44),
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
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        '小趣会按设定时间检查你关注的变化；静默时段、频控和最终投递仍由服务端策略控制。',
                        style: theme.textTheme.textStyle.copyWith(
                          color: secondary,
                          fontSize: 13,
                          height: 1.4,
                        ),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        '提醒关注什么',
                        style: theme.textTheme.navTitleTextStyle.copyWith(
                          color: primary,
                        ),
                      ),
                      const SizedBox(height: 8),
                      CupertinoTextField(
                        key: const ValueKey<String>(
                          'assistant_skill_subscription_setup_topic',
                        ),
                        controller: _topicController,
                        minLines: 2,
                        maxLines: 4,
                        placeholder: '例如：行程天气、交通变化和集合时间',
                        padding: const EdgeInsets.all(12),
                      ),
                      if (_validationError != null) ...[
                        const SizedBox(height: 6),
                        Text(
                          _validationError!,
                          key: const ValueKey<String>(
                            'assistant_skill_subscription_setup_error',
                          ),
                          style: theme.textTheme.textStyle.copyWith(
                            color: CupertinoColors.systemRed.resolveFrom(
                              context,
                            ),
                            fontSize: 13,
                          ),
                        ),
                      ],
                      const SizedBox(height: 20),
                      Text(
                        '每天检查时间',
                        style: theme.textTheme.navTitleTextStyle.copyWith(
                          color: primary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '北京时间（Asia/Shanghai）',
                        style: theme.textTheme.textStyle.copyWith(
                          color: secondary,
                          fontSize: 13,
                        ),
                      ),
                      Container(
                        margin: const EdgeInsets.only(top: 8),
                        height: 168,
                        decoration: BoxDecoration(
                          color: grouped,
                          borderRadius: BorderRadius.circular(14),
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
                      const SizedBox(height: 18),
                      CupertinoButton.filled(
                        key: const ValueKey<String>(
                          'assistant_skill_subscription_setup_save',
                        ),
                        onPressed: _save,
                        child: const Text('开启主动提醒'),
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
      setState(() => _validationError = '请填写要关注的变化');
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
