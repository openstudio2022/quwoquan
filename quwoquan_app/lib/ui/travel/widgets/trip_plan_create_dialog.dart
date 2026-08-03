import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';

/// 只收集创建共同旅行所必需的标题。日期和计划项可在 Trip
/// 创建后由群成员与小趣渐进补充，不在入口制造一次性长表单。
Future<String?> showTripPlanCreateDialog(BuildContext context) async {
  final controller = TextEditingController();
  try {
    return await showCupertinoDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) {
          final title = controller.text.trim();
          return CupertinoAlertDialog(
            title: const Text(TravelText.createTripTitle),
            content: Padding(
              padding: EdgeInsets.only(top: AppSpacing.containerSm),
              child: CupertinoTextField(
                key: const ValueKey<String>('travel-trip-title-field'),
                controller: controller,
                autofocus: true,
                placeholder: TravelText.createTripTitleHint,
                textInputAction: TextInputAction.done,
                onChanged: (_) => setDialogState(() {}),
                onSubmitted: (_) {
                  if (title.isNotEmpty) {
                    Navigator.of(dialogContext).pop(title);
                  }
                },
              ),
            ),
            actions: <Widget>[
              CupertinoDialogAction(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text(TravelText.cancel),
              ),
              CupertinoDialogAction(
                key: const ValueKey<String>('travel-create-confirm'),
                isDefaultAction: true,
                onPressed: title.isEmpty
                    ? null
                    : () => Navigator.of(dialogContext).pop(title),
                child: const Text(TravelText.createTripAction),
              ),
            ],
          );
        },
      ),
    );
  } finally {
    controller.dispose();
  }
}
