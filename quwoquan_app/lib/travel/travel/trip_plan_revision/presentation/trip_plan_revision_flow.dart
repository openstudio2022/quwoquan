import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_coordinator.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_item_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 把一次计划调整收敛成一个冻结 intent。任一选择被取消时均不会
/// 触发写操作；重试由调用方复用返回的 intent。
Future<TripPlanRevisionIntent?> composeTripPlanRevision(
  BuildContext context, {
  required TripPlanSlice plan,
  required TripPlanRevisionCoordinator coordinator,
  required String Function() itemIdFactory,
}) async {
  final items = tripPlanItemInputs(plan).toList(growable: true);
  final target = await showAppActionSheet<_RevisionTarget>(
    context,
    title: TravelText.revisePlanTitle,
    message: TravelText.revisePlanMessage,
    sections: <AppActionSheetSection<_RevisionTarget>>[
      const AppActionSheetSection<_RevisionTarget>(
        items: <AppActionSheetItem<_RevisionTarget>>[
          AppActionSheetItem<_RevisionTarget>(
            value: _RevisionTarget.add(),
            label: TravelText.addPlanItem,
            icon: CupertinoIcons.add_circled,
          ),
        ],
      ),
      if (items.isNotEmpty)
        AppActionSheetSection<_RevisionTarget>(
          items: <AppActionSheetItem<_RevisionTarget>>[
            for (final item in items)
              AppActionSheetItem<_RevisionTarget>(
                value: _RevisionTarget.item(item.itemId),
                label:
                    '${TravelText.dayPrefix}${item.dayIndex + 1}${TravelText.daySuffix} · ${item.title}',
                description: tripItemKindLabel(item.kind),
                icon: CupertinoIcons.pencil,
              ),
          ],
        ),
    ],
  );
  if (!context.mounted || target == null) {
    return null;
  }
  final changed = target.itemId == null
      ? await _appendItem(context, items, itemIdFactory)
      : await _changeExisting(context, items, target.itemId!);
  if (!context.mounted || !changed) {
    return null;
  }
  final reason = await _promptText(
    context,
    title: TravelText.changeReasonTitle,
    placeholder: TravelText.changeReasonHint,
  );
  if (!context.mounted || reason == null) {
    return null;
  }
  final severity = await showAppActionSheet<TripRevisionSeverity>(
    context,
    title: TravelText.changeSeverityTitle,
    message: TravelText.changeSeverityMessage,
    sections: const <AppActionSheetSection<TripRevisionSeverity>>[
      AppActionSheetSection<TripRevisionSeverity>(
        items: <AppActionSheetItem<TripRevisionSeverity>>[
          AppActionSheetItem<TripRevisionSeverity>(
            value: TripRevisionSeverity.minor,
            label: TravelText.changeMinor,
            icon: CupertinoIcons.info,
          ),
          AppActionSheetItem<TripRevisionSeverity>(
            value: TripRevisionSeverity.important,
            label: TravelText.changeImportant,
            icon: CupertinoIcons.bell,
          ),
          AppActionSheetItem<TripRevisionSeverity>(
            value: TripRevisionSeverity.critical,
            label: TravelText.changeCritical,
            icon: CupertinoIcons.exclamationmark_triangle,
          ),
        ],
      ),
    ],
  );
  if (!context.mounted || severity == null) {
    return null;
  }
  return coordinator.prepareRevision(
    plan: plan,
    items: items,
    changeReason: reason,
    severity: severity,
  );
}

