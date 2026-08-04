// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'revision freezes CAS snapshot, normalized items and one retry key',
    () async {
      final facet = _RecordingRevisionFacet();
      final coordinator = TripPlanRevisionCoordinator(
        facet,
        () => 'trip-revision-intent-1',
      );
      final intent = coordinator.prepareRevision(
        plan: _plan(),
        items: <TripPlanItemInput>[
          TripPlanItemInput(
            itemId: ' item-1 ',
            dayIndex: 0,
            orderInDay: 0,
            kind: TripPlanItemKind.sight,
            title: ' 西湖晨游改为午后 ',
          ),
        ],
        changeReason: ' 避开早高峰 ',
        severity: TripRevisionSeverity.important,
      );

      await coordinator.revise(intent);
      await coordinator.revise(intent);

      expect(intent.command.expectedRevisionNumber, 3);
      expect(intent.command.changeReason, '避开早高峰');
      expect(intent.command.items.single.title, '西湖晨游改为午后');
      expect(facet.keys, <String>[
        'trip-revision-intent-1',
        'trip-revision-intent-1',
      ]);
    },
  );

  test(
    'no-op revision and illegal lifecycle transition fail before Remote',
    () {
      final coordinator = TripPlanRevisionCoordinator(
        _RecordingRevisionFacet(),
        () => 'trip-revision-intent-1',
      );
      expect(
        () => coordinator.prepareRevision(
          plan: _plan(),
          items: tripPlanItemInputs(_plan()),
          changeReason: '没有变化',
          severity: TripRevisionSeverity.minor,
        ),
        throwsArgumentError,
      );
      expect(
        () => coordinator.prepareTransition(
          plan: _plan(),
          targetStatus: TripPlanStatus.completed,
        ),
        throwsArgumentError,
      );
    },
  );

  test('lifecycle transition freezes current revision and retry key', () async {
    final facet = _RecordingRevisionFacet();
    final coordinator = TripPlanRevisionCoordinator(
      facet,
      () => 'trip-transition-intent-1',
    );
    final intent = coordinator.prepareTransition(
      plan: _plan(),
      targetStatus: TripPlanStatus.active,
    );

    await coordinator.transition(intent);
    await coordinator.transition(intent);

    expect(intent.command.expectedRevisionNumber, 3);
    expect(facet.keys, <String>[
      'trip-transition-intent-1',
      'trip-transition-intent-1',
    ]);
    expect(nextTripPlanStatus(TripPlanStatus.active), TripPlanStatus.completed);
  });
}

final class _RecordingRevisionFacet implements TripPlanRevisionFacet {
  final List<String> keys = <String>[];

  @override
  Future<TripPlanCommandResult> revise(
    ReviseTripPlanCommand command, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _result(command.tripId, command.expectedRevisionNumber + 1);
  }

  @override
  Future<TripPlanCommandResult> transition(
    TransitionTripPlanCommand command, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _result(command.tripId, command.expectedRevisionNumber + 1);
  }
}

TripPlanSlice _plan() {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripPlanSlice(
    tripId: 'trip-1',
    version: 3,
    organizerPersonaId: 'persona-1',
    title: '西湖七日同行',
    status: TripPlanStatus.planning,
    sourceAttributions: const <TripPlanSourceAttribution>[],
    currentRevisionId: 'revision-3',
    currentRevisionNumber: 3,
    items: const <TripPlanItemSlice>[
      TripPlanItemSlice(
        itemId: 'item-1',
        dayIndex: 0,
        orderInDay: 0,
        kind: TripPlanItemKind.sight,
        title: '西湖晨游',
      ),
    ],
    createdAt: now,
    updatedAt: now,
  );
}

TripPlanCommandResult _result(String tripId, int revision) =>
    TripPlanCommandResult(
      tripId: tripId,
      version: revision,
      currentRevisionId: 'revision-$revision',
      currentRevisionNumber: revision,
      status: TripPlanStatus.planning,
      idempotentReplay: false,
    );
