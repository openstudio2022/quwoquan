// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/presentation/trip_plan_revision_flow.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('organizer rename flow returns one explicit revision intent', (
    tester,
  ) async {
    final coordinator = TripPlanRevisionCoordinator(
      _NoopRevisionFacet(),
      () => 'revision-intent-1',
    );
    TripPlanRevisionIntent? result;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                result = await composeTripPlanRevision(
                  context,
                  plan: _plan(),
                  coordinator: coordinator,
                  itemIdFactory: () => 'item-new',
                );
              },
              child: const Text('调整'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('调整'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('第1天 · 西湖晨游'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('修改安排名称'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(CupertinoTextField), '西湖午后游');
    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(CupertinoTextField), '避开早高峰');
    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('重要变化'));
    await tester.pumpAndSettle();

    expect(result?.command.items.single.title, '西湖午后游');
    expect(result?.command.changeReason, '避开早高峰');
    expect(result?.command.severity, TripRevisionSeverity.important);
    expect(result?.idempotencyKey, 'revision-intent-1');
    expect(tester.takeException(), isNull);
  });
}

final class _NoopRevisionFacet implements TripPlanRevisionFacet {
  @override
  Future<TripPlanCommandResult> revise(
    ReviseTripPlanCommand command, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<TripPlanCommandResult> transition(
    TransitionTripPlanCommand command, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
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