Future<bool> _appendItem(
  BuildContext context,
  List<TripPlanItemInput> items,
  String Function() itemIdFactory,
) async {
  final title = await _promptText(
    context,
    title: TravelText.planItemTitle,
    placeholder: TravelText.planItemTitleHint,
  );
  if (!context.mounted || title == null) {
    return false;
  }
  final kind = await showAppActionSheet<TripPlanItemKind>(
    context,
    title: TravelText.planItemKindTitle,
    sections: <AppActionSheetSection<TripPlanItemKind>>[
      AppActionSheetSection<TripPlanItemKind>(
        items: <AppActionSheetItem<TripPlanItemKind>>[
          for (final kind in TripPlanItemKind.values)
            AppActionSheetItem<TripPlanItemKind>(
              value: kind,
              label: tripItemKindLabel(kind),
            ),
        ],
      ),
    ],
  );
  if (!context.mounted || kind == null) {
    return false;
  }
  final existingDays = items.map((item) => item.dayIndex).toSet();
  final nextDay = existingDays.isEmpty
      ? 0
      : existingDays.reduce((left, right) => left > right ? left : right) + 1;
  final days = <int>{...existingDays, nextDay}.toList()..sort();
  final dayIndex = await showAppActionSheet<int>(
    context,
    title: TravelText.planItemDayTitle,
    sections: <AppActionSheetSection<int>>[
      AppActionSheetSection<int>(
        items: <AppActionSheetItem<int>>[
          for (final day in days)
            AppActionSheetItem<int>(
              value: day,
              label: '${TravelText.dayPrefix}${day + 1}${TravelText.daySuffix}',
              icon: CupertinoIcons.calendar,
            ),
        ],
      ),
    ],
  );
  if (dayIndex == null) {
    return false;
  }
  final itemId = itemIdFactory().trim();
  if (itemId.isEmpty) {
    throw StateError('TripPlan item id must not be blank');
  }
  final order =
      items
          .where((item) => item.dayIndex == dayIndex)
          .fold<int>(
            -1,
            (value, item) => item.orderInDay > value ? item.orderInDay : value,
          ) +
      1;
  items.add(
    TripPlanItemInput(
      itemId: itemId,
      dayIndex: dayIndex,
      orderInDay: order,
      kind: kind,
      title: title,
    ),
  );
  return true;
}

Future<bool> _changeExisting(
  BuildContext context,
  List<TripPlanItemInput> items,
  String itemId,
) async {
  final index = items.indexWhere((item) => item.itemId == itemId);
  if (index < 0) {
    return false;
  }
  final action = await showAppActionSheet<_ExistingAction>(
    context,
    title: items[index].title,
    sections: const <AppActionSheetSection<_ExistingAction>>[
      AppActionSheetSection<_ExistingAction>(
        items: <AppActionSheetItem<_ExistingAction>>[
          AppActionSheetItem<_ExistingAction>(
            value: _ExistingAction.rename,
            label: TravelText.renamePlanItem,
            icon: CupertinoIcons.pencil,
          ),
          AppActionSheetItem<_ExistingAction>(
            value: _ExistingAction.remove,
            label: TravelText.removePlanItem,
            icon: CupertinoIcons.delete,
            isDestructive: true,
          ),
        ],
      ),
    ],
  );
  if (!context.mounted || action == null) {
    return false;
  }
  if (action == _ExistingAction.remove) {
    items.removeAt(index);
    return true;
  }
  final title = await _promptText(
    context,
    title: TravelText.renamePlanItem,
    placeholder: TravelText.planItemTitleHint,
    initialValue: items[index].title,
  );
  if (title == null || title == items[index].title.trim()) {
    return false;
  }
  final current = items[index];
  items[index] = TripPlanItemInput(
    itemId: current.itemId,
    dayIndex: current.dayIndex,
    orderInDay: current.orderInDay,
    kind: current.kind,
    title: title,
    startAt: current.startAt,
    endAt: current.endAt,
    placeRef: current.placeRef,
    note: current.note,
  );
  return true;
}

Future<String?> _promptText(
  BuildContext context, {
  required String title,
  required String placeholder,
  String initialValue = '',
}) async {
  final controller = TextEditingController(text: initialValue);
  try {
    final result = await showAppCupertinoDialog<String>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(title),
        content: Padding(
          padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
          child: CupertinoTextField(
            controller: controller,
            autofocus: true,
            placeholder: placeholder,
            textInputAction: TextInputAction.done,
            onSubmitted: (value) =>
                Navigator.of(dialogContext).pop(value.trim()),
          ),
        ),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () =>
                Navigator.of(dialogContext).pop(controller.text.trim()),
            child: const Text(CommunityText.done),
          ),
        ],
      ),
    );
    final normalized = result?.trim() ?? '';
    return normalized.isEmpty ? null : normalized;
  } finally {
    controller.dispose();
  }
}

final class _RevisionTarget {
  const _RevisionTarget.add() : itemId = null;
  const _RevisionTarget.item(this.itemId);

  final String? itemId;
}

enum _ExistingAction { rename, remove }
