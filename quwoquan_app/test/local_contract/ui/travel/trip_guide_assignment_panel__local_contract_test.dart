// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/travel/guide/trip_guide_assignment_panel.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('organizer can create first guide task from an empty panel', (
    tester,
  ) async {
    var created = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TripGuideAssignmentPanel(
            plan: _plan(),
            assignments: const <TripGuideAssignment>[],
            activePersonaId: 'persona-organizer',
            onCreate: () => created = true,
          ),
        ),
      ),
    );

    expect(find.text('领队与讲解任务'), findsOneWidget);
    await tester.tap(find.text('分配任务'));
    expect(created, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('guide sees attributed task and can accept it', (tester) async {
    TripGuideAssignment? advanced;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TripGuideAssignmentPanel(
            plan: _plan(),
            assignments: <TripGuideAssignment>[_assignment()],
            activePersonaId: 'persona-guide',
            assigneeLabels: const <String, String>{'persona-guide': '西湖讲解员阿青'},
            onAdvance: (value) => advanced = value,
          ),
        ),
      ),
    );

    expect(find.text('集合与出发说明'), findsOneWidget);
    expect(find.text('持证导游'), findsOneWidget);
    expect(find.text('负责人 西湖讲解员阿青'), findsOneWidget);
    expect(find.textContaining('persona-guide'), findsNothing);
    expect(find.text('公开资质声明'), findsOneWidget);
    await tester.tap(find.text('接受任务'));
    expect(advanced?.taskKey, 'collection-1');
    expect(tester.takeException(), isNull);
  });

  testWidgets('unrelated participant cannot transition guide task', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TripGuideAssignmentPanel(
            plan: _plan(),
            assignments: <TripGuideAssignment>[_assignment()],
            activePersonaId: 'persona-other',
            onAdvance: (_) {},
          ),
        ),
      ),
    );

    expect(find.text('接受任务'), findsNothing);
  });

  testWidgets('only organizer can reassign an unfinished guide task', (
    tester,
  ) async {
    TripGuideAssignment? reassigned;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TripGuideAssignmentPanel(
            plan: _plan(),
            assignments: <TripGuideAssignment>[_assignment()],
            activePersonaId: 'persona-organizer',
            onReassign: (value) => reassigned = value,
          ),
        ),
      ),
    );

    await tester.tap(find.text('改派负责人'));
    expect(reassigned?.taskKey, 'collection-1');
    expect(tester.takeException(), isNull);
  });
}

TripPlanSlice _plan() {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripPlanSlice(
    tripId: 'trip-1',
    version: 3,
    organizerPersonaId: 'persona-organizer',
    title: '西湖同行',
    status: TripPlanStatus.active,
    sourceAttributions: const <TripPlanSourceAttribution>[],
    currentRevisionId: 'revision-3',
    currentRevisionNumber: 3,
    items: const <TripPlanItemSlice>[],
    createdAt: now,
    updatedAt: now,
  );
}

TripGuideAssignment _assignment() {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripGuideAssignment(
    id: 'assignment-1',
    version: 2,
    tripId: 'trip-1',
    taskKey: 'collection-1',
    assigneePersonaId: 'persona-guide',
    role: TripGuideRole.licensedGuide,
    taskKind: TripGuideTaskKind.collection,
    title: '集合与出发说明',
    sourceRevisionNumber: 3,
    attributionKind: TripGuideAttributionKind.professionalCommentary,
    attributionPersonaId: 'persona-guide',
    publicQualificationPersonaId: 'persona-guide',
    status: TripGuideAssignmentStatus.assigned,
    createdByPersonaId: 'persona-organizer',
    createdAt: now,
    updatedAt: now,
  );
}
