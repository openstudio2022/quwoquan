// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/travel/timeline/trip_moment_inbox_panel.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('personal moment remains visible and explicitly manageable', (
    tester,
  ) async {
    String? managedMomentId;
    final capturedAt = DateTime.utc(2026, 8, 2, 9);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TripMomentInboxPanel(
            moments: <TripMomentSlice>[
              TripMomentSlice(
                momentId: 'moment-personal-1',
                version: 2,
                tripId: 'trip-1',
                revisionNumber: 3,
                kind: TripMomentKind.text,
                inlineText: '想带同行者再看一次日落',
                capturedAt: capturedAt,
                visibility: TripMomentVisibility.personal,
                assignmentStatus: TripMomentAssignmentStatus.unassigned,
                attributionPersonaId: 'persona-1',
                sourceVersion: 0,
                status: TripMomentStatus.active,
                createdAt: capturedAt,
                updatedAt: capturedAt,
              ),
            ],
            onManage: (momentId) => managedMomentId = momentId,
          ),
        ),
      ),
    );

    expect(find.text(TravelText.personalMoments), findsOneWidget);
    expect(find.text('想带同行者再看一次日落'), findsOneWidget);
    await tester.tap(find.text(TravelText.organizeMoment));
    expect(managedMomentId, 'moment-personal-1');
    expect(tester.takeException(), isNull);
  });
}
