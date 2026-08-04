// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_creation_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_creation_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_directory.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/travel/pages/trip_plans_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('trip directory renders canonical summaries and status routing', (
    tester,
  ) async {
    final directory = _FakeTripPlanDirectory();
    final creationFacet = _FakeTripPlanCreationFacet();
    String? openedTripId;
    var openedTemplates = false;

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          tripPlanDirectoryProvider.overrideWithValue(directory),
          tripPlanCreationCoordinatorProvider.overrideWithValue(
            TripPlanCreationCoordinator(
              creationFacet,
              () => 'trip-create-intent-1',
            ),
          ),
        ],
        child: MaterialApp(
          home: TripPlansPage(
            onOpenTrip: (value) => openedTripId = value,
            onOpenTemplates: () => openedTemplates = true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('西湖七日同行'), findsOneWidget);
    expect(find.text('进行中 · 12个安排 · 版本3'), findsOneWidget);
    expect(directory.statuses, <TripPlanStatus?>[null]);

    await tester.tap(find.text('西湖七日同行'));
    expect(openedTripId, 'trip-1');

    await tester.tap(find.text('行程模板'));
    expect(openedTemplates, isTrue);

    await tester.tap(find.byIcon(CupertinoIcons.add));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey<String>('travel-trip-title-field')),
      '灵隐周末同行',
    );
    await tester.pump();
    await tester.tap(
      find.byKey(const ValueKey<String>('travel-create-confirm')),
    );
    await tester.pumpAndSettle();
    expect(creationFacet.command?.title, '灵隐周末同行');
    expect(creationFacet.key, 'trip-create-intent-1');
    expect(openedTripId, 'trip-created');

    await tester.tap(find.widgetWithText(ChoiceChip, '进行中'));
    await tester.pumpAndSettle();
    expect(directory.statuses, <TripPlanStatus?>[null, TripPlanStatus.active]);
    expect(tester.takeException(), isNull);
  });
}

final class _FakeTripPlanCreationFacet implements TripPlanCreationFacet {
  CreateTripPlanCommand? command;
  String? key;

  @override
  Future<TripPlanCommandResult> create(
    CreateTripPlanCommand command, {
    required String idempotencyKey,
  }) async {
    this.command = command;
    key = idempotencyKey;
    return const TripPlanCommandResult(
      tripId: 'trip-created',
      version: 1,
      currentRevisionId: 'revision-created',
      currentRevisionNumber: 1,
      status: TripPlanStatus.planning,
      idempotentReplay: false,
    );
  }

  @override
  Future<TripPlanCommandResult> createFromTemplate(
    CreateTripPlanFromTemplateCommand command, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
  }
}

final class _FakeTripPlanDirectory implements TripPlanDirectory {
  final List<TripPlanStatus?> statuses = <TripPlanStatus?>[];

  @override
  Future<TripPlanListSlice> list({
    TripPlanStatus? status,
    String? cursor,
    int limit = 20,
  }) async {
    statuses.add(status);
    return TripPlanListSlice(
      plans: <TripPlanSummarySlice>[
        TripPlanSummarySlice(
          tripId: 'trip-1',
          title: '西湖七日同行',
          status: TripPlanStatus.active,
          currentRevisionId: 'revision-3',
          currentRevisionNumber: 3,
          itemCount: 12,
          updatedAt: DateTime.utc(2026, 8, 2, 10),
        ),
      ],
    );
  }
}
