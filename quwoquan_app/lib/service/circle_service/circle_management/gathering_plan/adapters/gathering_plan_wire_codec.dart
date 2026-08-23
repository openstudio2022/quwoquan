import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

/// GatheringPlan 是 Gathering 的可选伴生对象，看板只读其 current Revision。
///
/// Story `gathering-plan-collaboration` 把 App Board 写入列为 Out of Scope，
/// 因此本 codec 只做 wire → 展示投影，不提供任何提案/commit 编码。
/// typed PlanItem 的 place/route 只保存 canonical reference（REQ-002 禁止复制
/// 来源对象正文），看板摘要因此只展示人工填写的 instruction，不解析地点名。
GatheringBoardPlanSlice gatheringBoardPlanFromWire(cloud.GatheringPlan wire) {
  final current = _currentRevision(wire);
  if (current == null) {
    // currentRevisionId 指不到任何已提交 Revision 属于 owner 数据不一致，
    // 是失败而非「计划为空」，不得塌陷成 notConfigured。
    return gatheringBoardPlanUnavailable(
      GatheringBoardCapabilityUnavailableReason.temporarilyUnavailable,
      ChatText.boardPlanUnavailable,
    );
  }
  final items = [...current.items]
    ..sort((left, right) => left.order.compareTo(right.order));
  return GatheringBoardPlanSlice(
    capability: GatheringBoardCapabilitySummary(
      state: GatheringBoardCapabilityState.available,
      summaryLabel: ChatText.boardPlanSummary(
        current.revisionNumber,
        items.length,
      ),
      itemCount: items.length,
    ),
    items: items.map(_boardItem).toList(growable: false),
  );
}

/// 计划不可读时的看板投影：reason 区分「未创建」「无权限」「暂时失败」。
GatheringBoardPlanSlice gatheringBoardPlanUnavailable(
  GatheringBoardCapabilityUnavailableReason reason,
  String label,
) => GatheringBoardPlanSlice(
  capability: GatheringBoardCapabilitySummary(
    state: GatheringBoardCapabilityState.unavailable,
    summaryLabel: label,
    unavailableReason: reason,
    unavailableLabel: label,
  ),
);

cloud.PlanRevision? _currentRevision(cloud.GatheringPlan wire) {
  for (final revision in wire.revisions) {
    if (revision.revisionId == wire.currentRevisionId) {
      return revision;
    }
  }
  return null;
}

GatheringBoardPlanItem _boardItem(cloud.PlanItem item) => switch (item.kind) {
  cloud.PlanItemKind.agenda => _agendaItem(item, item.agenda),
  cloud.PlanItemKind.place => _placeItem(item, item.place),
  cloud.PlanItemKind.routeSegment => _routeItem(item, item.routeSegment),
  cloud.PlanItemKind.task => _taskItem(item, item.task),
  cloud.PlanItemKind.checklist => _checklistItem(item, item.checklist),
  cloud.PlanItemKind.note => _noteItem(item, item.note),
};

GatheringBoardPlanItem _agendaItem(
  cloud.PlanItem item,
  cloud.PlanAgendaItem? agenda,
) {
  if (agenda == null) {
    return _typedPayloadMissing(item);
  }
  final startsAt = agenda.startsAt;
  final durationMinutes = agenda.durationMinutes;
  final parts = <String>[
    if (startsAt != null) _timeLabel(startsAt),
    if (durationMinutes != null) ChatText.boardPlanDuration(durationMinutes),
  ];
  return GatheringBoardPlanItem(
    planItemId: item.itemId,
    title: agenda.content,
    detail: parts.join(' · '),
    completed: false,
  );
}

GatheringBoardPlanItem _placeItem(
  cloud.PlanItem item,
  cloud.PlanPlaceItem? place,
) {
  if (place == null) {
    return _typedPayloadMissing(item);
  }
  final instruction = place.instruction?.trim() ?? '';
  return GatheringBoardPlanItem(
    planItemId: item.itemId,
    title: instruction.isEmpty ? ChatText.boardPlanPlaceItem : instruction,
    detail: '',
    completed: false,
  );
}

GatheringBoardPlanItem _routeItem(
  cloud.PlanItem item,
  cloud.PlanRouteSegmentItem? route,
) {
  if (route == null) {
    return _typedPayloadMissing(item);
  }
  final instruction = route.instruction?.trim() ?? '';
  final estimatedMinutes = route.estimatedMinutes;
  final parts = <String>[
    _travelModeLabel(route.travelMode),
    if (estimatedMinutes != null)
      ChatText.boardPlanTravelDuration(estimatedMinutes),
  ];
  return GatheringBoardPlanItem(
    planItemId: item.itemId,
    title: instruction.isEmpty ? ChatText.boardPlanRouteItem : instruction,
    detail: parts.join(' · '),
    completed: false,
  );
}

GatheringBoardPlanItem _taskItem(
  cloud.PlanItem item,
  cloud.PlanTaskItem? task,
) {
  if (task == null) {
    return _typedPayloadMissing(item);
  }
  final dueAt = task.dueAt;
  return GatheringBoardPlanItem(
    planItemId: item.itemId,
    title: task.content,
    detail: dueAt == null ? '' : ChatText.boardPlanDueAt(_dateLabel(dueAt)),
    completed: task.completed,
  );
}

GatheringBoardPlanItem _checklistItem(
  cloud.PlanItem item,
  cloud.PlanChecklistItem? checklist,
) {
  if (checklist == null) {
    return _typedPayloadMissing(item);
  }
  final entries = checklist.entries;
  final checked = entries.where((entry) => entry.checked).length;
  return GatheringBoardPlanItem(
    planItemId: item.itemId,
    title: ChatText.boardPlanChecklistItem,
    detail: ChatText.boardPlanChecklistProgress(checked, entries.length),
    completed: entries.isNotEmpty && checked == entries.length,
  );
}

GatheringBoardPlanItem _noteItem(
  cloud.PlanItem item,
  cloud.PlanNoteItem? note,
) {
  if (note == null) {
    return _typedPayloadMissing(item);
  }
  return GatheringBoardPlanItem(
    planItemId: item.itemId,
    title: note.content,
    detail: '',
    completed: false,
  );
}

/// kind 与 typed payload 不匹配时保留计划项本身，避免静默丢条目。
GatheringBoardPlanItem _typedPayloadMissing(cloud.PlanItem item) =>
    GatheringBoardPlanItem(
      planItemId: item.itemId,
      title: ChatText.boardPlanGenericItem,
      detail: '',
      completed: false,
    );

String _travelModeLabel(cloud.PlanTravelMode mode) => switch (mode) {
  cloud.PlanTravelMode.walk => ChatText.boardPlanTravelWalk,
  cloud.PlanTravelMode.bicycle => ChatText.boardPlanTravelBicycle,
  cloud.PlanTravelMode.transit => ChatText.boardPlanTravelTransit,
  cloud.PlanTravelMode.drive => ChatText.boardPlanTravelDrive,
  cloud.PlanTravelMode.ferry => ChatText.boardPlanTravelFerry,
  cloud.PlanTravelMode.other => ChatText.boardPlanTravelOther,
};

String _timeLabel(DateTime value) {
  final local = value.toLocal();
  return '${local.hour.toString().padLeft(2, '0')}:'
      '${local.minute.toString().padLeft(2, '0')}';
}

String _dateLabel(DateTime value) {
  final local = value.toLocal();
  return '${local.year}-${local.month.toString().padLeft(2, '0')}-'
      '${local.day.toString().padLeft(2, '0')}';
}
