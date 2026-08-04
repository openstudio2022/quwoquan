import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripPlanRevisionIntent {
  const TripPlanRevisionIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final ReviseTripPlanCommand command;
  final String idempotencyKey;
}

final class TripPlanTransitionIntent {
  const TripPlanTransitionIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final TransitionTripPlanCommand command;
  final String idempotencyKey;
}

/// 在调用 Remote 前冻结 current revision、整份计划与幂等键。
/// 冲突后必须回读新 revision 再生成新意图，不得偷偷改写 CAS。
final class TripPlanRevisionCoordinator {
  TripPlanRevisionCoordinator(this._facet, this._idempotencyKeyFactory);

  final TripPlanRevisionFacet _facet;
  final String Function() _idempotencyKeyFactory;

  TripPlanRevisionIntent prepareRevision({
    required TripPlanSlice plan,
    required List<TripPlanItemInput> items,
    required String changeReason,
    required TripRevisionSeverity severity,
  }) {
    final tripId = plan.tripId.trim();
    final reason = changeReason.trim();
    if (tripId.isEmpty || plan.currentRevisionNumber <= 0 || reason.isEmpty) {
      throw ArgumentError('Trip revision identity and reason are required');
    }
    final normalizedItems = _normalizeItems(items);
    if (_sameItems(plan.items, normalizedItems)) {
      throw ArgumentError('Trip revision must contain an observable change');
    }
    return TripPlanRevisionIntent(
      command: ReviseTripPlanCommand(
        tripId: tripId,
        expectedRevisionNumber: plan.currentRevisionNumber,
        changeReason: reason,
        severity: severity,
        items: normalizedItems,
      ),
      idempotencyKey: _nextKey(),
    );
  }

  TripPlanTransitionIntent prepareTransition({
    required TripPlanSlice plan,
    required TripPlanStatus targetStatus,
  }) {
    if (!_canTransition(plan.status, targetStatus)) {
      throw ArgumentError.value(targetStatus, 'targetStatus');
    }
    return TripPlanTransitionIntent(
      command: TransitionTripPlanCommand(
        tripId: plan.tripId,
        expectedRevisionNumber: plan.currentRevisionNumber,
        targetStatus: targetStatus,
      ),
      idempotencyKey: _nextKey(),
    );
  }

  Future<TripPlanCommandResult> revise(TripPlanRevisionIntent intent) {
    return _facet.revise(intent.command, idempotencyKey: intent.idempotencyKey);
  }

  Future<TripPlanCommandResult> transition(TripPlanTransitionIntent intent) {
    return _facet.transition(
      intent.command,
      idempotencyKey: intent.idempotencyKey,
    );
  }

  String _nextKey() {
    final key = _idempotencyKeyFactory().trim();
    if (key.isEmpty) {
      throw StateError('Trip revision idempotency key must not be blank');
    }
    return key;
  }
}

List<TripPlanItemInput> tripPlanItemInputs(TripPlanSlice plan) {
  return plan.items
      .map(
        (item) => TripPlanItemInput(
          itemId: item.itemId,
          dayIndex: item.dayIndex,
          orderInDay: item.orderInDay,
          kind: item.kind,
          title: item.title,
          startAt: item.startAt,
          endAt: item.endAt,
          placeRef: item.placeRef,
          note: item.note,
        ),
      )
      .toList(growable: false);
}

List<TripPlanItemInput> _normalizeItems(List<TripPlanItemInput> items) {
  if (items.length > 512) {
    throw ArgumentError.value(items.length, 'items');
  }
  final result = <TripPlanItemInput>[];
  final ids = <String>{};
  final positions = <String>{};
  for (final item in items) {
    final itemId = item.itemId.trim();
    final title = item.title.trim();
    final position = '${item.dayIndex}:${item.orderInDay}';
    if (itemId.isEmpty ||
        title.isEmpty ||
        item.dayIndex < 0 ||
        item.orderInDay < 0 ||
        !ids.add(itemId) ||
        !positions.add(position) ||
        (item.startAt != null &&
            item.endAt != null &&
            item.endAt!.isBefore(item.startAt!))) {
      throw ArgumentError.value(item, 'items');
    }
    result.add(
      TripPlanItemInput(
        itemId: itemId,
        dayIndex: item.dayIndex,
        orderInDay: item.orderInDay,
        kind: item.kind,
        title: title,
        startAt: item.startAt?.toUtc(),
        endAt: item.endAt?.toUtc(),
        placeRef: item.placeRef,
        note: _nullableTrim(item.note),
      ),
    );
  }
  result.sort((left, right) {
    final day = left.dayIndex.compareTo(right.dayIndex);
    return day != 0 ? day : left.orderInDay.compareTo(right.orderInDay);
  });
  return List.unmodifiable(result);
}

bool _sameItems(
  List<TripPlanItemSlice> current,
  List<TripPlanItemInput> proposed,
) {
  if (current.length != proposed.length) {
    return false;
  }
  for (var index = 0; index < current.length; index += 1) {
    final left = current[index];
    final right = proposed[index];
    if (left.itemId != right.itemId ||
        left.dayIndex != right.dayIndex ||
        left.orderInDay != right.orderInDay ||
        left.kind != right.kind ||
        left.title.trim() != right.title ||
        left.startAt?.toUtc() != right.startAt ||
        left.endAt?.toUtc() != right.endAt ||
        _nullableTrim(left.note) != right.note ||
        left.placeRef?.objectTypeRef != right.placeRef?.objectTypeRef ||
        left.placeRef?.objectId != right.placeRef?.objectId) {
      return false;
    }
  }
  return true;
}

String? _nullableTrim(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

bool _canTransition(TripPlanStatus current, TripPlanStatus target) =>
    switch (current) {
      TripPlanStatus.planning =>
        target == TripPlanStatus.active || target == TripPlanStatus.archived,
      TripPlanStatus.active =>
        target == TripPlanStatus.completed || target == TripPlanStatus.archived,
      TripPlanStatus.completed =>
        target == TripPlanStatus.archived || target == TripPlanStatus.active,
      TripPlanStatus.archived =>
        target == TripPlanStatus.planning || target == TripPlanStatus.active,
    };

/// 行程工作台的主要生命周期动作；其他合法跳转由后续管理面提供。
TripPlanStatus nextTripPlanStatus(TripPlanStatus current) => switch (current) {
  TripPlanStatus.planning => TripPlanStatus.active,
  TripPlanStatus.active => TripPlanStatus.completed,
  TripPlanStatus.completed => TripPlanStatus.active,
  TripPlanStatus.archived => TripPlanStatus.planning,
};
